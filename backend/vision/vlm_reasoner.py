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


def _call_ollama(frame: np.ndarray, user_goal: str, context: dict) -> ReasonerResult:
    """Call local Ollama Vision API (supporting fast Moondream or Qwen2.5-VL)."""
    try:
        import urllib.request

        # Encode frame to JPEG then base64
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        b64_image = base64.b64encode(buffer.tobytes()).decode("utf-8")

        model_name = getattr(settings, "OLLAMA_MODEL", "moondream")
        is_moondream = "moondream" in model_name.lower()

        if is_moondream:
            prompt = f"Question: Does this image show: {user_goal}? Answer Yes or No first, then briefly describe what you see."
            payload = {
                "model": model_name,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False,
            }
        else:
            prompt = _build_prompt(user_goal, context)
            payload = {
                "model": model_name,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False,
                "format": "json",
            }

        req = urllib.request.Request(
            f"{getattr(settings, 'OLLAMA_HOST', 'http://127.0.0.1:11434')}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        t0 = time.time()
        with urllib.request.urlopen(req, timeout=45) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        latency_ms = (time.time() - t0) * 1000
        raw_text = resp_data.get("response", "").strip()

        if is_moondream:
            raw_lower = raw_text.lower()
            tokens = raw_lower.split()
            first_word = tokens[0].strip(".,!?:;") if tokens else ""

            is_yes = first_word == "yes" or " yes," in raw_lower or " yes." in raw_lower or "is visible" in raw_lower or "there is a" in raw_lower
            is_no = first_word == "no" or "there is no" in raw_lower or "no visible" in raw_lower or "cannot see" in raw_lower or "does not appear" in raw_lower

            directive_words = [
                w.lower().strip(".,!?:;") for w in user_goal.split()
                if len(w) > 3 and w.lower() not in ["alert", "frame", "comes", "scene", "monitor", "this"]
            ]
            has_target = any(w in raw_lower for w in directive_words)

            if is_yes and not is_no:
                is_incident = True
            elif is_no:
                is_incident = False
            else:
                is_incident = has_target and bool(raw_text.strip())

            return ReasonerResult(
                incident_detected=is_incident,
                confidence=0.88 if is_incident else 0.70,
                explanation=raw_text if raw_text else f"Moondream: Scene clear for '{user_goal}'.",
                action_required="alert" if is_incident else "none",
                metrics={"local_vlm": "moondream", "vlm_latency_ms": round(latency_ms, 1)},
                latency_ms=latency_ms,
                boxes=[],
            )

        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            raw = match.group(0)
        else:
            raw = raw_text

        data = json.loads(raw)
        raw_boxes = data.get("boxes", [])

        incident_val = data.get("incident_detected")
        if incident_val is None:
            incident_val = data.get("detected", False)
        is_incident = bool(incident_val)

        action_val = data.get("action_required")
        if not action_val or action_val == "none":
            action_val = "alert" if is_incident else "none"

        return ReasonerResult(
            incident_detected=is_incident,
            confidence=float(data.get("confidence", 0.88 if is_incident else 0.70)),
            explanation=str(data.get("explanation", "Local VLM evaluated scene.")),
            action_required=str(action_val),
            metrics=dict(data.get("metrics", {})),
            latency_ms=latency_ms,
            boxes=raw_boxes if isinstance(raw_boxes, list) else [],
        )
    except Exception as e:
        logger.warning(f"Local Ollama VLM call failed ({e}); falling back to offline detector.")
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
# Dynamic Natural-Language Goal & Quantity Parsing (Zero Hardcoded Object Lists)
# ---------------------------------------------------------------------------

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1000000}

