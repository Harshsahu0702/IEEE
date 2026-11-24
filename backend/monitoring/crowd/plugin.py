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


class CrowdMonitoringPlugin(MonitoringPlugin):
    """
    Crowd Density and Overcrowding Monitoring Plugin.
    Capabilities:
    - Real-time person counting using YOLOv8n (person class only)
    - Density level classification (low / medium / high)
    - Configurable person threshold trigger
    - Evidence screenshot persistence in evidence/ directory
    - Cooldown mechanism to suppress duplicate alert flooding
    """

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.detector: Optional[PersonDetector] = None
        self.person_threshold: int = 4
        self.density_low_max: int = 2
        self.density_medium_max: int = 5
        self.cooldown_seconds: float = 30.0
        self.conf_threshold: float = 0.22

        self.last_alert_time: float = 0.0
        self.last_frame_result: Optional[FrameResult] = None
        self.last_raw_frame: Optional[np.ndarray] = None
        self.last_annotated_frame: Optional[np.ndarray] = None
        self.pending_events: List[EventCandidate] = []
        self._running: bool = False

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="crowd_monitoring",
            display_name="Crowd Density & Overcrowding Monitor",
            version="1.0.0",
            description="Analyzes live optical streams for person counts, spatial density, and overcrowding alerts.",
            domain="vision",
            default_config={
                "person_threshold": 4,
                "density_low_max": 2,
                "density_medium_max": 5,
                "cooldown_seconds": 30.0,
                "confidence_threshold": 0.22
            }
        )

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self.get_metadata().default_config
        merged = defaults.copy()
        merged.update(config or {})

        # Type validations
        merged["person_threshold"] = int(merged.get("person_threshold", 4))
        merged["density_low_max"] = int(merged.get("density_low_max", 2))
        merged["density_medium_max"] = int(merged.get("density_medium_max", 5))
        merged["cooldown_seconds"] = float(merged.get("cooldown_seconds", 30.0))
        merged["confidence_threshold"] = float(merged.get("confidence_threshold", 0.22))
        return merged

    def initialize(self, config: Dict[str, Any]) -> None:
        self.config = self.validate_config(config)
        self.person_threshold = self.config["person_threshold"]
        self.density_low_max = self.config["density_low_max"]
        self.density_medium_max = self.config["density_medium_max"]
        self.cooldown_seconds = self.config["cooldown_seconds"]
        self.conf_threshold = self.config["confidence_threshold"]

        # Ensure evidence storage path exists
        Path(settings.EVIDENCE_DIR).mkdir(parents=True, exist_ok=True)

        # Lazy-load YOLO detector
        self.detector = PersonDetector.get_instance()
        self.last_alert_time = 0.0
        self.pending_events.clear()
        self._running = True
        logger.info(f"CrowdMonitoringPlugin initialized with threshold={self.person_threshold}")

    def calculate_density_level(self, count: int) -> str:
        """Categorize person count into low, medium, or high density."""
        if count <= self.density_low_max:
            return "low"
        elif count <= self.density_medium_max:
            return "medium"
        else:
            return "high"

    def process_frame(self, frame: np.ndarray) -> Optional[FrameResult]:
        """Processes visual frame, detects persons, and renders annotations."""
        if not self._running or self.detector is None or frame is None:
            return None

        self.last_raw_frame = frame.copy()

        # Run person detection
        detections: List[DetectionBox] = self.detector.detect(
            frame,
            conf_threshold=self.conf_threshold
        )
        person_count = len(detections)
        density_level = self.calculate_density_level(person_count)

        # Annotate frame
        annotated = self.detector.annotate(
            frame=frame,
            detections=detections,
            person_count=person_count,
            density_level=density_level
        )
        self.last_annotated_frame = annotated

        result = FrameResult(
            person_count=person_count,
            density_level=density_level,
            detections=detections,
            metadata={
                "threshold": self.person_threshold,
                "confidence_avg": round(
                    sum(d.confidence for d in detections) / max(person_count, 1), 2
                ) if detections else 0.0
            },
            timestamp=time.time()
        )
        self.last_frame_result = result

        # Check for overcrowding condition
        now = time.time()
        if person_count >= self.person_threshold:
            if (now - self.last_alert_time) >= self.cooldown_seconds:
                self._record_overcrowding_event(person_count, density_level, detections, now)

        return result

    def _record_overcrowding_event(
        self,
        count: int,
        density_level: str,
        detections: List[DetectionBox],
        timestamp: float
    ):
        """Generate an overcrowding alert and save snapshot evidence."""
        self.last_alert_time = timestamp

        evidence_filename = f"crowd_alert_{int(timestamp)}_{count}p.jpg"
        evidence_filepath = Path(settings.EVIDENCE_DIR) / evidence_filename

        # Save annotated evidence frame
        if self.last_annotated_frame is not None:
            cv2.imwrite(str(evidence_filepath), self.last_annotated_frame)
            evidence_url = f"/evidence/{evidence_filename}"
        else:
            evidence_url = None

        confidence = round(
            sum(d.confidence for d in detections) / max(count, 1), 2
        ) if detections else 0.85

        severity = "high" if count >= (self.person_threshold * 1.5) else "medium"

        candidate = EventCandidate(
            event_type="crowd_density_high",
            severity=severity,
            confidence=confidence,
            description=f"Overcrowding alert: {count} persons detected (threshold: {self.person_threshold}, density: {density_level}).",
            details={
                "person_count": count,
                "threshold": self.person_threshold,
                "density_level": density_level,
                "detections_count": len(detections)
            },
            evidence_path=evidence_url,
            timestamp=timestamp
        )
        self.pending_events.append(candidate)
        logger.warning(f"Generated EventCandidate: {candidate.description}")

    def process_sensor_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crowd plugin does not process sensor telemetry."""
        return None

    def generate_events(self) -> List[EventCandidate]:
        """Drain and return newly triggered candidate events."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events

    def stop(self) -> None:
        self._running = False
        self.pending_events.clear()
        self.last_frame_result = None
        self.last_raw_frame = None
        self.last_annotated_frame = None
        logger.info("CrowdMonitoringPlugin stopped.")
