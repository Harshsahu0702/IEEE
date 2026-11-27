"""
Universal Motion / Activity Filter.
Runs at ~15 FPS locally using frame differencing.
Only returns True when meaningful motion or scene change is detected,
preventing unnecessary VLM API calls on static / idle frames.
"""

import cv2
import numpy as np
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MotionFilter:
    """
    Lightweight frame-differencing motion detector.

    Strategy:
    - Convert consecutive frames to grayscale.
    - Compute absolute difference between current and previous frame.
    - Apply threshold + contour detection.
    - Only trigger VLM reasoning when motion area exceeds min_area_ratio.
    """

    def __init__(
        self,
        min_area_ratio: float = 0.005,   # 0.5% of frame must change
        sensitivity: int = 25,            # pixel diff threshold (lower = more sensitive)
        blur_radius: int = 5,             # gaussian blur on 160x120 downsampled frame
        downsample_size: tuple[int, int] = (160, 120),
    ):
        self.min_area_ratio = min_area_ratio
        self.sensitivity = sensitivity
        self.blur_radius = blur_radius if blur_radius % 2 == 1 else blur_radius + 1
        self.downsample_size = downsample_size
        self._prev_gray: Optional[np.ndarray] = None
        self._last_motion_score: float = 0.0

    def detect(self, frame: np.ndarray) -> tuple[bool, float, list[tuple[int, int, int, int]]]:
        """
        Analyze a frame for motion using 4x downsampled frame differencing (<1ms CPU).

        Returns:
            (motion_detected: bool, motion_score: float 0.0–1.0, motion_boxes: list of (x1, y1, x2, y2))
        """
        h, w = frame.shape[:2]
        dw, dh = self.downsample_size
        total_pixels = dw * dh
        scale_x = w / float(dw)
        scale_y = h / float(dh)

        small = cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_NEAREST)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.blur_radius, self.blur_radius), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return False, 0.0, []

        diff = cv2.absdiff(self._prev_gray, gray)
        self._prev_gray = gray

        _, thresh = cv2.threshold(diff, self.sensitivity, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_area = 0.0
        motion_boxes = []
        min_box_area = total_pixels * 0.002  # At least 0.2% of downsampled frame

        for c in contours:
            area = cv2.contourArea(c)
            if area >= min_box_area:
                motion_area += area
                bx, by, bw, bh = cv2.boundingRect(c)
                motion_boxes.append((
                    int(bx * scale_x),
                    int(by * scale_y),
                    int((bx + bw) * scale_x),
                    int((by + bh) * scale_y),
                ))

        motion_score = min(motion_area / total_pixels, 1.0)
        self._last_motion_score = motion_score
        motion_detected = motion_score >= self.min_area_ratio

        return motion_detected, motion_score, motion_boxes

    def reset(self):
        """Reset state (call when camera restarts or task changes)."""
        self._prev_gray = None
        self._last_motion_score = 0.0

    @property
    def last_motion_score(self) -> float:
        return self._last_motion_score