_DIRECTIVE_STOPWORDS = {
    "alert", "warn", "notify", "trigger", "alarm", "report", "log",
    "if", "when", "whenever", "where", "that", "which", "who",
    "any", "a", "an", "the", "this", "these", "those", "some",
    "comes", "come", "coming", "enters", "enter", "entering", "gather", "gathering",
    "appears", "appear", "appearing", "seen", "visible", "present",
    "shows", "show", "showing", "found", "detected", "detect",
    "monitor", "watch", "check", "count", "track", "find",
    "frame", "camera", "webcam", "video", "screen", "scene", "view", "image", "area", "zone",
    "is", "are", "was", "were", "be", "been", "being", "has", "have", "had",
    "in", "into", "inside", "on", "onto", "at", "to", "of", "from", "with", "near", "by",
    "up", "down", "out", "off", "away", "around", "together",
    "there", "here", "and", "or", "not", "no", "more", "than", "less", "least",
    "greater", "exceeds", "above", "below", "under", "over", "equals", "only",
    "thing", "anything", "something", "object", "item",
}

_ACTION_OR_STATE_WORDS = {
    "moving", "move", "moves", "spinning", "spin", "spins", "rotating", "rotate", "rotates",
    "running", "run", "runs", "falling", "fall", "falls", "fallen",
    "fighting", "fight", "fights", "hitting", "hit", "hits", "attacking", "attack", "attacks",
    "cheating", "cheat", "cheats", "sleeping", "sleep", "sleeps",
    "standing", "stand", "stands", "sitting", "sit", "sits", "lying", "lie", "lies",
    "walking", "walk", "walks", "smoking", "smoke", "smokes",
    "burning", "burn", "burns", "fire", "flame", "flames", "gas", "leak", "leaks",
    "temperature", "heat", "humidity", "holding", "hold", "holds",
    "wearing", "wear", "wears", "using", "use", "uses", "looking", "look", "looks",
    "crying", "cry", "cries", "shouting", "shout", "shouts", "waving", "wave", "waves",
    "climbing", "climb", "climbs", "jumping", "jump", "jumps",
    "breaking", "break", "breaks", "stealing", "steal", "steals",
}


def _words_to_int(tokens: list[str]) -> Optional[int]:
    """Convert an arbitrary-length sequence of English number words into an integer."""
    current = 0
    total = 0
    matched = False
    for tok in tokens:
        if tok in _UNITS:
            current += _UNITS[tok]
            matched = True
        elif tok in _TENS:
            current += _TENS[tok]
            matched = True
        elif tok in _SCALES:
            scale = _SCALES[tok]
            current = max(1, current) * scale
            if scale >= 1000:
                total += current
                current = 0
            matched = True
        elif tok == "and" and matched:
            continue
        else:
            break
    return (total + current) if matched else None


def _extract_required_count(goal_lower: str) -> tuple[int, str]:
    """
    Extract dynamic count threshold of any magnitude from the command.
    Strips duration/camera identifiers first so 'for 30 minutes' is never misread as count=30.
    Returns (required_count, cleaned_text_without_numbers).
    """
    cleaned = re.sub(r"\bfor\s+\d+\s*(?:sec|second|seconds|min|minute|minutes|hr|hrs|hour|hours)\b", " ", goal_lower)
    cleaned = re.sub(r"\b(?:camera|cam|webcam|sensor)\s*\d+\b", " ", cleaned)

    # 1. Check strict inequality modifiers: "more than N" / "greater than N" / "above N"
    is_strict_gt = bool(re.search(r"\b(?:more than|greater than|exceeds?|above|over)\b", cleaned))

    # 2. Match digits of any size
    digit_m = re.search(r"\b(\d+)\b", cleaned)
    if digit_m:
        val = int(digit_m.group(1))
        required = (val + 1) if is_strict_gt else max(1, val)
        cleaned_no_num = cleaned[:digit_m.start()] + " " + cleaned[digit_m.end():]
        return required, cleaned_no_num

    # 3. Match arbitrary English number word sequences ("two", "twenty five", "one hundred")
    tokens = re.findall(r"[a-z]+", cleaned)
    num_tokens_set = set(_UNITS) | set(_TENS) | set(_SCALES)
    for i, tok in enumerate(tokens):
        if tok in num_tokens_set:
            val = _words_to_int(tokens[i:])
            if val is not None:
                required = (val + 1) if is_strict_gt else max(1, val)
                # Strip matched number words
                consumed = 0
                for t in tokens[i:]:
                    if t in num_tokens_set or (t == "and" and consumed > 0):
                        consumed += 1
                    else:
                        break
                to_remove = set(tokens[i:i + consumed]) - {"and"}
                cleaned_no_num = " ".join(w for w in tokens if w not in to_remove)
                return required, cleaned_no_num

    return 1, cleaned


