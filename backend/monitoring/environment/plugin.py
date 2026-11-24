import time
import logging
from typing import Dict, Any, List, Optional
import numpy as np

from backend.monitoring.base import (
    MonitoringPlugin,
    PluginMetadata,
    FrameResult,
    EventCandidate,
)

logger = logging.getLogger(__name__)


class EnvironmentMonitoringPlugin(MonitoringPlugin):
    """
    Environmental Telemetry Monitoring Plugin.
    Capabilities:
    - Analyzes DHT22 (temp/humidity), MQ-2 (gas level), and PIR (motion)
    - Threshold rules for gas leak risk, critical temperatures, and abnormal humidity
    - Per-metric cooldown suppression
    - Strictly generates 'pending_review' events
    """

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.temp_threshold: float = 32.0       # Celsius
        self.humidity_max: float = 75.0         # %
        self.humidity_min: float = 20.0         # %
        self.gas_threshold: float = 400.0       # ppm (MQ-2)
        self.motion_alert: bool = False
        self.cooldown_seconds: float = 30.0

        self.last_alert_times: Dict[str, float] = {}
        self.last_sensor_data: Dict[str, Any] = {}
        self.pending_events: List[EventCandidate] = []
        self._running: bool = False

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="environment_monitoring",
            display_name="Environmental & Gas Safety Monitor",
            version="1.0.0",
            description="Evaluates ambient telemetry for gas leaks, temperature spikes, and environmental hazards.",
            domain="iot",
            default_config={
                "temp_threshold": 32.0,
                "humidity_max": 75.0,
                "humidity_min": 20.0,
                "gas_threshold": 400.0,
                "motion_alert": False,
                "cooldown_seconds": 30.0
            }
        )

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self.get_metadata().default_config
        merged = defaults.copy()
        merged.update(config or {})

        merged["temp_threshold"] = float(merged.get("temp_threshold", 32.0))
        merged["humidity_max"] = float(merged.get("humidity_max", 75.0))
        merged["humidity_min"] = float(merged.get("humidity_min", 20.0))
        merged["gas_threshold"] = float(merged.get("gas_threshold", 400.0))
        merged["motion_alert"] = bool(merged.get("motion_alert", False))
        merged["cooldown_seconds"] = float(merged.get("cooldown_seconds", 30.0))
        return merged

    def initialize(self, config: Dict[str, Any]) -> None:
        self.config = self.validate_config(config)
        self.temp_threshold = self.config["temp_threshold"]
        self.humidity_max = self.config["humidity_max"]
        self.humidity_min = self.config["humidity_min"]
        self.gas_threshold = self.config["gas_threshold"]
        self.motion_alert = self.config["motion_alert"]
        self.cooldown_seconds = self.config["cooldown_seconds"]

        self.last_alert_times.clear()
        self.last_sensor_data.clear()
        self.pending_events.clear()
        self._running = True
        logger.info(f"EnvironmentMonitoringPlugin initialized with gas_limit={self.gas_threshold}, temp_limit={self.temp_threshold}")

    def process_frame(self, frame: np.ndarray) -> Optional[FrameResult]:
        """Environment plugin does not consume video frames directly."""
        return None

    def process_sensor_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Processes telemetry payload and checks thresholds against cooldowns."""
        if not self._running or not data:
            return None

        self.last_sensor_data = data.copy()
        now = time.time()
        device_id = data.get("device_id", "unknown-device")

        # 1. Gas Leak Check (MQ-2) - CRITICAL
        gas = data.get("gas_level")
        if gas is not None and gas >= self.gas_threshold:
            if self._can_alert("gas_leak_risk", now):
                self._record_alert(
                    event_type="gas_leak_risk",
                    severity="critical",
                    confidence=0.95,
                    description=f"Critical gas concentration detected ({gas} ppm >= {self.gas_threshold} ppm) on device {device_id}.",
                    details={"gas_level": gas, "threshold": self.gas_threshold, "device_id": device_id},
                    timestamp=now
                )

        # 2. Temperature Spike Check (DHT22) - HIGH
        temp = data.get("temperature")
        if temp is not None and temp >= self.temp_threshold:
            if self._can_alert("temperature_critical", now):
                self._record_alert(
                    event_type="temperature_critical",
                    severity="high",
                    confidence=0.90,
                    description=f"Excessive ambient temperature ({temp}°C >= {self.temp_threshold}°C) on device {device_id}.",
                    details={"temperature": temp, "threshold": self.temp_threshold, "device_id": device_id},
                    timestamp=now
                )

        # 3. Humidity Out of Bounds Check (DHT22) - MEDIUM
        hum = data.get("humidity")
        if hum is not None and (hum >= self.humidity_max or hum <= self.humidity_min):
            if self._can_alert("humidity_abnormal", now):
                self._record_alert(
                    event_type="humidity_abnormal",
                    severity="medium",
                    confidence=0.85,
                    description=f"Abnormal humidity reading ({hum}% outside range {self.humidity_min}% - {self.humidity_max}%) on device {device_id}.",
                    details={"humidity": hum, "min": self.humidity_min, "max": self.humidity_max, "device_id": device_id},
                    timestamp=now
                )

        # 4. Motion Alert (PIR) - LOW
        motion = data.get("motion")
        if self.motion_alert and motion:
            if self._can_alert("motion_detected", now):
                self._record_alert(
                    event_type="motion_detected",
                    severity="low",
                    confidence=0.99,
                    description=f"PIR motion sensor triggered on device {device_id}.",
                    details={"motion": True, "device_id": device_id},
                    timestamp=now
                )

        return self.last_sensor_data

    def _can_alert(self, alert_key: str, now: float) -> bool:
        last = self.last_alert_times.get(alert_key, 0.0)
        return (now - last) >= self.cooldown_seconds

    def _record_alert(
        self,
        event_type: str,
        severity: str,
        confidence: float,
        description: str,
        details: Dict[str, Any],
        timestamp: float
    ):
        self.last_alert_times[event_type] = timestamp
        candidate = EventCandidate(
            event_type=event_type,
            severity=severity,
            confidence=confidence,
            description=description,
            details=details,
            evidence_path=None,
            timestamp=timestamp
        )
        self.pending_events.append(candidate)
        logger.warning(f"Generated EventCandidate: {description}")

    def generate_events(self) -> List[EventCandidate]:
        events = list(self.pending_events)
        self.pending_events.clear()
        return events

    def stop(self) -> None:
        self._running = False
        self.pending_events.clear()
        self.last_sensor_data.clear()
        logger.info("EnvironmentMonitoringPlugin stopped.")
