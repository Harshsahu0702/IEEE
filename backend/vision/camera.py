import collections
import threading
import time
import logging
from typing import Optional, Tuple, List
import cv2
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


class CameraStream:
    """
    Threaded non-blocking OpenCV video capture.
    Features:
    - Unified 20 FPS capture clock (50ms interval)
    - Zero-copy read-only latest frame buffer
    - Producer-side cached JPEG broadcast buffer (encodes once per frame)
    - Rolling temporal ring buffer for multi-frame event context
    - Automatic reconnection with backoff if camera drops
    - Graceful fallback synthetic frame generator if physical camera is unavailable
    """
    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        target_fps: int = 20
    ):
        self.camera_source = camera_index
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.target_fps = target_fps
        self.frame_interval = 1.0 / max(target_fps, 1)
        self.rotation: int = 0  # 0, 90, 180, 270 degrees

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._jpeg_lock = threading.Lock()
        self._running = False
        self._is_synthetic = False

        self._synthetic_counter: int = 0
        self._frame_id: int = 0
        self._last_frame_time: float = time.time()
        self._latest_timestamp_ms: float = self._last_frame_time * 1000.0

        init_frame = self._generate_synthetic_frame()
        init_frame.flags.writeable = False
        self._latest_frame: Optional[np.ndarray] = init_frame

        # Cached JPEG broadcast state
        self._cached_jpeg_id: int = -1
        self._cached_jpeg_bytes: Optional[bytes] = None
        self._last_raw_jpeg_req: float = 0.0

        # Rolling temporal ring buffer (sampled at 5 Hz -> 20 frames for 4s)
        ring_len = max(5, 5 * getattr(settings, "RING_BUFFER_SECONDS", 4))
        self._ring_buffer: collections.deque[Tuple[float, bytes]] = collections.deque(maxlen=ring_len)
        self._ring_sample_step: int = max(1, self.target_fps // 5)

    def set_source(self, source) -> Tuple[bool, str]:
        """
        Dynamically switch camera source between webcam index (e.g. 0, 1)
        and mobile phone IP camera URL (e.g. 'http://192.168.1.15:8080/video').
        """
        if isinstance(source, str) and source.strip().isdigit():
            source = int(source.strip())
        elif isinstance(source, str):
            source = source.strip()

        with self._lock:
            self.camera_source = source
            self.camera_index = source if isinstance(source, int) else 0

            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

            ok = self._init_camera()
            mode = "Physical Webcam / Phone Stream Live" if ok else "Synthetic Fallback Mode"
            msg = f"Camera switched to '{source}' ({mode})"
            logger.info(msg)
            return ok, msg

    def set_rotation(self, deg: int) -> int:
        """Set video frame rotation angle in degrees (0, 90, 180, 270)."""
        with self._lock:
            self.rotation = int(deg) % 360
            logger.info(f"Camera rotation set to {self.rotation} degrees")
            return self.rotation

    def start(self):
        """Starts the capture background thread (non-blocking)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="CameraCaptureThread")
        self._thread.start()
        logger.info(f"Camera stream thread launched (source={self.camera_source}, target_fps={self.target_fps})")

    def _init_camera(self) -> bool:
        """Attempt to open physical OpenCV VideoCapture or IP camera URL with timeout guard."""
        source = self.camera_source
        try:
            cap = None
            if isinstance(source, int):
                # On Windows, try DirectShow (CAP_DSHOW) first for reliable low-latency hardware access
                try:
                    cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap.release()
                        cap = None
                except Exception:
                    cap = None

            if cap is None:
                try:
                    cap = cv2.VideoCapture(source, cv2.CAP_ANY, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000])
                except Exception:
                    cap = cv2.VideoCapture(source)

            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                cap.set(cv2.CAP_PROP_FPS, self.target_fps)
                # Lower buffer size for zero-latency IP streams
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                ret, frame = cap.read()
                if ret and frame is not None:
                    self._cap = cap
                    self._is_synthetic = False
                    logger.info(f"Camera initialized successfully on source: {source}")
                    return True
                cap.release()
        except Exception as e:
            logger.warning(f"Error opening camera source {source}: {e}")

        logger.info(f"Camera source '{source}' not accessible; activating synthetic optical generator.")
        self._cap = None
        self._is_synthetic = True
        return False


    def _generate_synthetic_frame(self) -> np.ndarray:
        """Generates a dynamic simulated test scene with moving shapes."""
        self._synthetic_counter += 1
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        # Background gradient
        frame[:] = (30, 32, 38)

        # Draw simulated room environment grid
        for x in range(0, self.width, 40):
            cv2.line(frame, (x, 0), (x, self.height), (40, 42, 50), 1)
        for y in range(0, self.height, 40):
            cv2.line(frame, (0, y), (self.width, y), (40, 42, 50), 1)

        # Draw a simulated moving person silhouette to allow YOLO to detect or test
        offset = int(np.sin(self._synthetic_counter * 0.1) * 120)
        center_x = (self.width // 2) + offset
        center_y = self.height // 2

        # Draw silhouette representation
        cv2.circle(frame, (center_x, center_y - 70), 30, (180, 180, 180), -1)  # Head
        cv2.ellipse(frame, (center_x, center_y + 30), (45, 80), 0, 0, 360, (180, 180, 180), -1)  # Body

        # Status text
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, "OPTICAL FEED [SYNTHETIC / NO HARDWARE WEBCAM]", (25, 450),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Time: {timestamp}", (25, 470),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
        return frame

    def _capture_loop(self):
        """Continuous background capture loop at unified 20 FPS with auto-reconnection."""
        retry_delay = 2.0
        if self._cap is None and not self._is_synthetic:
            self._init_camera()

        while self._running:
            start_time = time.time()

            if self._cap is not None and self._cap.isOpened():
                ret, frame = self._cap.read()
                if ret and frame is not None:
                    frame = cv2.flip(frame, 1)  # Horizontal mirror (side-wise inversion)
                    if self.rotation == 90:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                    elif self.rotation == 180:
                        frame = cv2.rotate(frame, cv2.ROTATE_180)
                    elif self.rotation == 270:
                        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    self._publish_frame(frame)
                else:
                    logger.warning("Camera read failed. Attempting reconnect...")
                    self._cap.release()
                    self._cap = None
                    time.sleep(retry_delay)
                    self._init_camera()
            else:
                # Generate synthetic frame if no physical camera
                frame = self._generate_synthetic_frame()
                self._publish_frame(frame)

            # Maintain unified target FPS (50ms at 20 FPS)
            elapsed = time.time() - start_time
            sleep_time = self.frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _publish_frame(self, frame: np.ndarray):
        """Store frame as zero-copy read-only view and update ring buffer / broadcast cache."""
        now = time.time()
        ts_ms = now * 1000.0
        frame.flags.writeable = False

        with self._lock:
            self._latest_frame = frame
            self._frame_id += 1
            fid = self._frame_id
            self._last_frame_time = now
            self._latest_timestamp_ms = ts_ms

        # Sample into temporal ring buffer at 5 Hz (always include very first frame)
        need_ring = (len(self._ring_buffer) == 0) or (fid % self._ring_sample_step == 0)
        need_raw_stream = (now - self._last_raw_jpeg_req) < 2.0

        if need_ring or need_raw_stream:
            quality = getattr(settings, "JPEG_QUALITY", 75)
            ret, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if ret:
                jpeg_bytes = buf.tobytes()
                if need_ring:
                    self._ring_buffer.append((ts_ms, jpeg_bytes))
                if need_raw_stream:
                    with self._jpeg_lock:
                        self._cached_jpeg_id = fid
                        self._cached_jpeg_bytes = jpeg_bytes

    def get_frame(self, copy: bool = False) -> Tuple[bool, Optional[np.ndarray]]:
        """Non-blocking retrieval of latest frame (zero-copy read-only by default)."""
        with self._lock:
            if self._latest_frame is None:
                return False, None
            return True, self._latest_frame.copy() if copy else self._latest_frame

    def get_frame_meta(self) -> Tuple[bool, Optional[np.ndarray], int, float]:
        """Non-blocking retrieval of latest read-only frame with monotonic ID and timestamp_ms."""
        with self._lock:
            if self._latest_frame is None:
                return False, None, -1, 0.0
            return True, self._latest_frame, self._frame_id, self._latest_timestamp_ms

    def get_latest_jpeg(self) -> Tuple[Optional[bytes], int, float]:
        """Return cached pre-encoded JPEG bytes for raw stream fallback (encodes once per frame_id)."""
        self._last_raw_jpeg_req = time.time()
        with self._lock:
            frame = self._latest_frame
            fid = self._frame_id
            ts_ms = self._latest_timestamp_ms

        if frame is None:
            return None, -1, 0.0

        with self._jpeg_lock:
            if self._cached_jpeg_id == fid and self._cached_jpeg_bytes is not None:
                return self._cached_jpeg_bytes, fid, ts_ms
            quality = getattr(settings, "JPEG_QUALITY", 75)
            ret, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if ret:
                self._cached_jpeg_id = fid
                self._cached_jpeg_bytes = buf.tobytes()
                return self._cached_jpeg_bytes, fid, ts_ms
            return None, -1, 0.0

    def get_ring_buffer_frames(self, max_frames: int = 3) -> List[Tuple[float, bytes]]:
        """Extract evenly spaced historical frames from the temporal ring buffer."""
        buf = list(self._ring_buffer)
        if not buf:
            return []
        if len(buf) <= max_frames:
            return buf
        indices = np.linspace(0, len(buf) - 1, max_frames, dtype=int)
        return [buf[i] for i in indices]

    @property
    def is_synthetic(self) -> bool:
        return self._is_synthetic

    def stop(self):
        """Stops capture loop and releases camera resources."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info("Camera stream stopped.")


# Singleton camera stream instance
camera_stream = CameraStream(
    camera_index=settings.CAMERA_INDEX,
    width=settings.FRAME_WIDTH,
    height=settings.FRAME_HEIGHT,
    target_fps=settings.TARGET_FPS
)
