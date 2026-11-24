import asyncio
import time
import logging
from typing import Optional
import cv2
import numpy as np
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from pydantic import BaseModel
from backend.monitoring.runner import task_manager
from backend.vision.camera import camera_stream

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/video", tags=["Video Stream"])


class CameraSourceRequest(BaseModel):
    source: str  # "0", "1", or "http://192.168.1.15:8080/video"


class CameraRotationRequest(BaseModel):
    rotation: int  # 0, 90, 180, 270



def get_standby_frame() -> bytes:
    """Generate sleek standby frame when camera is initializing."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (24, 24, 27)

    # Frame border
    cv2.rectangle(img, (10, 10), (630, 470), (45, 45, 55), 1)

    cv2.putText(img, "OMNISENSE AI - OPTICAL STREAM", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 220, 140), 2, cv2.LINE_AA)
    cv2.putText(img, "Standby: Waiting for video capture / monitoring task...", (30, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(img, f"Time: {timestamp}", (30, 430),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1, cv2.LINE_AA)
    cv2.putText(img, "Status: System Ready", (30, 455),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 100), 1, cv2.LINE_AA)

    _, jpeg = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return jpeg.tobytes()


async def mjpeg_frame_generator(max_frames: Optional[int] = None):
    """
    Generator yielding live annotated MJPEG frames.
    Consumes live annotated frames with bounding boxes, person counts,
    and density levels from active vision tasks.
    Supports max_frames limit for automated test assertions.
    """
    camera_stream.start()
    frames_sent = 0

    while True:
        if max_frames is not None and frames_sent >= max_frames:
            break

        try:
            from backend.monitoring import universal_runner
            frame = universal_runner.get_latest_vision_frame()
            if frame is None:
                try:
                    frame = task_manager.get_latest_vision_frame()
                except Exception:
                    frame = None
            if frame is None:
                ok, raw_frame = camera_stream.get_frame()
                if ok and raw_frame is not None:
                    frame = raw_frame

            if frame is not None:
                ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ret:
                    frame_bytes = jpeg.tobytes()
                else:
                    frame_bytes = get_standby_frame()
            else:
                frame_bytes = get_standby_frame()

            frames_sent += 1
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
            )
        except Exception as e:
            logger.error(f"Error yielding video frame: {e}")
            frame_bytes = get_standby_frame()
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
            )

        await asyncio.sleep(0.066)


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

