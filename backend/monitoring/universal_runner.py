"""
Universal Monitoring Runner.

Replaces all hardcoded plugin workers (crowd, security, threat).
One single runner handles ANY monitoring goal the user specifies in natural language.

Flow per frame:
  1. MotionFilter detects if scene changed (cheap, local).
  2. If motion detected → VLMReasoner evaluates the frame against user_goal.
  3. If incident detected → save evidence snapshot + write DB event + broadcast WebSocket.
  4. Always → broadcast live metrics via WebSocket for adaptive UI.
"""

import asyncio
import base64
import logging
import threading
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.connection import SessionLocal
from backend.database import crud
from backend.vision.camera import camera_stream
from backend.vision.motion_filter import MotionFilter
from backend.vision.vlm_reasoner import VLMReasoner, ReasonerResult, _parse_goal_directive, _label_matches_targets
from backend.vision.detector import UniversalWorldDetector
from backend.api.websocket import dashboard_ws_manager
from backend.iot.telemetry import get_latest_sensor_data

logger = logging.getLogger(__name__)


class UniversalMonitorRunner:
    """
    Universal background monitoring worker.

    Accepts any natural-language monitoring goal and runs the
    Motion Filter → VLM Reasoner pipeline on live camera frames.

    Parameters
    ----------
    task_id : int
        Database ID of the MonitoringTask record.
    user_goal : str
        Natural language description of what to monitor
        (e.g. "Watch for student cheating in exam",
               "Detect fights or accidents at home",
               "Count people and report temperature every minute").
    config : dict
        Optional operator-defined config (cooldown, sensitivity, camera_index).
    """

    def __init__(self, task_id: int, user_goal: str, config: Dict[str, Any]):
        self.task_id = task_id
        self.user_goal = user_goal
        self.config = config

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._vlm_in_flight = False
        self._world_in_flight = False

        # Tunable parameters (from config or defaults)
        self.target_fps: float = float(config.get("target_fps", 10.0))
        self.vlm_every_n_frames: int = int(config.get("vlm_every_n_frames", 15))
        self.cooldown_seconds: float = float(config.get("cooldown_seconds", 20.0))

        self._motion_filter = MotionFilter(
            min_area_ratio=float(config.get("motion_sensitivity", 0.005)),
        )
        self._reasoner = VLMReasoner.get_instance()
        self._world_detector = UniversalWorldDetector.get_instance()

        goal_spec = _parse_goal_directive(user_goal)
        self._target_entities: list[str] = goal_spec["targets"]
        self._requires_vlm: bool = goal_spec["requires_vlm"]

        self._last_incident_time: float = 0.0
        self._frame_counter: int = 0
        self._latest_annotated: Optional[np.ndarray] = None
        self._last_result: Optional[ReasonerResult] = None
        self._live_boxes: list[dict] = []
        self._last_metrics: dict = {}

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        camera_stream.start()
        self._thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"UniversalMonitor-Task-{self.task_id}",
        )
        self._thread.start()
        logger.info(f"[Task {self.task_id}] Universal monitor started. Goal: '{self.user_goal}'")

    def stop(self):
        self._running = False
        self._motion_filter.reset()
        logger.info(f"[Task {self.task_id}] Universal monitor stopped.")

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._latest_annotated.copy() if self._latest_annotated is not None else None

    # ------------------------------------------------------------------
    # Core worker loop
    # ------------------------------------------------------------------

    def _worker_loop(self):
        frame_interval = 1.0 / self.target_fps

        while self._running:
            loop_start = time.time()

            ok, frame = camera_stream.get_frame()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            self._frame_counter += 1
            motion_detected, motion_score, motion_boxes = self._motion_filter.detect(frame)

            # Tier 1 / Full Reasoner scheduling:
            # - If goal is pure spatial/open-vocabulary (not requires_vlm), run continuously as fast as Tier 1 completes (~5-6 FPS)
            # - If goal requires Tier 2 VLM (semantic action/state), keep Tier 1 live boxes running continuously in parallel
            if not self._requires_vlm:
                if not self._vlm_in_flight:
                    self._vlm_in_flight = True
                    threading.Thread(
                        target=self._run_vlm_background,
                        args=(frame.copy(), motion_score),
                        daemon=True,
                    ).start()
            else:
                if not self._world_in_flight:
                    self._world_in_flight = True
                    threading.Thread(
                        target=self._run_live_boxes_background,
                        args=(frame.copy(),),
                        daemon=True,
                    ).start()

                should_reason = (
                    not self._vlm_in_flight
                    and (
                        self._frame_counter == 1
                        or (motion_detected and self._frame_counter % self.vlm_every_n_frames == 0)
                        or (self._frame_counter % 50 == 0)
                    )
                )
                if should_reason:
                    self._vlm_in_flight = True
                    threading.Thread(
                        target=self._run_vlm_background,
                        args=(frame.copy(), motion_score),
                        daemon=True,
                    ).start()

            # Always annotate and stream frame at full FPS (live object boxes + red alert isolation)
            annotated = self._annotate_frame(frame, self._last_result, motion_score, motion_boxes)
            with self._lock:
                self._latest_annotated = annotated

            # Broadcast live metrics via WebSocket (thread-safe)
            if self._frame_counter % 5 == 0:
                self._broadcast_metrics_sync(self._last_result)

            # Sleep to maintain target FPS
            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _run_live_boxes_background(self, frame: np.ndarray):
        """Continuously update live open-vocabulary bounding boxes during Tier 2 VLM tasks."""
        try:
            detections, _, _ = self._world_detector.detect_all(
                frame,
                target_classes=self._target_entities if self._target_entities else None,
            )
            h, w = frame.shape[:2]
            boxes = []
            for d in detections:
                ymin = max(0, min(1000, int(d.y1 * 1000 / h)))
                xmin = max(0, min(1000, int(d.x1 * 1000 / w)))
                ymax = max(0, min(1000, int(d.y2 * 1000 / h)))
                xmax = max(0, min(1000, int(d.x2 * 1000 / w)))
                is_target = _label_matches_targets(d.class_name, self._target_entities) if self._target_entities else False
                boxes.append({
                    "label": d.class_name,
                    "confidence": d.confidence,
                    "is_target": is_target,
                    "box_2d": [ymin, xmin, ymax, xmax],
                })
            self._live_boxes = boxes
        except Exception as e:
            logger.debug(f"Live boxes thread error: {e}")
        finally:
            self._world_in_flight = False

    def _run_vlm_background(self, frame: np.ndarray, motion_score: float):
        """Run VLM/World reasoning and incident handling off the video frame loop."""
        try:
            sensor_ctx = self._get_sensor_context()
            result = self._reasoner.reason(frame, self.user_goal, sensor_ctx)
            self._last_result = result
            if result.boxes:
                self._live_boxes = result.boxes
            self._last_metrics = result.metrics
            self._last_metrics["motion_score"] = round(motion_score, 3)
            self._last_metrics["vlm_latency_ms"] = round(result.latency_ms, 1)

            if result.incident_detected:
                self._handle_incident(frame, result)
                self._broadcast_metrics_sync(result)
        except Exception as e:
            logger.error(f"[Task {self.task_id}] Background VLM error: {e}")
        finally:
            self._vlm_in_flight = False

    # ------------------------------------------------------------------
    # Incident handling
    # ------------------------------------------------------------------

    def _handle_incident(self, frame: np.ndarray, result: ReasonerResult):
        now = time.time()
        if now - self._last_incident_time < self.cooldown_seconds:
            logger.debug(f"[Task {self.task_id}] Incident suppressed (cooldown).")
            return
        self._last_incident_time = now

        # Save evidence snapshot
        evidence_path = self._save_evidence(frame, result)

        # Persist to database
        self._persist_event(result, evidence_path)

        # Trigger Arduino alarm if physical danger
        if result.action_required == "alarm":
            self._trigger_hardware_alarm()

        # Broadcast event_alert over WebSocket for instant toast notification across the whole app
        try:
            alert_payload = {
                "type": "event_alert",
                "event": {
                    "id": self.task_id,
                    "event_type": f"prompt_{result.action_required}",
                    "severity": "critical" if result.action_required == "alarm" else "high",
                    "description": result.explanation,
                    "confidence": result.confidence,
                    "evidence_screenshot_path": evidence_path,
                }
            }
            dashboard_ws_manager.broadcast_sync(alert_payload)
        except Exception as e:
            logger.debug(f"Failed to broadcast event_alert: {e}")

        logger.warning(
            f"[Task {self.task_id}] INCIDENT [{result.action_required.upper()}]: "
            f"{result.explanation} (confidence: {result.confidence:.0%})"
        )

    def _save_evidence(self, frame: np.ndarray, result: ReasonerResult) -> str:
        evidence_dir = Path(settings.EVIDENCE_DIR)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"task_{self.task_id}_{ts}.jpg"
        filepath = evidence_dir / filename
        cv2.imwrite(str(filepath), frame)
        return str(filepath)

    def _persist_event(self, result: ReasonerResult, evidence_path: str):
        db: Session = SessionLocal()
        try:
            severity_map = {
                "alarm": "critical",
                "warn": "high",
                "monitor": "medium",
                "log": "low",
            }
            crud.create_event(
                db=db,
                event_type=f"universal_{result.action_required}",
                source=f"universal_task_{self.task_id}",
                description=result.explanation,
                confidence=result.confidence,
                severity=severity_map.get(result.action_required, "medium"),
                evidence_screenshot_path=evidence_path,
                metrics={
                    "goal": self.user_goal,
                    "action_required": result.action_required,
                    **(result.metrics or {}),
                },
            )
        except Exception as e:
            logger.error(f"Failed to persist event: {e}")
        finally:
            db.close()

    def _trigger_hardware_alarm(self):
        """Signal Arduino to activate physical strobe/buzzer."""
        try:
            import requests
            requests.post(
                "http://localhost:8000/api/devices/alarm/trigger",
                json={"alarm_active": True, "threat_type": self.user_goal},
                timeout=1.0,
            )
        except Exception:
            pass  # Non-critical — alarm is optional hardware

    # ------------------------------------------------------------------
    # Frame annotation
    # ------------------------------------------------------------------

    def _annotate_frame(
        self, frame, result, motion_score, motion_boxes=None
    ):
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        is_alert = bool(
            result and (result.incident_detected or result.action_required in ["alert", "alarm"])
        )

        # 1. Motion Bounding Boxes (only shown during normal ambient monitoring; suppressed on alert)
        if not is_alert and motion_boxes:
            for bx1, by1, bx2, by2 in motion_boxes:
                cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (255, 200, 0), 1)
                cv2.putText(
                    annotated,
                    "MOTION",
                    (bx1 + 2, max(14, by1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    (255, 200, 0),
                    1,
                    cv2.LINE_AA,
                )

        # 2. Dual-Layer Open-Vocabulary Bounding Boxes
        #    - Normal state: All visible objects labeled in calm cyan (PERSON, CHAIR, FAN, etc.)
        #    - Alert state: ONLY the triggering target object(s) shown in bold RED; others hidden
        raw_boxes = self._live_boxes or (getattr(result, "boxes", None) if result else None) or []
        if is_alert:
            target_only = [b for b in raw_boxes if b.get("is_target")]
            boxes_to_draw = target_only if target_only else raw_boxes
        else:
            boxes_to_draw = raw_boxes

        for b in boxes_to_draw:
            coords = b.get("box_2d", [])
            if len(coords) != 4:
                continue
            ymin, xmin, ymax, xmax = coords
            x1 = max(0, min(w - 1, int(xmin * w / 1000)))
            y1 = max(0, min(h - 1, int(ymin * h / 1000)))
            x2 = max(0, min(w - 1, int(xmax * w / 1000)))
            y2 = max(0, min(h - 1, int(ymax * h / 1000)))

            # Red (0, 0, 235) for active alert box; calm cyan (230, 190, 0) for live ambient boxes
            box_color = (0, 0, 235) if is_alert else (230, 190, 0)
            label = str(b.get("label", "OBJECT")).upper()
            box_conf = b.get("confidence", result.confidence if result else 0.0)

            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2 if is_alert else 1)
            c_len = min(16, max(6, int(min(x2 - x1, y2 - y1) * 0.2)))
            thickness = 3 if is_alert else 2
            cv2.line(annotated, (x1, y1), (x1 + c_len, y1), box_color, thickness)
            cv2.line(annotated, (x1, y1), (x1, y1 + c_len), box_color, thickness)
            cv2.line(annotated, (x2, y1), (x2 - c_len, y1), box_color, thickness)
            cv2.line(annotated, (x2, y1), (x2, y1 + c_len), box_color, thickness)
            cv2.line(annotated, (x1, y2), (x1 + c_len, y2), box_color, thickness)
            cv2.line(annotated, (x1, y2), (x1, y2 - c_len), box_color, thickness)
            cv2.line(annotated, (x2, y2), (x2 - c_len, y2), box_color, thickness)
            cv2.line(annotated, (x2, y2), (x2, y2 - c_len), box_color, thickness)

            tag = f"ALERT: {label} ({box_conf:.0%})" if is_alert else f"{label} ({box_conf:.0%})"
            (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            badge_y1 = max(0, y1 - th - 6)
            cv2.rectangle(annotated, (x1, badge_y1), (x1 + tw + 6, y1), box_color, -1)
            cv2.putText(
                annotated,
                tag,
                (x1 + 3, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        # 3. Status bar at top
        status_color = (0, 200, 0)
        status_text = "MONITORING ACTIVE"
        if result and result.incident_detected:
            status_color = (0, 0, 220) if result.action_required == "alarm" else (0, 140, 255)
            status_text = f"ALERT: {result.action_required.upper()} - {result.explanation[:60]}"

        cv2.rectangle(annotated, (0, 0), (w, 36), (20, 20, 20), -1)
        cv2.putText(annotated, status_text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 1, cv2.LINE_AA)

        motion_pct = int(motion_score * 100)
        motion_label = f"Motion: {motion_pct}%"
        cv2.putText(annotated, motion_label, (w - 140, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1, cv2.LINE_AA)

        if result:
            conf_label = f"AI Confidence: {result.confidence:.0%}"
            cv2.putText(annotated, conf_label, (8, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 220, 100), 1, cv2.LINE_AA)

        return annotated

    # ------------------------------------------------------------------
    # WebSocket broadcast
    # ------------------------------------------------------------------

    def _broadcast_metrics_sync(self, result: Optional[ReasonerResult]):
        """Thread-safe synchronous broadcast using dashboard_ws_manager.broadcast_sync."""
        sensor_ctx = self._get_sensor_context()
        active_res = result or self._last_result
        payload = {
            "type": "universal_monitor_update",
            "task_id": self.task_id,
            "goal": self.user_goal,
            "timestamp": datetime.now(UTC).isoformat(),
            "motion_score": round(self._motion_filter.last_motion_score, 3),
            "incident_detected": active_res.incident_detected if active_res else False,
            "confidence": active_res.confidence if active_res else 0.0,
            "explanation": active_res.explanation if active_res else "",
            "action_required": active_res.action_required if active_res else "none",
            "boxes": getattr(active_res, "boxes", []) if active_res else [],
            # Dynamic metrics for the adaptive UI
            "metrics": {**self._last_metrics, **sensor_ctx},
            # Context hint for the UI: tells frontend WHICH widgets to render
            "active_metrics": self._derive_active_metrics(sensor_ctx),
        }
        dashboard_ws_manager.broadcast_sync(payload)

    async def _broadcast_metrics(self, result: Optional[ReasonerResult]):
        sensor_ctx = self._get_sensor_context()
        active_res = result or self._last_result
        payload = {
            "type": "universal_monitor_update",
            "task_id": self.task_id,
            "goal": self.user_goal,
            "timestamp": datetime.now(UTC).isoformat(),
            "motion_score": round(self._motion_filter.last_motion_score, 3),
            "incident_detected": active_res.incident_detected if active_res else False,
            "confidence": active_res.confidence if active_res else 0.0,
            "explanation": active_res.explanation if active_res else "",
            "action_required": active_res.action_required if active_res else "none",
            "boxes": getattr(active_res, "boxes", []) if active_res else [],
            # Dynamic metrics for the adaptive UI
            "metrics": {**self._last_metrics, **sensor_ctx},
            # Context hint for the UI: tells frontend WHICH widgets to render
            "active_metrics": self._derive_active_metrics(sensor_ctx),
        }
        try:
            await dashboard_ws_manager.broadcast(payload)
        except Exception as e:
            logger.debug(f"WebSocket broadcast error: {e}")

    def _derive_active_metrics(self, sensor_ctx: dict) -> list[str]:
        """
        Returns the list of metric names the frontend should actively display.
        The UI reads this to know which charts/widgets to render dynamically.
        """
        active = []
        goal_lower = self.user_goal.lower()

        # Vision-based metrics
        if any(w in goal_lower for w in ["people", "crowd", "count", "person", "headcount"]):
            active.append("person_count")
        if any(w in goal_lower for w in ["exam", "cheat", "study", "class"]):
            active.append("risk_score")
            active.append("incident_timeline")
        if any(w in goal_lower for w in ["fight", "violence", "accident", "fall", "hurt"]):
            active.append("safety_status")
            active.append("incident_timeline")

        # IoT / sensor metrics
        if sensor_ctx.get("temperature") is not None:
            active.append("temperature")
        if sensor_ctx.get("humidity") is not None:
            active.append("humidity")
        if sensor_ctx.get("gas_level") is not None:
            active.append("gas_level")
        if sensor_ctx.get("motion_detected") is not None:
            active.append("pir_motion")

        # Always show motion score
        active.append("motion_score")

        return active

    # ------------------------------------------------------------------
    # Sensor context from IoT layer
    # ------------------------------------------------------------------

    def _get_sensor_context(self) -> dict:
        """Pull latest sensor data from MQTT/Arduino telemetry layer."""
        try:
            data = get_latest_sensor_data()
            return data or {}
        except Exception:
            return {}


# ------------------------------------------------------------------
# Global task registry
# ------------------------------------------------------------------

_active_runners: Dict[int, UniversalMonitorRunner] = {}
_registry_lock = threading.Lock()


def start_universal_task(task_id: int, user_goal: str, config: Dict[str, Any]) -> UniversalMonitorRunner:
    with _registry_lock:
        if task_id in _active_runners:
            _active_runners[task_id].stop()
        runner = UniversalMonitorRunner(task_id, user_goal, config)
        runner.start()
        _active_runners[task_id] = runner
        return runner


def stop_universal_task(task_id: int):
    with _registry_lock:
        runner = _active_runners.pop(task_id, None)
        if runner:
            runner.stop()


def get_runner(task_id: int) -> Optional[UniversalMonitorRunner]:
    return _active_runners.get(task_id)


def get_active_frame(task_id: int) -> Optional[np.ndarray]:
    runner = get_runner(task_id)
    return runner.get_latest_frame() if runner else None


def get_latest_vision_frame() -> Optional[np.ndarray]:
    """Retrieve the latest annotated frame from any active universal runner."""
    with _registry_lock:
        for runner in _active_runners.values():
            frame = runner.get_latest_frame()
            if frame is not None:
                return frame
    return None


def stop_all():
    """Stop all active universal monitoring tasks."""
    with _registry_lock:
        for runner in list(_active_runners.values()):
            try:
                runner.stop()
            except Exception as e:
                logger.error(f"Error stopping runner {runner.task_id}: {e}")
        _active_runners.clear()
