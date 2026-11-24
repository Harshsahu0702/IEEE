"""
Universal VLM Reasoner.

The cognitive brain of the monitoring platform.
Receives a frame and a natural language monitoring goal from the user,
and returns a structured decision:
{
    "incident_detected": bool,
    "confidence": float,       # 0.0 – 1.0
    "explanation": str,        # Human-readable description of what was observed
    "action_required": str,    # "none" | "alert" | "alarm" | "log"
    "metrics": dict            # Dynamic key-value metrics for the adaptive UI
}

Supports:
- Gemini 2.0 Flash (cloud, via GEMINI_API_KEY in .env)
- Offline fallback: rule-based heuristic (no API key required)
"""

import base64
import json
import logging
import re
import time
from typing import Optional
import cv2
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

class ReasonerResult:
    __slots__ = ("incident_detected", "confidence", "explanation", "action_required", "metrics", "latency_ms", "boxes")

    def __init__(
        self,
        incident_detected: bool,
        confidence: float,
        explanation: str,
        action_required: str,
        metrics: dict,
        latency_ms: float = 0.0,
        boxes: Optional[list] = None,
    ):
        self.incident_detected = incident_detected
        self.confidence = confidence
        self.explanation = explanation
        self.action_required = action_required  # "none" | "alert" | "alarm" | "log"
        self.metrics = metrics                  # e.g. {"person_count": 3, "risk_score": 72}
        self.latency_ms = latency_ms
        self.boxes = boxes or []                # list of {"label": str, "box_2d": [ymin, xmin, ymax, xmax]}

    def to_dict(self) -> dict:
        return {
            "incident_detected": self.incident_detected,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "action_required": self.action_required,
            "metrics": self.metrics,
            "latency_ms": self.latency_ms,
            "boxes": self.boxes,
        }


# ---------------------------------------------------------------------------
# Gemini VLM backend
# ---------------------------------------------------------------------------

def _encode_frame_b64(frame: np.ndarray, quality: int = 70) -> str:
    """Encode OpenCV frame → base64 JPEG string for Gemini API."""
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buffer).decode("utf-8")


def _build_prompt(user_goal: str, context: dict) -> str:
    """
    Build a structured system+user prompt for the VLM that strictly enforces
    user-defined prompt triggers (e.g. 'alert if person comes in frame', 'alert if fan comes to the frame').
    """
    sensor_summary = ""
    if context:
        parts = []
        if "temperature" in context:
            parts.append(f"Temperature: {context['temperature']}°C")
        if "humidity" in context:
            parts.append(f"Humidity: {context['humidity']}%")
        if "gas_level" in context:
            parts.append(f"Gas/Smoke: {context['gas_level']} ppm")
        if "motion_detected" in context:
            parts.append(f"PIR Motion: {'Triggered' if context['motion_detected'] else 'Idle'}")
        if parts:
            sensor_summary = "Live sensor context from Arduino:\n" + "\n".join(parts) + "\n\n"

    return f"""You are OmniSense AI, an intelligent real-time computer vision alert engine.

USER DIRECTIVE & ALERT CONDITION:
\"{user_goal}\"

{sensor_summary}INSTRUCTIONS:
1. Examine the user directive carefully. Determine what specific condition, person, object, action, or event triggers an alert:
   - e.g. "alert if any person comes in frame" -> Condition: Presence of any human in view.
   - e.g. "alert if fan comes to the frame" -> Condition: Presence or appearance of a fan.
   - e.g. "alert if fan is moving" -> Condition: A fan with spinning or moving blades.
   - e.g. "alert if someone stands up / looks sideways" -> Condition: That specific posture or gesture.
   - e.g. "alert if smoke or gas occurs" -> Condition: Visible smoke, flame, or elevated sensor readings.

2. Inspect the camera frame right now. Does the image CURRENTLY exhibit this trigger condition?
   - If YES (the condition is observed in the frame):
     * "incident_detected": true
     * "action_required": "alert" (or "alarm" if dangerous hazard like fire/weapon/injury)
     * "explanation": A clear, concise sentence stating what triggered the alert (e.g., "Person detected entering the camera frame", "Ceiling fan observed in the scene").
     * "boxes": Bounding box(es) around the exact object(s) or person(s) that caused the alert.
   - If NO (the condition is NOT observed in the frame):
     * "incident_detected": false
     * "action_required": "none"
     * "explanation": A brief note that the scene is clear (e.g., "No person observed in frame", "No fan detected").
     * "boxes": Bounding box(es) of any other prominent objects if relevant, or empty list [].

OUTPUT FORMAT:
Respond ONLY with a valid JSON object (no markdown, no preamble):
{{
  "incident_detected": true or false,
  "confidence": 0.0 to 1.0,
  "explanation": "concise description of why alert was triggered or why scene is clear",
  "action_required": "none" or "alert" or "alarm" or "log",
  "metrics": {{
    "target_detected": true or false,
    "target_name": "name of target object/event",
    "status": "clear or alerting"
  }},
  "boxes": [
    {{
      "label": "target label (e.g. fan, person, stove)",
      "box_2d": [ymin, xmin, ymax, xmax]
    }}
  ]
}}

Rules:
- Coordinates [ymin, xmin, ymax, xmax] MUST be normalized integers between 0 and 1000.
- "action_required": use "alarm" ONLY for life safety hazards (fire, brandished weapons, medical emergency); use "alert" for all other prompt conditions.
- NEVER mention or attempt to identify personal identities or faces.
"""


