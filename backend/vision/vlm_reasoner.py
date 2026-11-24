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
    Build a structured system+user prompt for the VLM.
    context: extra info such as sensor readings (temp, gas, motion) from Arduino.
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
            parts.append(f"PIR Motion Sensor: {'Triggered' if context['motion_detected'] else 'Idle'}")
        if parts:
            sensor_summary = "Live sensor readings from Arduino:\n" + "\n".join(parts) + "\n\n"

    return f"""You are OmniSense AI, an intelligent multi-modal monitoring assistant.

Monitoring goal set by the operator:
\"{user_goal}\"

{sensor_summary}Analyze the provided camera frame carefully.

Respond ONLY with a valid JSON object in this exact format (no markdown, no preamble):
{{
  "incident_detected": true or false,
  "confidence": 0.0 to 1.0,
  "explanation": "clear one-sentence description of what you observed",
  "action_required": "none" or "alert" or "alarm" or "log",
  "metrics": {{
    "key": value
  }}
}}

Rules:
- "metrics" must contain only the most relevant observable data points for the goal (e.g. person_count, risk_score, temperature_status, description).
- If the scene is calm and matches what is expected, set incident_detected: false and action_required: "none".
- If something violates the monitoring goal, set incident_detected: true.
- "alarm" is only for critical physical danger (fire, violence, medical emergency).
- "alert" is for policy violations (cheating, unauthorized presence, threshold exceeded).
- "log" is for data collection only with no immediate urgency.
- NEVER mention or attempt to identify specific people's faces or personal identities.
"""


def _call_gemini(frame: np.ndarray, user_goal: str, context: dict) -> ReasonerResult:
    """Call Gemini 2.0 Flash vision API."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)

        model = genai.GenerativeModel("gemini-2.0-flash")

        img_b64 = _encode_frame_b64(frame)
        prompt = _build_prompt(user_goal, context)

        t0 = time.time()
        response = model.generate_content([
            {"mime_type": "image/jpeg", "data": img_b64},
            prompt,
        ])
        latency_ms = (time.time() - t0) * 1000

        raw = response.text.strip()
        # Strip markdown code fences if model wraps response
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        return ReasonerResult(
            incident_detected=bool(data.get("incident_detected", False)),
            confidence=float(data.get("confidence", 0.5)),
            explanation=str(data.get("explanation", "No description returned.")),
            action_required=str(data.get("action_required", "none")),
            metrics=dict(data.get("metrics", {})),
            latency_ms=latency_ms,
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
    Uses basic computer vision signals to produce a best-effort result.
    """
    from backend.vision.detector import PersonDetector

    detector = PersonDetector.get_instance()
    boxes = detector.detect(frame)
    person_count = len(boxes)

    # Simple heuristic: combine sensor context + person count
    gas = context.get("gas_level", 0)
    temp = context.get("temperature", 25)
    motion = context.get("motion_detected", False)

    incident = False
    action = "log"
    explanation = f"Offline mode: {person_count} person(s) detected in frame."
    confidence = 0.6

    goal_lower = user_goal.lower()

    # Crowd / headcount goals
    if any(w in goal_lower for w in ["people", "crowd", "count", "person", "headcount"]):
        limit = 4
        for w in goal_lower.split():
            if w.isdigit():
                limit = int(w)
                break
        if person_count > limit:
            incident = True
            action = "alert"
            explanation = f"Offline: {person_count} people detected, exceeding limit of {limit}."
            confidence = 0.78

    # Environmental / hazard goals
    if any(w in goal_lower for w in ["gas", "smoke", "fire", "leak", "temperature", "heat"]):
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

    # Security / intrusion goals
    if any(w in goal_lower for w in ["restricted", "intrusion", "trespass", "unauthorized", "zone"]):
        if person_count > 0:
            incident = True
            action = "alert"
            explanation = f"Offline: {person_count} person(s) detected in monitored area."
            confidence = 0.70

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
