import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
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


class SecurityMonitoringPlugin(MonitoringPlugin):
    """
    Restricted-Area Intrusion Monitoring Plugin.
    Capabilities:
    - User-defined restricted zones (normalized polygon or rectangle coordinates 0.0 - 1.0)
    - Person detection via YOLOv8n (person class 0 only, strictly zero identity tracking)
    - Point-in-polygon spatial testing using ground contact (feet) and centroid
    - Visual zone overlays (green when secure, red highlight on breach)
    - Snapshot evidence persistence in evidence/ directory
    - Zone-specific cooldown suppression to prevent duplicate alert flooding
    """

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.detector: Optional[PersonDetector] = None
        self.zones: List[Dict[str, Any]] = []
        self.cooldown_seconds: float = 20.0
        self.conf_threshold: float = 0.35

        self.last_alert_times: Dict[str, float] = {}
        self.last_frame_result: Optional[FrameResult] = None
        self.last_raw_frame: Optional[np.ndarray] = None
        self.last_annotated_frame: Optional[np.ndarray] = None
        self.pending_events: List[EventCandidate] = []
        self._running: bool = False

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="security_monitoring",
            display_name="Restricted Area Intrusion Monitor",
            version="1.0.0",
            description="Monitors designated restricted zones for unauthorized human intrusion with spatial polygon validation and snapshot evidence.",
            domain="vision",
            default_config={
                "zones": [
                    {
                        "name": "Restricted Zone A",
                        "polygon": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
                    }
                ],
                "cooldown_seconds": 20.0,
                "confidence_threshold": 0.35
            }
        )

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self.get_metadata().default_config
        merged = defaults.copy()
        merged.update(config or {})

        # Validate zones
        raw_zones = merged.get("zones", [])
        validated_zones = []

        if isinstance(raw_zones, list):
            for i, z in enumerate(raw_zones):
                if not isinstance(z, dict):
                    continue
                name = z.get("name", f"Zone {i+1}")
                polygon = z.get("polygon")
                rect = z.get("rect")

                # If normalized rect is provided [x1, y1, x2, y2], expand to polygon
                if rect and isinstance(rect, (list, tuple)) and len(rect) == 4:
                    x1, y1, x2, y2 = rect
                    polygon = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

                if polygon and isinstance(polygon, list) and len(polygon) >= 3:
                    # Sanitize points into [0.0, 1.0] float pairs
                    clean_poly = []
                    for pt in polygon:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            clean_poly.append([
                                max(0.0, min(1.0, float(pt[0]))),
                                max(0.0, min(1.0, float(pt[1])))
                            ])
                    if len(clean_poly) >= 3:
                        validated_zones.append({
                            "name": name,
                            "polygon": clean_poly
                        })

        if not validated_zones:
            validated_zones = defaults["zones"]

        merged["zones"] = validated_zones
        merged["cooldown_seconds"] = float(merged.get("cooldown_seconds", 20.0))
        merged["confidence_threshold"] = float(merged.get("confidence_threshold", 0.35))
        return merged

    def initialize(self, config: Dict[str, Any]) -> None:
        self.config = self.validate_config(config)
        self.zones = self.config["zones"]
        self.cooldown_seconds = self.config["cooldown_seconds"]
        self.conf_threshold = self.config["confidence_threshold"]

        # Ensure evidence directory exists
        Path(settings.EVIDENCE_DIR).mkdir(parents=True, exist_ok=True)

        self.detector = PersonDetector.get_instance()
        self.last_alert_times.clear()
        self.pending_events.clear()
        self._running = True
        logger.info(f"SecurityMonitoringPlugin initialized with {len(self.zones)} restricted zone(s).")

    def _is_point_in_polygon(self, pt: tuple, polygon_pts: np.ndarray) -> bool:
        """Point-in-polygon test using OpenCV."""
        # result >= 0 means inside or on edge
        return cv2.pointPolygonTest(polygon_pts, pt, False) >= 0

    def process_frame(self, frame: np.ndarray) -> FrameResult:
        if not self._running or frame is None:
            return FrameResult()

        h, w = frame.shape[:2]
        self.last_raw_frame = frame.copy()

        # 1. Detect persons (person class 0 only, no facial embeddings)
        detections: List[DetectionBox] = self.detector.detect(
            frame,
            conf_threshold=self.conf_threshold
        )

        annotated = frame.copy()
        intrusion_detected = False
        breached_zones: List[str] = []
        intruder_detections: List[DetectionBox] = []

        now = time.time()

        # 2. Check each restricted zone
        for zone in self.zones:
            zone_name = zone["name"]
            poly_norm = zone["polygon"]

            # Convert normalized polygon points to frame pixels
            poly_pixels = np.array([
                [int(p[0] * w), int(p[1] * h)] for p in poly_norm
            ], dtype=np.int32)

            zone_intruders = []

            for det in detections:
                # Bottom-center represents feet/ground contact
                feet_pt = ((det.x1 + det.x2) / 2.0, float(det.y2))
                # Centroid represents body core
                center_pt = ((det.x1 + det.x2) / 2.0, (det.y1 + det.y2) / 2.0)

                if self._is_point_in_polygon(feet_pt, poly_pixels) or self._is_point_in_polygon(center_pt, poly_pixels):
                    zone_intruders.append(det)

            zone_breached = len(zone_intruders) > 0
            if zone_breached:
                intrusion_detected = True
                breached_zones.append(zone_name)
                intruder_detections.extend(zone_intruders)

            # Draw zone overlay
            overlay = annotated.copy()
            fill_color = (0, 0, 220) if zone_breached else (0, 200, 100)
            line_color = (0, 0, 255) if zone_breached else (0, 255, 120)

            cv2.fillPoly(overlay, [poly_pixels], fill_color)
            alpha = 0.25 if not zone_breached else 0.40
            cv2.addWeighted(overlay, alpha, annotated, 1 - alpha, 0, annotated)
            cv2.polylines(annotated, [poly_pixels], isClosed=True, color=line_color, thickness=2)

            # Label zone
            label_x = int(poly_norm[0][0] * w)
            label_y = max(20, int(poly_norm[0][1] * h) - 8)
            status_text = f"RESTRICTED: {zone_name} {'[BREACH!]' if zone_breached else '[SECURE]'}"
            cv2.putText(annotated, status_text, (label_x, label_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, line_color, 2)

            # Check alert cooldown for this zone
            if zone_breached:
                last_time = self.last_alert_times.get(zone_name, 0.0)
                if (now - last_time) >= self.cooldown_seconds:
                    self.last_alert_times[zone_name] = now
                    self._record_intrusion_event(
                        zone_name=zone_name,
                        intruders=zone_intruders,
                        total_detections=len(detections),
                        annotated_snapshot=annotated,
                        timestamp=now
                    )

        # 3. Draw bounding boxes for persons
        for det in detections:
            is_intruder = det in intruder_detections
            box_color = (0, 0, 255) if is_intruder else (255, 180, 0)
            tag = "INTRUDER" if is_intruder else "Person"

            cv2.rectangle(annotated, (det.x1, det.y1), (det.x2, det.y2), box_color, 2)
            cv2.putText(
                annotated,
                f"{tag} ({det.confidence:.2f})",
                (det.x1, max(15, det.y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                box_color,
                1
            )

        # Top HUD banner
        hud_bg = (0, 0, 180) if intrusion_detected else (40, 40, 40)
        cv2.rectangle(annotated, (0, 0), (w, 36), hud_bg, -1)
        hud_text = f"ZONE MONITOR: {'BREACH DETECTED!' if intrusion_detected else 'ALL ZONES SECURE'} | PERSONS: {len(detections)}"
        cv2.putText(annotated, hud_text, (15, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        self.last_annotated_frame = annotated

        result = FrameResult(
            person_count=len(detections),
            density_level="high" if intrusion_detected else "low",
            detections=detections,
            metadata={
                "intrusion_detected": intrusion_detected,
                "breached_zones": breached_zones,
                "intruder_count": len(intruder_detections),
                "zones_monitored": len(self.zones)
            },
            timestamp=now
        )
        self.last_frame_result = result
        return result

    def _record_intrusion_event(
        self,
        zone_name: str,
        intruders: List[DetectionBox],
        total_detections: int,
        annotated_snapshot: np.ndarray,
        timestamp: float
    ):
        """Generates a security intrusion alert and saves snapshot evidence."""
        filename = f"security_alert_{int(timestamp)}_{zone_name.replace(' ', '_')}.jpg"
        filepath = Path(settings.EVIDENCE_DIR) / filename

        cv2.imwrite(str(filepath), annotated_snapshot)
        evidence_url = f"/evidence/{filename}"

        max_conf = max([d.confidence for d in intruders], default=0.90)

        candidate = EventCandidate(
            event_type="restricted_zone_intrusion",
            severity="critical",
            confidence=round(float(max_conf), 2),
            description=f"Security Alert: Unauthorized intrusion in '{zone_name}' ({len(intruders)} intruder(s) detected).",
            details={
                "zone_name": zone_name,
                "intruders_count": len(intruders),
                "total_persons": total_detections,
                "cooldown_seconds": self.cooldown_seconds
            },
            evidence_path=evidence_url,
            timestamp=timestamp
        )
        self.pending_events.append(candidate)
        logger.warning(f"Security Alert: Intrusion detected in {zone_name}! Event queued (pending_review).")

    def process_sensor_data(self, sensor_data: Dict[str, Any]) -> None:
        """Optional PIR correlation."""
        pass

    def generate_events(self) -> List[EventCandidate]:
        events = list(self.pending_events)
        self.pending_events.clear()
        return events

    def stop(self) -> None:
        self._running = False
        self.pending_events.clear()
        logger.info("SecurityMonitoringPlugin stopped.")
