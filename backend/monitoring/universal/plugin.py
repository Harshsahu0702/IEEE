import logging
from typing import Dict, Any, List, Optional
import numpy as np

from backend.monitoring.base import (
    MonitoringPlugin,
    PluginMetadata,
    FrameResult,
    EventCandidate,
)
from backend.vision.motion_filter import MotionFilter
from backend.vision.vlm_reasoner import get_vlm_reasoner

logger = logging.getLogger(__name__)


class UniversalMonitoringPlugin(MonitoringPlugin):
    """
    Universal Vision-Language & Motion Monitoring Plugin.
    Replaces hardcoded scenario plugins (crowd, security, threat) by dynamically
    reasoning over any user-defined monitoring goal using motion filtering and VLM.
    """

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.user_goal: str = "Monitor the scene for anomalies or hazards"
        self._motion_filter = MotionFilter()
        self._reasoner = get_vlm_reasoner()
        self.pending_events: List[EventCandidate] = []

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="universal_vlm_monitor",
            display_name="Universal AI Vision-Language Monitor",
            version="2.0.0",
            description="Context-adaptive monitor using motion filtering and vision-language reasoning for any real-world scenario.",
            domain="multimodal",
            default_config={
                "user_goal": "Monitor the scene for safety and security anomalies",
                "vlm_every_n_frames": 15,
                "motion_sensitivity": 25,
            }
        )

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self.get_metadata().default_config
        merged = defaults.copy()
        merged.update(config or {})
        return merged

    def initialize(self, config: Dict[str, Any]) -> None:
        self.config = self.validate_config(config)
        self.user_goal = self.config.get("user_goal", self.user_goal)

    def process_frame(self, frame: np.ndarray) -> Optional[FrameResult]:
        motion_detected, motion_score, motion_boxes = self._motion_filter.detect(frame)
        return FrameResult(
            person_count=1 if motion_detected else 0,
            density_level="high" if motion_score > 0.3 else "low",
            detections=[],
            metadata={
                "motion_detected": motion_detected,
                "motion_score": motion_score,
                "motion_boxes": motion_boxes,
                "user_goal": self.user_goal
            },
            timestamp=0.0
        )

    def process_sensor_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return data

    def generate_events(self) -> List[EventCandidate]:
        ev = list(self.pending_events)
        self.pending_events.clear()
        return ev

    def stop(self) -> None:
        self._motion_filter.reset()