def _call_gemini(frame: np.ndarray, user_goal: str, context: dict) -> ReasonerResult:
    """Call Google GenAI Vision API (gemini-3.5-flash-lite / gemini-3.8-flash)."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Encode frame to JPEG
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        image_part = types.Part.from_bytes(data=buffer.tobytes(), mime_type="image/jpeg")

        prompt = _build_prompt(user_goal, context)

        t0 = time.time()
        # Try gemini-3.5-flash-lite, fallback to gemini-3.8-flash
        model_names = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
        response = None
        for m in model_names:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=[image_part, prompt]
                )
                if response and response.text:
                    break
            except Exception as me:
                logger.warning(f"Gemini model {m} attempt failed: {me}")

        if not response or not response.text:
            return _offline_fallback(frame, user_goal, context)

        latency_ms = (time.time() - t0) * 1000

        # Robust regex-based JSON extraction (handles markdown or preambles)
        match = re.search(r"\{.*\}", response.text, re.DOTALL)
        if match:
            raw = match.group(0)
        else:
            raw = response.text.strip()

        data = json.loads(raw)
        raw_boxes = data.get("boxes", [])
        return ReasonerResult(
            incident_detected=bool(data.get("incident_detected", False)),
            confidence=float(data.get("confidence", 0.5)),
            explanation=str(data.get("explanation", "No description returned.")),
            action_required=str(data.get("action_required", "none")),
            metrics=dict(data.get("metrics", {})),
            latency_ms=latency_ms,
            boxes=raw_boxes if isinstance(raw_boxes, list) else [],
        )

    except json.JSONDecodeError as e:
        logger.warning(f"VLM returned non-JSON response: {e}")
        return _offline_fallback(frame, user_goal, context)
    except Exception as e:
        logger.error(f"Gemini VLM call failed: {e}")
        return _offline_fallback(frame, user_goal, context)


# ---------------------------------------------------------------------------
# Offline fallback (no API key)
# ---------------------------------------------------------------------------

def _offline_fallback(frame: np.ndarray, user_goal: str, context: dict) -> ReasonerResult:
    """
    Heuristic offline reasoner when no Gemini API key is configured.
    Uses basic computer vision signals and prompt matching to evaluate alerts.
    """
    boxes = []
    try:
        from backend.vision.detector import PersonDetector
        detector = PersonDetector.get_instance()
        boxes = detector.detect(frame)
    except Exception as de:
        logger.debug(f"PersonDetector offline unavailable: {de}")

    person_count = len(boxes)

    gas = context.get("gas_level", 0)
    temp = context.get("temperature", 25)
    motion = context.get("motion_detected", False)

    incident = False
    action = "none"
    explanation = f"Offline mode: Monitoring '{user_goal}'."
    confidence = 0.70

    goal_lower = user_goal.lower()

    # 1. Person / headcount / presence directive
    if any(w in goal_lower for w in ["person", "people", "someone", "anyone", "human", "crowd", "man", "woman"]):
        limit = 0 if any(w in goal_lower for w in ["any", "a person", "someone", "comes", "enters"]) else 4
        for w in goal_lower.split():
            if w.isdigit():
                limit = int(w)
                break
        if person_count > limit:
            incident = True
            action = "alert"
            explanation = f"Offline: {person_count} person(s) detected in frame matching directive '{user_goal}'."
            confidence = 0.85
        else:
            explanation = f"Offline: No unauthorized persons detected (count: {person_count}, limit: {limit})."

    # 2. Fan / motion / movement directive
    elif any(w in goal_lower for w in ["fan", "motion", "move", "moving", "active", "movement"]):
        if motion:
            incident = True
            action = "alert"
            explanation = f"Offline: Active movement/motion detected matching directive '{user_goal}'."
            confidence = 0.80
        else:
            explanation = f"Offline: Scene is idle, no motion detected for directive '{user_goal}'."

    # 3. Environmental / hazard directive
    elif any(w in goal_lower for w in ["gas", "smoke", "fire", "leak", "temperature", "heat"]):
        if gas > 400:
            incident = True
            action = "alarm"
            explanation = f"Offline: Gas level {gas} ppm exceeds safe threshold."
            confidence = 0.85
        elif temp > 35:
            incident = True
            action = "alert"
            explanation = f"Offline: Temperature {temp}°C is elevated."
            confidence = 0.80

    # 4. Security / intrusion directive
    elif any(w in goal_lower for w in ["restricted", "intrusion", "trespass", "unauthorized", "zone"]):
        if person_count > 0:
            incident = True
            action = "alert"
            explanation = f"Offline: {person_count} person(s) detected in monitored area."
            confidence = 0.75

    h, w = frame.shape[:2]
    formatted_boxes = []
    for b in boxes:
        ymin = max(0, min(1000, int(b.y1 * 1000 / h)))
        xmin = max(0, min(1000, int(b.x1 * 1000 / w)))
        ymax = max(0, min(1000, int(b.y2 * 1000 / h)))
        xmax = max(0, min(1000, int(b.x2 * 1000 / w)))
        formatted_boxes.append({"label": "person", "box_2d": [ymin, xmin, ymax, xmax]})

    return ReasonerResult(
        incident_detected=incident,
        confidence=confidence,
        explanation=explanation,
        action_required=action,
        metrics={
            "person_count": person_count,
            "temperature": temp,
            "gas_level": gas,
            "motion_sensor": motion,
        },
        boxes=formatted_boxes,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

class VLMReasoner:
    """
    Singleton VLM Reasoner.
    Routes to Gemini if API key is set, otherwise uses offline heuristic.
    """

    _instance: Optional["VLMReasoner"] = None

    def __init__(self):
        self._use_gemini = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())
        mode = "Gemini 2.0 Flash (cloud)" if self._use_gemini else "Offline Heuristic (no API key)"
        logger.info(f"VLMReasoner initialized in mode: {mode}")

    @classmethod
    def get_instance(cls) -> "VLMReasoner":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reason(
        self,
        frame: np.ndarray,
        user_goal: str,
        sensor_context: Optional[dict] = None,
    ) -> ReasonerResult:
        """
        Primary inference call.

        Args:
            frame: OpenCV BGR image (current camera frame).
            user_goal: Natural language goal the operator set (e.g., "Watch for cheating in exam").
            sensor_context: Optional dict of live IoT readings from Arduino.

        Returns:
            ReasonerResult with structured decision.
        """
        context = sensor_context or {}

        if self._use_gemini:
            return _call_gemini(frame, user_goal, context)
        else:
            return _offline_fallback(frame, user_goal, context)


def get_vlm_reasoner() -> VLMReasoner:
    """Return singleton instance of VLMReasoner."""
    return VLMReasoner.get_instance()
