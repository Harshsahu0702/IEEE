import json
import time
import threading
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.connection import SessionLocal
from backend.database import crud
from backend.database.models import Device
from backend.iot.telemetry_schema import TelemetryPayload, DeviceStatusPayload
from backend.monitoring.runner import task_manager
from backend.api.websocket import dashboard_ws_manager

logger = logging.getLogger(__name__)


class TelemetryHandler:
    """
    Ingests and validates incoming device telemetry.
    Business Rules:
    - Never trust raw device input; drop malformed JSON or invalid schema.
    - Auto-register unknown devices as 'pending' (untrusted until admin approves).
    - If approved, mark device 'online', update last_seen, forward to environment_monitoring.
    - Push live updates to WebSocket.
    - Offline Checker: background thread marks devices 'offline' if no ping for 30s.
    """
    def __init__(self):
        self._offline_checker_running = False
        self._offline_thread: Optional[threading.Thread] = None

    def handle_raw_telemetry(self, raw_bytes: bytes, topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Validates raw payload, applies business rules, persists telemetry,
        and dispatches to monitoring plugin and WebSocket clients.
        """
        # 1. Parse JSON safely
        try:
            raw_text = raw_bytes.decode("utf-8") if isinstance(raw_bytes, (bytes, bytearray)) else str(raw_bytes)
            raw_dict = json.loads(raw_text)
        except Exception as e:
            logger.warning(f"Dropped malformed non-JSON telemetry payload from topic {topic}: {e}")
            return None

        # 2. Validate strictly with Pydantic
        try:
            telemetry_data = TelemetryPayload(**raw_dict)
        except ValidationError as ve:
            logger.warning(f"Dropped invalid telemetry payload: {ve.errors()} (raw: {raw_dict})")
            return None

        # 3. Apply database rules & auto-registration
        db: Session = SessionLocal()
        try:
            device = crud.get_device_by_id(db, telemetry_data.device_id)

            if not device:
                # Rule: Auto-register unknown devices as 'pending' (not trusted until admin approves)
                device = crud.create_device(
                    db=db,
                    device_id=telemetry_data.device_id,
                    name=f"Device {telemetry_data.device_id}",
                    device_type="multisensor",
                    location="Unassigned Area",
                    status="pending",
                    approval_status="pending",
                    config={"auto_registered": True}
                )
                logger.warning(f"Auto-registered untrusted device '{telemetry_data.device_id}' with status 'pending'")

            # Update last_seen
            device.last_seen = datetime.utcnow()
            is_approved = (device.approval_status == "approved")

            if is_approved:
                # Only trusted / approved devices can be marked online
                device.status = "online"
            db.commit()

            # Store DeviceTelemetry row
            stored = crud.create_telemetry(
                db=db,
                device_id=telemetry_data.device_id,
                temperature=telemetry_data.temperature,
                humidity=telemetry_data.humidity,
                gas_level=telemetry_data.gas_level,
                motion=telemetry_data.motion,
                raw_payload=raw_dict,
                timestamp=telemetry_data.timestamp
            )

            result_dict = {
                "device_id": stored.device_id,
                "temperature": stored.temperature,
                "humidity": stored.humidity,
                "gas_level": stored.gas_level,
                "motion": stored.motion,
                "timestamp": stored.timestamp.isoformat() if stored.timestamp else datetime.utcnow().isoformat(),
                "device_status": device.status,
                "approval_status": device.approval_status
            }

            # 4. If approved, update live sensor snapshot for VLM Reasoner and forward to any active plugins
            if is_approved:
                _update_sensor_snapshot(result_dict)
                try:
                    task_manager.dispatch_sensor_data(result_dict)
                except Exception:
                    pass
            else:
                logger.info(f"Telemetry recorded for pending device '{telemetry_data.device_id}' (not dispatched to alerts until approved).")

            # 5. Broadcast live telemetry update over WebSocket
            ws_payload = {
                "type": "telemetry_update",
                "telemetry": result_dict
            }
            self._safe_ws_broadcast(ws_payload)

            return result_dict
        except Exception as e:
            db.rollback()
            logger.error(f"Error persisting device telemetry: {e}")
            return None
        finally:
            db.close()

    def handle_raw_status(self, raw_bytes: bytes, topic: Optional[str] = None):
        """Processes device status/heartbeat message."""
        try:
            raw_text = raw_bytes.decode("utf-8") if isinstance(raw_bytes, (bytes, bytearray)) else str(raw_bytes)
            raw_dict = json.loads(raw_text)
            status_data = DeviceStatusPayload(**raw_dict)
        except Exception as e:
            logger.warning(f"Dropped malformed device status payload: {e}")
            return

        db: Session = SessionLocal()
        try:
            device = crud.get_device_by_id(db, status_data.device_id)
            if device:
                device.last_seen = datetime.utcnow()
                if device.approval_status == "approved":
                    device.status = status_data.status
                db.commit()

                # Broadcast device health change
                self._safe_ws_broadcast({
                    "type": "device_status",
                    "device_id": device.device_id,
                    "status": device.status,
                    "approval_status": device.approval_status,
                    "last_seen": device.last_seen.isoformat()
                })
        finally:
            db.close()

    def start_offline_checker(self, interval_sec: int = 10, timeout_sec: int = 30):
        """Starts background loop to mark devices offline after 30s with no telemetry."""
        if self._offline_checker_running:
            return
        self._offline_checker_running = True
        self._offline_thread = threading.Thread(
            target=self._offline_checker_loop,
            args=(interval_sec, timeout_sec),
            daemon=True,
            name="DeviceOfflineCheckerThread"
        )
        self._offline_thread.start()
        logger.info(f"Device offline checker started (timeout={timeout_sec}s, interval={interval_sec}s)")

    def _offline_checker_loop(self, interval_sec: int, timeout_sec: int):
        while self._offline_checker_running:
            try:
                self.check_offline_devices(timeout_sec)
            except Exception as e:
                logger.error(f"Error in offline checker loop: {e}")
            time.sleep(interval_sec)

    def check_offline_devices(self, timeout_sec: int = 30) -> list[str]:
        """Scans devices and marks overdue devices offline."""
        db: Session = SessionLocal()
        offline_marked = []
        try:
            now = datetime.utcnow()
            cutoff = now - timedelta(seconds=timeout_sec)

            # Query devices that are online or alerting but haven't sent telemetry past cutoff
            devices = db.query(Device).filter(Device.status.in_(["online", "alerting"])).all()
            for d in devices:
                if d.last_seen and d.last_seen < cutoff:
                    d.status = "offline"
                    offline_marked.append(d.device_id)
                    logger.info(f"Marked device '{d.device_id}' as OFFLINE (no heartbeat for >{timeout_sec}s)")

                    # Broadcast offline status
                    self._safe_ws_broadcast({
                        "type": "device_status",
                        "device_id": d.device_id,
                        "status": "offline",
                        "last_seen": d.last_seen.isoformat() if d.last_seen else None
                    })
            if offline_marked:
                db.commit()
        finally:
            db.close()
        return offline_marked

    def stop_offline_checker(self):
        self._offline_checker_running = False
        if self._offline_thread and self._offline_thread.is_alive():
            self._offline_thread.join(timeout=2.0)
        logger.info("Device offline checker stopped.")

    def _safe_ws_broadcast(self, payload: dict):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(dashboard_ws_manager.broadcast(payload), loop)
        except Exception:
            try:
                new_loop = asyncio.new_event_loop()
                new_loop.run_until_complete(dashboard_ws_manager.broadcast(payload))
                new_loop.close()
            except Exception:
                pass


telemetry_handler = TelemetryHandler()


# ---------------------------------------------------------------------------
# Global latest sensor data cache (used by VLM Reasoner for context)
# ---------------------------------------------------------------------------

_latest_sensor_snapshot: dict = {}


def _update_sensor_snapshot(data: dict):
    """Called by TelemetryHandler when new data arrives from any approved device."""
    global _latest_sensor_snapshot
    _latest_sensor_snapshot = {
        "temperature": data.get("temperature"),
        "humidity": data.get("humidity"),
        "gas_level": data.get("gas_level"),
        "motion_detected": data.get("motion"),
        "device_id": data.get("device_id"),
    }


def get_latest_sensor_data() -> dict:
    """Return the most recently received sensor readings from any approved IoT device."""
    return dict(_latest_sensor_snapshot)
