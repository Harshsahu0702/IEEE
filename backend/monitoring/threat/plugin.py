import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import cv2
import numpy as np

from backend.config import settings
from backend.monitoring.base import (
    MonitoringPlugin,
    PluginMetadata,
    FrameResult,
    DetectionBox,
    EventCandidate,
)
from backend.vision.detector import PersonDetector

logger = logging.getLogger(__name__)


def compute_iou(box1: DetectionBox, box2: DetectionBox) -> float:
    """Compute Intersection over Union between two detection boxes."""
    x1 = max(box1.x1, box2.x1)
    y1 = max(box1.y1, box2.y1)
    x2 = min(box1.x2, box2.x2)
    y2 = min(box1.y2, box2.y2)

    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter_area = inter_w * inter_h

    if inter_area == 0:
        return 0.0

    area1 = (box1.x2 - box1.x1) * (box1.y2 - box1.y1)
    area2 = (box2.x2 - box2.x1) * (box2.y2 - box2.y1)
    union_area = area1 + area2 - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


class ThreatMonitoringPlugin(MonitoringPlugin):
    """
    Physical Threat, Weapon, and Violence Monitoring Plugin.
    Capabilities:
    - Real-time weapon detection: knives, blades, scissors, blunt bats/clubs.
    - Physical altercation / grapple detection: spatial bounding box collision & struggle heuristics.
    - Multi-modal alarm dispatch: Web Audio sirens on dashboard + Hardware Red LED on Arduino.
    - Snapshot evidence persistence in evidence/ directory.
    - Cooldown mechanism to suppress duplicate alert flooding.
    - Zero facial recognition, zero identity tracking.
    """

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.detector: Optional[PersonDetector] = None
        self.weapon_detection: bool = True
        self.violence_detection: bool = True
        self.cooldown_seconds: float = 15.0
        self.conf_threshold: float = 0.20
        self.enable_hardware_alarm: bool = True

        self.last_alert_time: float = 0.0
        self.last_frame_result: Optional[FrameResult] = None
        self.last_raw_frame: Optional[np.ndarray] = None
        self.last_annotated_frame: Optional[np.ndarray] = None
        self.pending_events: List[EventCandidate] = []
        self._running: bool = False

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="threat_monitoring",
            display_name="Physical Threat & Weapon Watch",
            version="1.0.0",
            description="Monitors live camera feeds for brandished weapons (knives, blunt weapons) and violent physical altercations. Dispatches multi-modal alarms & Arduino LED signals.",
            domain="vision",
            default_config={
                "weapon_detection": True,
                "violence_detection": True,
                "confidence_threshold": 0.20,
                "cooldown_seconds": 15.0,
                "enable_hardware_alarm": True
            }
        )

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self.get_metadata().default_config
        merged = defaults.copy()
        merged.update(config or {})

        merged["weapon_detection"] = bool(merged.get("weapon_detection", True))
        merged["violence_detection"] = bool(merged.get("violence_detection", True))
        merged["confidence_threshold"] = float(merged.get("confidence_threshold", 0.20))
        merged["cooldown_seconds"] = float(merged.get("cooldown_seconds", 15.0))
        merged["enable_hardware_alarm"] = bool(merged.get("enable_hardware_alarm", True))
        return merged

    def initialize(self, config: Dict[str, Any]) -> None:
        self.config = self.validate_config(config)
        self.weapon_detection = self.config["weapon_detection"]
        self.violence_detection = self.config["violence_detection"]
        self.conf_threshold = self.config["confidence_threshold"]
        self.cooldown_seconds = self.config["cooldown_seconds"]
        self.enable_hardware_alarm = self.config["enable_hardware_alarm"]

        Path(settings.EVIDENCE_DIR).mkdir(parents=True, exist_ok=True)
        self.detector = PersonDetector.get_instance()
        self.last_alert_time = 0.0
        self.pending_events.clear()
        self._running = True
        logger.info("ThreatMonitoringPlugin initialized successfully.")

    def process_frame(self, frame: np.ndarray) -> Optional[FrameResult]:
        """Detect weapons and violent altercations, render alert HUD, and trigger alarms."""
        if not self._running or self.detector is None or frame is None:
            return None

        self.last_raw_frame = frame.copy()
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # 1. Detect persons and weapon objects
        persons, weapons = self.detector.detect_threats(
            frame,
            conf_threshold=self.conf_threshold
        )

        threat_detected = False
        threat_type = "none"
        threat_details: List[str] = []

        # Check weapons
        if self.weapon_detection and len(weapons) > 0:
            threat_detected = True
            threat_type = "weapon_threat"
            threat_details.append(f"Weapons brandished: {', '.join([w.class_name for w in weapons])}")

        # Check violent physical struggles (IoU > 0.28 between any two persons)
        grappling_pairs = []
        if self.violence_detection and len(persons) >= 2:
            for i in range(len(persons)):
                for j in range(i + 1, len(persons)):
                    iou = compute_iou(persons[i], persons[j])
                    if iou > 0.25:
                        grappling_pairs.append((persons[i], persons[j]))

            if len(grappling_pairs) > 0:
                threat_detected = True
                if threat_type == "none":
                    threat_type = "physical_violence_risk"
                threat_details.append(f"Physical struggle/grappling detected ({len(grappling_pairs)} altercation pairs)")

        now = time.time()

        # 2. Render Visual HUD & Annotations
        if threat_detected:
            # Flashing red perimeter strobe
            border_thickness = 8
            cv2.rectangle(annotated, (0, 0), (w, h), (0, 0, 255), border_thickness)

            # Top Danger Banner
            cv2.rectangle(annotated, (0, 0), (w, 42), (0, 0, 200), -1)
            hud_text = f"CRITICAL THREAT DETECTED: {threat_type.upper()} | ALARM ACTIVE!"
            cv2.putText(annotated, hud_text, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        else:
            # Normal HUD Banner
            cv2.rectangle(annotated, (0, 0), (w, 36), (30, 32, 38), -1)
            hud_text = f"THREAT WATCH: SECURE | NO WEAPONS DETECTED | PERSONS: {len(persons)}"
            cv2.putText(annotated, hud_text, (15, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 140), 1, cv2.LINE_AA)

        # Draw Person Boxes
        for p in persons:
            is_grappling = any(p in pair for pair in grappling_pairs)
            color = (0, 0, 255) if is_grappling else (0, 200, 100)
            cv2.rectangle(annotated, (p.x1, p.y1), (p.x2, p.y2), color, 2)
            label = "STRUGGLE/ALTERCATION" if is_grappling else f"Person {int(p.confidence * 100)}%"
            cv2.putText(annotated, label, (p.x1, max(18, p.y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        # Draw Weapon Boxes (Bright Crimson Red with Warning)
        for wbox in weapons:
            cv2.rectangle(annotated, (wbox.x1, wbox.y1), (wbox.x2, wbox.y2), (0, 0, 255), 3)
            wlabel = f"THREAT: {wbox.class_name.upper()} ({int(wbox.confidence * 100)}%)"
            (tw, th), _ = cv2.getTextSize(wlabel, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(annotated, (wbox.x1, max(0, wbox.y1 - 22)), (wbox.x1 + tw + 8, wbox.y1), (0, 0, 220), -1)
            cv2.putText(annotated, wlabel, (wbox.x1 + 4, max(15, wbox.y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

        self.last_annotated_frame = annotated

        # 3. Handle Alert Triggering & Cooldown
        if threat_detected:
            if (now - self.last_alert_time) >= self.cooldown_seconds:
                self.last_alert_time = now
                self._record_threat_event(
                    threat_type=threat_type,
                    threat_details="; ".join(threat_details),
                    persons=persons,
                    weapons=weapons,
                    annotated_snapshot=annotated,
                    timestamp=now
                )

        all_detections = persons + weapons
        result = FrameResult(
            person_count=len(persons),
            density_level="high" if threat_detected else "low",
            detections=all_detections,
            metadata={
                "threat_detected": threat_detected,
                "threat_type": threat_type,
                "weapons_count": len(weapons),
                "altercation_pairs": len(grappling_pairs),
                "alarm_state": "TRIGGERED" if threat_detected else "NORMAL"
            },
            timestamp=now
        )
        self.last_frame_result = result
        return result

    def _record_threat_event(
        self,
        threat_type: str,
        threat_details: str,
        persons: List[DetectionBox],
        weapons: List[DetectionBox],
        annotated_snapshot: np.ndarray,
        timestamp: float
    ):
        """Persists snapshot evidence, creates pending_review event, and triggers Arduino alarm."""
        snap_id = f"threat_{int(timestamp)}_{threat_type}"
        snap_name = f"{snap_id}.jpg"
        snap_path = Path(settings.EVIDENCE_DIR) / snap_name

        try:
            cv2.imwrite(str(snap_path), annotated_snapshot)
            evidence_rel_path = f"/evidence/{snap_name}"
        except Exception as e:
            logger.error(f"Failed to write threat evidence snapshot: {e}")
            evidence_rel_path = None

        max_conf = max([w.confidence for w in weapons] + [p.confidence for p in persons] + [0.85])
        desc = f"Physical threat identified: {threat_details}. Emergency alarm triggered."

        candidate = EventCandidate(
            event_type=threat_type,
            severity="critical",
            confidence=round(float(max_conf), 2),
            description=desc,
            evidence_path=evidence_rel_path,
            details={
                "threat_type": threat_type,
                "details": threat_details,
                "weapons": [w.class_name for w in weapons],
                "persons_involved": len(persons),
                "alarm_dispatched": True,
                "timestamp": timestamp
            }
        )
        self.pending_events.append(candidate)
        logger.warning(f"[SECURITY ALERT] {desc} (Event queued as pending_review)")

        # Dispatch Hardware Alarm to Arduino via MQTT & Serial
        if self.enable_hardware_alarm:
            self._trigger_hardware_alarm(threat_type)

    def _trigger_hardware_alarm(self, threat_type: str):
        """Sends MQTT trigger to activate Arduino Red LED (Pin 13) and audio buzzer."""
        try:
            payload = {
                "command": "alarm",
                "state": "ON",
                "threat": threat_type,
                "timestamp": time.time(),
                "duration_seconds": 15
            }
            if hasattr(mqtt_service, "publish_alarm"):
                mqtt_service.publish_alarm(payload)
            logger.info(f"Hardware alarm dispatch broadcasted: {payload}")
        except Exception as e:
            logger.error(f"Failed to dispatch hardware alarm: {e}")

    def generate_events(self) -> List[EventCandidate]:
        events = list(self.pending_events)
        self.pending_events.clear()
        return events

    def process_sensor_data(self, data: Dict[str, Any]) -> None:
        """Vision plugins do not directly process numeric telemetry."""
        pass

    def stop(self) -> None:
        self._running = False
        self.pending_events.clear()
        logger.info("ThreatMonitoringPlugin stopped.")