def _normalize_noun(word: str) -> str:
    """Standard English morphology normalization (no hardcoded object list)."""
    if word in {"people", "persons", "humans", "someone", "anyone", "anybody", "somebody", "individual", "individuals"}:
        return "person"
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("es") and word[-3] in {"s", "x", "z", "h"}:
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _parse_goal_directive(user_goal: str) -> dict:
    """
    Parse any natural language goal into open-vocabulary target entities,
    unbounded count threshold, and whether Tier 2 VLM semantic reasoning is required.
    """
    goal_lower = user_goal.lower().strip()
    required_count, cleaned_text = _extract_required_count(goal_lower)

    raw_words = re.findall(r"[a-z]+", cleaned_text)
    requires_vlm = any(
        (w in _ACTION_OR_STATE_WORDS or _normalize_noun(w) in _ACTION_OR_STATE_WORDS)
        for w in raw_words
    )

    target_phrases: list[str] = []
    current_phrase: list[str] = []
    for w in raw_words:
        norm = _normalize_noun(w)
        if (
            w in _DIRECTIVE_STOPWORDS
            or w in _ACTION_OR_STATE_WORDS
            or norm in _DIRECTIVE_STOPWORDS
            or norm in _ACTION_OR_STATE_WORDS
        ):
            if current_phrase:
                phrase = " ".join(current_phrase)
                if phrase not in target_phrases:
                    target_phrases.append(phrase)
                if len(current_phrase) > 1 and current_phrase[-1] not in target_phrases:
                    target_phrases.append(current_phrase[-1])
                current_phrase = []
        else:
            current_phrase.append(norm)

    if current_phrase:
        phrase = " ".join(current_phrase)
        if phrase not in target_phrases:
            target_phrases.append(phrase)
        if len(current_phrase) > 1 and current_phrase[-1] not in target_phrases:
            target_phrases.append(current_phrase[-1])

    if not target_phrases:
        requires_vlm = True

    return {
        "targets": target_phrases,
        "required_count": required_count,
        "requires_vlm": requires_vlm,
    }


def _label_matches_targets(class_name: str, targets: list[str]) -> bool:
    """Check if a detected class label matches any extracted open-vocabulary target."""
    cls_norm = _normalize_noun(class_name.lower().strip())
    for t in targets:
        t_norm = _normalize_noun(t.lower().strip())
        if cls_norm == t_norm:
            return True
        if re.search(rf"\b{re.escape(t_norm)}\b", cls_norm) or re.search(rf"\b{re.escape(cls_norm)}\b", t_norm):
            return True
    return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

