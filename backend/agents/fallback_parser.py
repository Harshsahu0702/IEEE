import re
from typing import Dict, Any, Tuple, Optional
from backend.monitoring.registry import list_plugins


class FallbackParser:
    """
    Deterministic keyword & regex parser.
    Features:
    - 100% offline, zero API dependency.
    - English + Hinglish understanding.
    - Extracts numbers (limits, thresholds, duration).
    - Clear unsupported module explanation if requested domain does not exist.
    """

    CROWD_KEYWORDS = [
        "crowd", "people", "person", "density", "overcrowd", "gathering",
        "log", "bhid", "aadmi", "camera", "webcam", "video", "optical"
    ]

    ENV_KEYWORDS = [
        "gas", "smoke", "fire", "heat", "temp", "temperature", "humidity",
        "dht", "mq2", "mq-2", "air", "aqi", "leak", "hawa", "dhua"
    ]

    SECURITY_KEYWORDS = [
        "security", "intrusion", "restricted", "zone", "perimeter", "trespass",
        "ghusbaith", "unauthorized", "surveillance", "boundary"
    ]

    THREAT_KEYWORDS = [
        "threat", "weapon", "knife", "chaku", "gun", "bandook", "pistol",
        "violence", "fight", "fighting", "maar", "marte", "assault", "attack",
        "danger", "khatra", "alarm", "bat", "hitting", "beating"
    ]


    STOP_KEYWORDS = [
        "stop", "halt", "cancel", "terminate", "kill", "roko", "band karo",
        "pause", "off", "khatam"
    ]

    STATUS_KEYWORDS = [
        "status", "health", "state", "kya chal raha hai", "batao",
        "how are devices", "overview", "diagnostics"
    ]

    SWITCH_KEYWORDS = [
        "switch", "change", "badlo", "replace", "instead of"
    ]

    def parse(self, command: str) -> Dict[str, Any]:
        """
        Parses command into structured intent, module, source, and rules.
        """
        text = command.lower().strip()
        available_modules = [p.name for p in list_plugins()]

        # Helper for word-boundary keyword matching (prevents 'air' matching 'airplane')
        def match_kw(kw_list):
            for kw in kw_list:
                if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
                    return True
            return False

        # 1. Stop Monitoring
        if match_kw(self.STOP_KEYWORDS) and not match_kw(self.SWITCH_KEYWORDS):
            return {
                "intent": "stop_monitoring",
                "domain": "system",
                "modules": [],
                "source": "all",
                "rules": {},
                "duration_minutes": None,
                "confidence": 0.95,
                "what_i_understood": "Stop active monitoring tasks.",
                "why": "Command contains explicit stop/halt directive."
            }

        # 2. Get Status
        if match_kw(self.STATUS_KEYWORDS) and not (match_kw(self.CROWD_KEYWORDS) or match_kw(self.ENV_KEYWORDS)):
            return {
                "intent": "get_status",
                "domain": "system",
                "modules": [],
                "source": "all",
                "rules": {},
                "duration_minutes": None,
                "confidence": 0.95,
                "what_i_understood": "Retrieve system health and sensor diagnostics.",
                "why": "Command requests status/health check."
            }

        # 3. Switch Monitoring
        is_switch = match_kw(self.SWITCH_KEYWORDS)

        # 4. Extract Numbers & Duration
        duration_minutes = self._extract_duration(text)
        person_threshold = self._extract_person_threshold(text)
        temp_threshold = self._extract_temp_threshold(text)
        gas_threshold = self._extract_gas_threshold(text)
        source = self._extract_source(text)

        # 5. Domain Identification using strict word boundaries
        has_crowd = match_kw(self.CROWD_KEYWORDS)
        has_env = match_kw(self.ENV_KEYWORDS)
        has_security = match_kw(self.SECURITY_KEYWORDS)
        has_threat = match_kw(self.THREAT_KEYWORDS)

        # 6. Check for unsupported domains
        unsupported_keywords = ["airplane", "flight", "car speed", "traffic plate", "speed gun", "face", "drone"]
        for unk in unsupported_keywords:
            if unk in text and not has_crowd and not has_env and not has_security and not has_threat:
                return {
                    "intent": "start_monitoring",
                    "domain": "unsupported",
                    "modules": [],
                    "source": "none",
                    "rules": {},
                    "confidence": 0.3,
                    "what_i_understood": f"Request for unsupported capability '{unk}'.",
                    "why": f"Module '{unk}' is unsupported. Available modules in registry: {', '.join(available_modules)}."
                }

        # Intent resolution
        intent = "switch_monitoring" if is_switch else "start_monitoring"

        # Threat Monitoring takes precedence if threat/weapon keywords are present
        if has_threat:
            return {
                "intent": intent,
                "domain": "vision",
                "modules": ["universal_vlm_monitor"],
                "source": source or "webcam_0",
                "rules": {
                    "cooldown_seconds": 15.0,
                    "confidence_threshold": 0.20,
                    "enable_hardware_alarm": True
                },
                "duration_minutes": duration_minutes,
                "confidence": 0.95,
                "what_i_understood": f"{'Switch to' if is_switch else 'Start'} physical threat, weapon, or hazard monitoring via Universal AI Monitor.",
                "why": "Detected keywords for hazard, violence, weapon, or brandished threat."
            }

        # If switching "from X to Y", identify destination module Y
        if is_switch:
            if re.search(r"(?:to|into|par|me|badlo)\s+(?:the\s+)?(?:environment|gas|temp|sensor|station)", text):
                has_env = True
                has_crowd = False
                has_security = False
            elif re.search(r"(?:to|into|par|me|badlo)\s+(?:the\s+)?(?:security|zone|perimeter|intrusion)", text):
                has_security = True
                has_crowd = False
                has_env = False
            elif re.search(r"(?:to|into|par|me|badlo)\s+(?:the\s+)?(?:crowd|camera|webcam|people)", text):
                has_crowd = True
                has_env = False
                has_security = False

        if has_security:
            return {
                "intent": intent,
                "domain": "vision",
                "modules": ["universal_vlm_monitor"],
                "source": source or "webcam_0",
                "rules": {
                    "cooldown_seconds": 20.0,
                    "confidence_threshold": 0.35
                },
                "duration_minutes": duration_minutes,
                "confidence": 0.92,
                "what_i_understood": f"{'Switch to' if is_switch else 'Start'} perimeter security and intrusion monitoring via Universal AI Monitor.",
                "why": "Detected keywords matching security monitoring, restricted zone, or intrusion surveillance."
            }

        if has_crowd and not has_env:
            threshold = person_threshold or 4
            return {
                "intent": intent,
                "domain": "vision",
                "modules": ["universal_vlm_monitor"],
                "source": source or "webcam_0",
                "rules": {
                    "person_threshold": threshold,
                    "cooldown_seconds": 30.0,
                    "confidence_threshold": 0.35
                },
                "duration_minutes": duration_minutes,
                "confidence": 0.90,
                "what_i_understood": f"{'Switch to' if is_switch else 'Start'} crowd monitoring with person threshold {threshold} via Universal AI Monitor.",
                "why": "Detected keywords matching visual crowd density and spatial occupancy."
            }

        if has_env and not has_crowd:
            temp_lim = temp_threshold or 32.0
            gas_lim = gas_threshold or 400.0
            return {
                "intent": intent,
                "domain": "iot",
                "modules": ["environment_monitoring"],
                "source": source or "env-sensor-01",
                "rules": {
                    "temp_threshold": temp_lim,
                    "gas_threshold": gas_lim,
                    "humidity_max": 75.0,
                    "cooldown_seconds": 30.0
                },
                "duration_minutes": duration_minutes,
                "confidence": 0.90,
                "what_i_understood": f"{'Switch to' if is_switch else 'Start'} environmental safety monitoring (gas limit: {gas_lim} ppm, temp limit: {temp_lim}°C).",
                "why": "Detected telemetry indicators for environmental gas or temperature monitoring."
            }

        # Both or general multimodal
        if has_crowd and has_env:
            return {
                "intent": intent,
                "domain": "multimodal",
                "modules": ["universal_vlm_monitor", "environment_monitoring"],
                "source": "webcam_0",
                "rules": {
                    "person_threshold": person_threshold or 4,
                    "temp_threshold": temp_threshold or 32.0,
                    "gas_threshold": gas_threshold or 400.0
                },
                "duration_minutes": duration_minutes,
                "confidence": 0.85,
                "what_i_understood": f"{'Switch to' if is_switch else 'Start'} multimodal visual and environmental monitoring via Universal AI Monitor.",
                "why": "Command contains references to both optical vision and ambient environmental sensors."
            }

        # Universal fallback for any custom monitoring goal (e.g. "exam cheating", "home accidents", "fall detection")
        return {
            "intent": "start_monitoring",
            "domain": "vision",
            "modules": ["universal_vlm_monitor"],
            "source": "webcam_0",
            "rules": {},
            "duration_minutes": duration_minutes,
            "confidence": 0.85,
            "what_i_understood": f"Monitor the scene for: '{command.strip()}'.",
            "why": "Routing to Universal AI Vision-Language Monitor with dynamic context-adaptive reasoning."
        }

    def _extract_duration(self, text: str) -> Optional[int]:
        # "for 2 hours", "for 1 hour"
        m_hr = re.search(r"(\d+)\s*(?:hour|hours|hr|hrs|ghante)", text)
        if m_hr:
            return int(m_hr.group(1)) * 60

        # "for 30 minutes", "for 45 mins"
        m_min = re.search(r"(\d+)\s*(?:minute|minutes|min|mins|minute)", text)
        if m_min:
            return int(m_min.group(1))
        return None

    def _extract_person_threshold(self, text: str) -> Optional[int]:
        # "limit 30 people", "limit of 5", "threshold 10"
        m = re.search(r"(?:limit|threshold|max|more than|se jyada)\s*(?:of|is)?\s*(\d+)", text)
        if m:
            return int(m.group(1))
        m2 = re.search(r"(\d+)\s*(?:people|persons|log|aadmi)", text)
        if m2:
            return int(m2.group(1))
        return None

    def _extract_temp_threshold(self, text: str) -> Optional[float]:
        m = re.search(r"(?:temp|temperature|garmi)\s*(?:limit|threshold|above|se upar)?\s*(\d+(?:\.\d+)?)", text)
        if m:
            return float(m.group(1))
        return None

    def _extract_gas_threshold(self, text: str) -> Optional[float]:
        m = re.search(r"(?:gas|smoke|dhua)\s*(?:limit|threshold|above|ppm)?\s*(\d+(?:\.\d+)?)", text)
        if m:
            return float(m.group(1))
        return None

    def _extract_source(self, text: str) -> Optional[str]:
        if "camera 1" in text or "cam 1" in text or "camera 0" in text:
            return "webcam_0"
        if "sensor 1" in text or "station 1" in text:
            return "env-sensor-01"
        return None


fallback_parser = FallbackParser()
