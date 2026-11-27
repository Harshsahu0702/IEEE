import asyncio
import time
import logging
from typing import Optional
import cv2
import numpy as np
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from pydantic import BaseModel
from backend.config import settings
from backend.monitoring.runner import task_manager
from backend.vision.camera import camera_stream

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/video", tags=["Video Stream"])

_STANDBY_CACHE: Optional[bytes] = None


class CameraSourceRequest(BaseModel):
    source: str  # "0", "1", or "http://192.168.1.15:8080/video"


class CameraRotationRequest(BaseModel):
    rotation: int  # 0, 90, 180, 270


def get_standby_frame() -> bytes:
    """Generate cached standby frame when camera is initializing."""
    global _STANDBY_CACHE
    if _STANDBY_CACHE is not None:
        return _STANDBY_CACHE

    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (24, 24, 27)
    cv2.rectangle(img, (10, 10), (630, 470), (45, 45, 55), 1)
    cv2.putText(img, "OMNISENSE AI - OPTICAL STREAM", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 220, 140), 2, cv2.LINE_AA)
    cv2.putText(img, "Standby: Initializing optical capture...", (30, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(img, "Status: System Ready", (30, 455),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 100), 1, cv2.LINE_AA)

    _, jpeg = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    _STANDBY_CACHE = jpeg.tobytes()
    return _STANDBY_CACHE


def get_latest_encoded_frame() -> tuple[Optional[bytes], str, int, float]:
    """
    Zero-copy retrieval of pre-encoded JPEG bytes from the active vision pipeline.
    Returns (jpeg_bytes, source_tag, frame_id, timestamp_ms).
    Never runs cv2.imencode or YOLO inference on the FastAPI async event loop.
    """
    from backend.monitoring import universal_runner
    jpeg_bytes, fid, ts_ms = universal_runner.get_latest_jpeg_frame()
    if jpeg_bytes is not None:
        return jpeg_bytes, "universal", fid, ts_ms

    jpeg_bytes, fid, ts_ms = task_manager.get_active_worker_jpeg()
    if jpeg_bytes is not None:
        return jpeg_bytes, "legacy_worker", fid, ts_ms

    jpeg_bytes, fid, ts_ms = camera_stream.get_latest_jpeg()
    if jpeg_bytes is not None:
        return jpeg_bytes, "camera", fid, ts_ms

    return None, "standby", -1, 0.0


async def mjpeg_frame_generator(max_frames: Optional[int] = None):
    """
    Generator yielding pre-encoded MJPEG frames without blocking the event loop.
    Only yields when a new frame_id is produced, avoiding redundant encoding/sending.
    """
    camera_stream.start()
    frames_sent = 0
    last_key = None
    target_interval = 1.0 / max(getattr(settings, "TARGET_FPS", 20), 1)

    while True:
        if max_frames is not None and frames_sent >= max_frames:
            break

        try:
            frame_bytes, src_tag, fid, _ = get_latest_encoded_frame()
            current_key = (src_tag, fid)

            if frame_bytes is None:
                frame_bytes = get_standby_frame()
            elif current_key == last_key:
                await asyncio.sleep(0.015)
                continue

            last_key = current_key
            frames_sent += 1
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
            )
        except Exception as e:
            logger.error(f"Error yielding video frame: {e}")
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + get_standby_frame() + b'\r\n'
            )

        await asyncio.sleep(target_interval * 0.7)


@router.get("/stream")
def video_stream(max_frames: Optional[int] = None, token: Optional[str] = None):
    """
    MJPEG live stream endpoint for dashboard.
    Outputs annotated video with YOLO person bounding boxes,
    crowd count, and density level badge.
    Accepts optional token in query param for authenticated <img> tags.
    """
    return StreamingResponse(
        mjpeg_frame_generator(max_frames=max_frames),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/source")
def get_camera_source():
    """Retrieve current camera input source and active state."""
    return {
        "source": str(camera_stream.camera_source),
        "is_synthetic": camera_stream._is_synthetic,
        "is_running": camera_stream._running,
        "rotation": camera_stream.rotation
    }


@router.post("/rotation")
def set_camera_rotation(req: CameraRotationRequest):
    """Rotate camera feed (0, 90, 180, 270 degrees)."""
    rot = camera_stream.set_rotation(req.rotation)
    return {
        "success": True,
        "rotation": rot
    }


@router.post("/source")
def switch_camera_source(req: CameraSourceRequest):
    """
    Switch optical input source in real-time.
    Supports laptop webcam index (e.g. 0) or Mobile Phone IP stream URL
    (e.g. http://192.168.1.15:8080/video).
    """
    ok, msg = camera_stream.set_source(req.source)
    return {
        "success": ok,
        "message": msg,
        "source": str(camera_stream.camera_source),
        "is_synthetic": camera_stream._is_synthetic,
        "rotation": camera_stream.rotation
    }