class VLMReasoner:
    """
    Singleton VLM + Open-Vocabulary Reasoner.
    Tier 1: UniversalWorldDetector (OpenVINO INT8 / YOLOWorld Open-Vocabulary)
    Tier 2: Semantic VLM (Ollama / Gemini) for actions, postures, and unseen states
    """

    _instance: Optional["VLMReasoner"] = None

    def __init__(self):
        provider = getattr(settings, "VLM_PROVIDER", "ollama").lower()
        if provider == "ollama":
            self._mode = "ollama"
            logger.info(f"VLMReasoner initialized in mode: Local Ollama ({getattr(settings, 'OLLAMA_MODEL', 'moondream')})")
        elif provider == "gemini" and settings.GEMINI_API_KEY:
            self._mode = "gemini"
            logger.info("VLMReasoner initialized in mode: Gemini Cloud")
        else:
            self._mode = "ollama"
            logger.info("VLMReasoner initialized in mode: Auto (Ollama)")

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
        Primary two-tier inference call.
        1. Runs UniversalWorldDetector (Open-Vocabulary) for all live object boxes.
        2. Evaluates spatial/count rules directly on Tier 1, or delegates semantic
           action/state checks to Tier 2 VLM while preserving live spatial boxes.
        """
        context = sensor_context or {}
        spec = _parse_goal_directive(user_goal)
        targets: list[str] = spec["targets"]
        required_count: int = spec["required_count"]
        requires_vlm: bool = spec["requires_vlm"]

        # Tier 1: Open-Vocabulary World Detection (live boxes for all visible objects)
        all_boxes: list[dict] = []
        matched_boxes: list[dict] = []
        world_engine = "none"
        world_latency = 0.0

        try:
            from backend.vision.detector import UniversalWorldDetector
            detector = UniversalWorldDetector.get_instance()
            detections, world_engine, world_latency = detector.detect_all(
                frame,
                target_classes=targets if targets else None,
            )
            h, w = frame.shape[:2]
            for d in detections:
                ymin = max(0, min(1000, int(d.y1 * 1000 / h)))
                xmin = max(0, min(1000, int(d.x1 * 1000 / w)))
                ymax = max(0, min(1000, int(d.y2 * 1000 / h)))
                xmax = max(0, min(1000, int(d.x2 * 1000 / w)))
                is_target = _label_matches_targets(d.class_name, targets) if targets else False
                box_entry = {
                    "label": d.class_name,
                    "confidence": d.confidence,
                    "is_target": is_target,
                    "box_2d": [ymin, xmin, ymax, xmax],
                }
                all_boxes.append(box_entry)
                if is_target:
                    matched_boxes.append(box_entry)
        except Exception as e:
            logger.warning(f"UniversalWorldDetector failed: {e}")

        # Spatial / Object-Presence / Count directives resolve cleanly on Tier 1
        if not requires_vlm and targets:
            actual_count = len(matched_boxes)
            primary_target = targets[0]
            detected = actual_count >= required_count
            if detected:
                explanation = f"{actual_count} {primary_target}(s) detected in frame (meets '{user_goal}')."
                action = "alert"
            else:
                explanation = f"Detected {actual_count} {primary_target}(s) in frame (requires {required_count})."
                action = "none"

            return ReasonerResult(
                incident_detected=detected,
                confidence=max((b["confidence"] for b in matched_boxes), default=0.88) if detected else 0.85,
                explanation=explanation,
                action_required=action,
                metrics={
                    "detector": world_engine,
                    "targets": targets,
                    "matched_count": actual_count,
                    "required_count": required_count,
                    "total_objects": len(all_boxes),
                    "latency_ms": round(world_latency, 1),
                },
                latency_ms=world_latency,
                boxes=all_boxes,
            )

        # Tier 2: Semantic / Temporal Action / State reasoning via configured VLM
        if self._mode == "ollama":
            vlm_res = _call_ollama(frame, user_goal, context)
        elif self._mode == "gemini":
            vlm_res = _call_gemini(frame, user_goal, context)
        else:
            vlm_res = _offline_fallback(frame, user_goal, context)

        # Preserve Tier 1 live bounding boxes when VLM doesn't provide box_2d overlays
        if not vlm_res.boxes and all_boxes:
            vlm_res.boxes = all_boxes
        return vlm_res


def get_vlm_reasoner() -> VLMReasoner:
    """Return singleton instance of VLMReasoner."""
    return VLMReasoner.get_instance()
