import asyncio
import time
import threading
import logging
from typing import Dict, Optional, Any
import cv2
import numpy as np
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.connection import SessionLocal
from backend.database import crud
from backend.monitoring.registry import get_plugin
from backend.monitoring.base import MonitoringPlugin, FrameResult, EventCandidate
from backend.vision.camera import camera_stream
from backend.api.websocket import dashboard_ws_manager

logger = logging.getLogger(__name__)


class VisionTaskWorker:
    """
    Background worker for vision monitoring plugins (e.g. crowd_monitoring).
    Runs at unified TARGET_FPS (20 FPS), consumes frames from camera_stream, executes plugin logic,
    persists events to SQLite ('pending_review'), and broadcasts live metrics over WebSocket.
    """
    def __init__(self, task_id: int, plugin: MonitoringPlugin, config: Dict[str, Any]):
        self.task_id = task_id
        self.plugin = plugin
        self.config = config
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._latest_annotated: Optional[np.ndarray] = None
        self._latest_jpeg_bytes: Optional[bytes] = None
        self._latest_frame_id: int = -1
        self._latest_timestamp_ms: float = 0.0
        self._frame_seq: int = 0
        self._lock = threading.Lock()
        self._fps: float = 0.0

    def start(self):
        if self._running:
            return
        self._running = True
        camera_stream.start()
        self._thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"VisionWorker-Task-{self.task_id}"
        )
        self._thread.start()
        logger.info(f"VisionTaskWorker started for task {self.task_id}")

    def _worker_loop(self):
        target_fps = float(self.config.get("target_fps", settings.TARGET_FPS))
        frame_interval = 1.0 / max(target_fps, 1.0)
        frame_count = 0
        fps_timer = time.time()

        while self._running:
            loop_start = time.time()
            ok, frame, _, ts_ms = camera_stream.get_frame_meta()

            if ok and frame is not None:
                # 1. Process frame with plugin
                try:
                    result: Optional[FrameResult] = self.plugin.process_frame(frame)
                    if result:
                        frame_count += 1
                        # Update FPS calculation
                        if (time.time() - fps_timer) >= 1.0:
                            self._fps = frame_count / (time.time() - fps_timer)
                            frame_count = 0
                            fps_timer = time.time()

                        # Store latest annotated frame and pre-encode JPEG ONCE in worker thread
                        if hasattr(self.plugin, "last_annotated_frame") and self.plugin.last_annotated_frame is not None:
                            ann = self.plugin.last_annotated_frame
                            quality = getattr(settings, "JPEG_QUALITY", 75)
                            ret, buf = cv2.imencode(".jpg", ann, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                            jpeg_bytes = buf.tobytes() if ret else None
                            with self._lock:
                                self._latest_annotated = ann.copy()
                                if jpeg_bytes is not None:
                                    self._frame_seq += 1
                                    self._latest_jpeg_bytes = jpeg_bytes
                                    self._latest_frame_id = self._frame_seq
                                    self._latest_timestamp_ms = ts_ms

                        # 2. Check for generated events
                        events = self.plugin.generate_events()
                        if events:
                            self._persist_events(events)

                        # 3. Broadcast telemetry update over WebSocket (non-blocking)
                        self._broadcast_vision_metrics(result)
                except Exception as e:
                    logger.error(f"Error in VisionTaskWorker {self.task_id} frame processing: {e}", exc_info=True)

            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _persist_events(self, events: list[EventCandidate]):
        """Persist generated candidate events into database with 'pending_review' status."""
        db: Session = SessionLocal()
        plugin_name = self.plugin.get_metadata().name
        try:
            for cand in events:
                event_row = crud.create_event(
                    db=db,
                    event_type=cand.event_type,
                    source=plugin_name,
                    description=cand.description,
                    confidence=cand.confidence,
                    severity=cand.severity,
                    evidence_screenshot_path=cand.evidence_path,
                    metrics=cand.details
                )
                logger.info(f"Persisted event #{event_row.id} for task {self.task_id} (status: pending_review)")

                # Broadcast alert event over WebSocket
                event_payload = {
                    "type": "event_alert",
                    "event": {
                        "id": event_row.id,
                        "event_type": event_row.event_type,
                        "source": event_row.source,
                        "description": event_row.description,
                        "confidence": event_row.confidence,
                        "severity": event_row.severity,
                        "evidence_path": event_row.evidence_screenshot_path,
                        "metrics": event_row.metrics,
                        "status": event_row.status,
                        "created_at": event_row.created_at.isoformat() if event_row.created_at else None
                    }
                }
                self._safe_ws_broadcast(event_payload)
        except Exception as e:
            logger.error(f"Error persisting events for task {self.task_id}: {e}")
        finally:
            db.close()

    def _broadcast_vision_metrics(self, result: FrameResult):
        """Send live frame stats to connected WebSocket clients."""
        payload = {
            "type": "vision_update",
            "task_id": self.task_id,
            "person_count": result.person_count,
            "density_level": result.density_level,
            "fps": round(self._fps, 1),
            "timestamp": time.time(),
            "detections": [d.model_dump() for d in result.detections]
        }
        self._safe_ws_broadcast(payload)

    def _safe_ws_broadcast(self, payload: dict):
        """Schedule WebSocket broadcast without blocking worker loop."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(dashboard_ws_manager.broadcast(payload), loop)
        except Exception:
            # Fallback for environments with standalone event loop
            try:
                new_loop = asyncio.new_event_loop()
                new_loop.run_until_complete(dashboard_ws_manager.broadcast(payload))
                new_loop.close()
            except Exception as ex:
                logger.debug(f"WS broadcast warning: {ex}")

    def get_annotated_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            if self._latest_annotated is not None:
                return self._latest_annotated.copy()
            return None

    def get_latest_jpeg(self) -> tuple[Optional[bytes], int, float]:
        with self._lock:
            return self._latest_jpeg_bytes, self._latest_frame_id, self._latest_timestamp_ms

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.plugin.stop()
        logger.info(f"VisionTaskWorker stopped for task {self.task_id}")


class EnvironmentTaskWorker:
    """
    Background worker for environmental IoT monitoring plugins.
    Processes telemetry data, generates events when thresholds are crossed,
    and updates database & WebSockets.
    """
    def __init__(self, task_id: int, plugin: MonitoringPlugin, config: Dict[str, Any]):
        self.task_id = task_id
        self.plugin = plugin
        self.config = config
        self._running = False

    def start(self):
        self._running = True
        logger.info(f"EnvironmentTaskWorker started for task {self.task_id}")

    def ingest_sensor_data(self, data: Dict[str, Any]):
        """Feed telemetry data to the plugin."""
        if not self._running:
            return

        self.plugin.process_sensor_data(data)
        events = self.plugin.generate_events()
        if events:
            self._persist_events(events)

    def _persist_events(self, events: list[EventCandidate]):
        db: Session = SessionLocal()
        try:
            for cand in events:
                event_row = crud.create_event(
                    db=db,
                    event_type=cand.event_type,
                    source="environment_monitoring",
                    description=cand.description,
                    confidence=cand.confidence,
                    severity=cand.severity,
                    evidence_screenshot_path=None,
                    metrics=cand.details
                )
                logger.info(f"Persisted environment event #{event_row.id} (status: pending_review)")

                event_payload = {
                    "type": "event_alert",
                    "event": {
                        "id": event_row.id,
                        "event_type": event_row.event_type,
                        "source": event_row.source,
                        "description": event_row.description,
                        "confidence": event_row.confidence,
                        "severity": event_row.severity,
                        "evidence_path": None,
                        "metrics": event_row.metrics,
                        "status": event_row.status,
                        "created_at": event_row.created_at.isoformat() if event_row.created_at else None
                    }
                }
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.run_coroutine_threadsafe(dashboard_ws_manager.broadcast(event_payload), loop)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error persisting environment event: {e}")
        finally:
            db.close()

    def stop(self):
        self._running = False
        self.plugin.stop()
        logger.info(f"EnvironmentTaskWorker stopped for task {self.task_id}")


class TaskRunnerManager:
    """
    Coordinates lifecycle of active monitoring workers.
    Ensures single source of truth for running plugin instances.
    """
    _instance: Optional["TaskRunnerManager"] = None

    def __init__(self):
        self._active_workers: Dict[int, Any] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "TaskRunnerManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start_task(
        self,
        task_id: int,
        plugin_name: str,
        target_source: str,
        config: Dict[str, Any]
    ) -> bool:
        """Instantiates, initializes, and starts a worker for a task."""
        with self._lock:
            # Stop existing worker if running for this task_id
            if task_id in self._active_workers:
                self.stop_task(task_id)

            plugin = get_plugin(plugin_name)
            if not plugin:
                logger.error(f"Plugin '{plugin_name}' not found in registry!")
                return False

            plugin.initialize(config)

            meta = plugin.get_metadata()
            if meta.domain == "vision" or plugin_name == "crowd_monitoring":
                worker = VisionTaskWorker(task_id, plugin, config)
            else:
                worker = EnvironmentTaskWorker(task_id, plugin, config)

            worker.start()
            self._active_workers[task_id] = worker
            logger.info(f"Started worker for task {task_id} ({plugin_name})")
            return True

    def stop_task(self, task_id: int) -> bool:
        """Stops worker and releases resources."""
        with self._lock:
            worker = self._active_workers.pop(task_id, None)
            if worker:
                worker.stop()
                logger.info(f"Stopped worker for task {task_id}")
                return True
            return False

    def get_active_worker(self, task_id: int) -> Optional[Any]:
        return self._active_workers.get(task_id)

    def get_active_worker_jpeg(self) -> tuple[Optional[bytes], int, float]:
        """Non-blocking pre-encoded JPEG retrieval from active VisionTaskWorker only."""
        with self._lock:
            for worker in self._active_workers.values():
                if isinstance(worker, VisionTaskWorker):
                    jpeg_bytes, fid, ts_ms = worker.get_latest_jpeg()
                    if jpeg_bytes is not None:
                        return jpeg_bytes, fid, ts_ms
        return None, -1, 0.0

    def get_latest_vision_frame(self) -> Optional[np.ndarray]:
        """Returns the latest annotated frame from any active vision worker, or real-time camera preview detection."""
        with self._lock:
            for worker in self._active_workers.values():
                if isinstance(worker, VisionTaskWorker):
                    frame = worker.get_annotated_frame()
                    if frame is not None:
                        return frame

        # Real-time preview detection on live camera feed when no task is active
        ok, frame = camera_stream.get_frame()
        if ok and frame is not None:
            try:
                from backend.vision.detector import UniversalWorldDetector, PersonDetector
                world = UniversalWorldDetector.get_instance()
                detections, _, _ = world.detect_all(frame, conf_threshold=0.22, imgsz=320)
                person_count = sum(1 for d in detections if d.class_name == "person")
                density_level = "low" if person_count <= 2 else ("medium" if person_count <= 5 else "high")
                annotated = PersonDetector.get_instance().annotate(
                    frame=frame,
                    detections=detections,
                    person_count=person_count,
                    density_level=density_level,
                    fps=15.0
                )
                payload = {
                    "type": "vision_update",
                    "task_id": 0,
                    "person_count": person_count,
                    "density_level": density_level,
                    "fps": 15.0,
                    "timestamp": time.time(),
                    "detections": [d.model_dump() for d in detections]
                }
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.run_coroutine_threadsafe(dashboard_ws_manager.broadcast(payload), loop)
                except Exception:
                    pass
                return annotated
            except Exception as e:
                logger.debug(f"Preview annotation fallback: {e}")
                return frame
        return None

    def dispatch_sensor_data(self, data: Dict[str, Any]):
        """Dispatches incoming sensor telemetry to active environment workers."""
        with self._lock:
            for worker in self._active_workers.values():
                if isinstance(worker, EnvironmentTaskWorker):
                    worker.ingest_sensor_data(data)

    def stop_all(self):
        """Stops all active workers during shutdown."""
        with self._lock:
            for task_id, worker in list(self._active_workers.items()):
                try:
                    worker.stop()
                except Exception as e:
                    logger.error(f"Error stopping worker {task_id}: {e}")
            self._active_workers.clear()


task_manager = TaskRunnerManager.get_instance()
