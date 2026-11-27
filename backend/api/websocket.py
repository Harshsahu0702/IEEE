import asyncio
import json
import logging
import struct
import time
from typing import List, Set, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import settings
from backend.vision.camera import camera_stream

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSockets"])


class ConnectionManager:
    """Manages active WebSocket connections for live dashboard updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast JSON payload to all active clients."""
        dead_connections = []
        payload = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.warning(f"Error sending message to websocket: {e}")
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)

    def broadcast_sync(self, message: dict):
        """Thread-safe synchronous broadcast for background worker threads."""
        if not self.active_connections:
            return
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)
        else:
            try:
                asyncio.run(self.broadcast(message))
            except Exception as e:
                logger.debug(f"broadcast_sync fallback failed: {e}")


dashboard_ws_manager = ConnectionManager()


@router.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time telemetry, person counts,
    density levels, and pending alerts.
    """
    await dashboard_ws_manager.connect(websocket)
    try:
        # Send initial handshake message
        await websocket.send_json({
            "type": "connection_ack",
            "message": "Connected to OmniSense AI real-time dashboard stream",
            "timestamp": None
        })
        while True:
            # Keep connection open and receive optional client heartbeats
            data = await websocket.receive_text()
            # Respond to ping
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        dashboard_ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        dashboard_ws_manager.disconnect(websocket)


@router.websocket("/ws/live-feed")
async def websocket_live_video_feed(websocket: WebSocket):
    """
    High-speed binary WebSocket live video stream (zero HTTP buffer drift).
    Payload: 8-byte big-endian float64 timestamp_ms + pre-encoded JPEG bytes.
    Implements server-side backpressure dropping so slow clients never queue stale frames.
    """
    from backend.api.video import get_latest_encoded_frame

    await websocket.accept()
    camera_stream.start()
    last_key = None
    target_interval = 1.0 / max(getattr(settings, "TARGET_FPS", 20), 1)

    try:
        while True:
            frame_bytes, src_tag, fid, ts_ms = get_latest_encoded_frame()
            current_key = (src_tag, fid)

            if frame_bytes is not None and current_key != last_key:
                last_key = current_key
                header = struct.pack(">d", ts_ms if ts_ms > 0 else time.time() * 1000.0)
                packet = header + frame_bytes
                try:
                    await asyncio.wait_for(websocket.send_bytes(packet), timeout=0.25)
                except asyncio.TimeoutError:
                    logger.debug("Live feed client backpressure: dropped frame")
                    await asyncio.sleep(target_interval)
                    continue
                await asyncio.sleep(target_interval * 0.6)
            else:
                await asyncio.sleep(0.015)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Live feed WebSocket closed: {e}")
