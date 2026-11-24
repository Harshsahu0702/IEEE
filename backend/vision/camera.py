import threading
import time
import logging
from typing import Optional, Tuple
import cv2
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


class CameraStream:
    """
    Threaded non-blocking OpenCV video capture.
    Features:
    - Dedicated capture worker thread
    - Thread-safe latest frame buffer
    - Automatic reconnection with backoff if camera drops
    - Graceful fallback synthetic frame generator if physical camera is unavailable
    """
    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        target_fps: int = 15
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
        self._running = False
        self._is_synthetic = False

        self._synthetic_counter: int = 0
        self._latest_frame: Optional[np.ndarray] = self._generate_synthetic_frame()
        self._last_frame_time: float = time.time()

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
        """Starts the capture background thread."""
        if self._running:
            return
        self._running = True
        self._init_camera()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="CameraCaptureThread")
        self._thread.start()
        logger.info(f"Camera stream started (source={self.camera_source}, synthetic_mode={self._is_synthetic})")

    def _init_camera(self) -> bool:
        """Attempt to open physical OpenCV VideoCapture or IP camera URL."""
        source = self.camera_source
        try:
            cap = None
            if isinstance(source, int):
                # On Windows, try DirectShow (CAP_DSHOW) first for reliable low-latency hardware access
                try:
                    cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap = None
                except Exception:
                    cap = None

            if cap is None:
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
        """Continuous background capture loop with auto-reconnection."""
        retry_delay = 2.0

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
                    with self._lock:
                        self._latest_frame = frame
                        self._last_frame_time = time.time()
                else:
                    logger.warning("Camera read failed. Attempting reconnect...")
                    self._cap.release()
                    self._cap = None
                    time.sleep(retry_delay)
                    self._init_camera()
            else:
                # Generate synthetic frame if no physical camera
                frame = self._generate_synthetic_frame()
                with self._lock:
                    self._latest_frame = frame
                    self._last_frame_time = time.time()

            # Maintain target FPS
            elapsed = time.time() - start_time
            sleep_time = self.frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def get_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Non-blocking retrieval of latest frame."""
        with self._lock:
            if self._latest_frame is None:
                return False, None
            return True, self._latest_frame.copy()

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
