import time
import logging
from typing import List, Tuple, Optional
import cv2
import numpy as np
from ultralytics import YOLO

from backend.config import settings
from backend.monitoring.base import DetectionBox

logger = logging.getLogger(__name__)


class PersonDetector:
    """
    YOLOv8n Person Detector.
    Strict Rules:
    - Pretrained yolov8n only
    - Person class only (COCO class 0)
    - Lazy-loaded once (singleton)
    - No face recognition, no identity tracking
    """
    _instance: Optional["PersonDetector"] = None

    def __init__(self, model_name: str = "yolov8n.pt"):
        self.model_name = model_name
        logger.info(f"Loading YOLOv8 detector from {model_name}...")
        self.model = YOLO(model_name)
        # Person class index in standard COCO dataset is 0
        self.person_class_id = 0
        logger.info("YOLOv8 detector loaded successfully (person class filter active).")

    @classmethod
    def get_instance(cls, model_name: Optional[str] = None) -> "PersonDetector":
        """Lazy-load singleton instance."""
        if cls._instance is None:
            name = model_name or settings.YOLO_MODEL_NAME
            cls._instance = cls(name)
        return cls._instance

    def detect(self, frame: np.ndarray, conf_threshold: float = 0.22, imgsz: int = 480) -> List[DetectionBox]:
        """
        Run person detection on a BGR frame.
        Returns list of DetectionBox items for class 0 (person) only.
        Uses imgsz=480 for enhanced feature recall on challenging poses/orientations.
        """
        if frame is None or frame.size == 0:
            return []

        # Run inference filtering for person class (classes=[0])
        results = self.model.predict(
            source=frame,
            classes=[self.person_class_id],
            conf=conf_threshold,
            imgsz=imgsz,
            verbose=False
        )


        detections: List[DetectionBox] = []
        if not results:
            return detections

        first_res = results[0]
        boxes = first_res.boxes
        if boxes is None or len(boxes) == 0:
            return detections

        for box in boxes:
            cls_id = int(box.cls[0].item())
            if cls_id != self.person_class_id:
                continue

            conf = float(box.conf[0].item())
            xyxy = box.xyxy[0].tolist()
            x1, y1, x2, y2 = [int(v) for v in xyxy]

            detections.append(DetectionBox(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                confidence=round(conf, 3),
                class_id=self.person_class_id,
                class_name="person"
            ))

        return detections

    def detect_threats(
        self,
        frame: np.ndarray,
        conf_threshold: float = 0.20,
        imgsz: int = 480
    ) -> Tuple[List[DetectionBox], List[DetectionBox]]:
        """
        Detects persons and weapon/threat objects (knife, baseball bat, scissors).
        Returns: (persons, weapons)
        """
        if frame is None or frame.size == 0:
            return [], []

        threat_classes = {
            0: "person",
            34: "baseball bat",
            43: "knife",
            76: "scissors"
        }

        results = self.model.predict(
            source=frame,
            classes=list(threat_classes.keys()),
            conf=conf_threshold,
            imgsz=imgsz,
            verbose=False
        )

        persons: List[DetectionBox] = []
        weapons: List[DetectionBox] = []

        if not results or not results[0].boxes:
            return persons, weapons

        for box in results[0].boxes:
            cls_id = int(box.cls[0].item())
            if cls_id not in threat_classes:
                continue

            conf = float(box.conf[0].item())
            xyxy = box.xyxy[0].tolist()
            x1, y1, x2, y2 = [int(v) for v in xyxy]

            det = DetectionBox(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                confidence=round(conf, 3),
                class_id=cls_id,
                class_name=threat_classes[cls_id]
            )

            if cls_id == 0:
                persons.append(det)
            else:
                weapons.append(det)

        return persons, weapons

    def annotate(
        self,
        frame: np.ndarray,
        detections: List[DetectionBox],
        person_count: int,
        density_level: str = "low",
        fps: float = 0.0
    ) -> np.ndarray:
        """
        Draw clean bounding boxes, banners, and density badges on frame.
        No face recognition, identity tags, or biometric labels are drawn.
        """
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # Choose color scheme based on density
        density_colors = {
            "low": (0, 200, 100),       # Green
            "medium": (0, 180, 255),    # Amber
            "high": (50, 50, 240)       # Red
        }
        badge_color = density_colors.get(density_level.lower(), (0, 200, 100))

        # 1. Draw person bounding boxes
        for det in detections:
            cv2.rectangle(
                annotated,
                (det.x1, det.y1),
                (det.x2, det.y2),
                badge_color,
                2
            )
            # Confidence tag only (NO identity)
            label = f"Person {int(det.confidence * 100)}%"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            tag_y1 = max(det.y1 - 18, 0)
            tag_y2 = det.y1
            cv2.rectangle(
                annotated,
                (det.x1, tag_y1),
                (det.x1 + label_size[0] + 6, tag_y2),
                badge_color,
                -1
            )
            cv2.putText(
                annotated,
                label,
                (det.x1 + 3, det.y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )

        # 2. Top Header HUD Banner
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (w, 50), (20, 20, 25), -1)
        cv2.addWeighted(overlay, 0.75, annotated, 0.25, 0, annotated)

        # HUD Text: Title, Person Count, Density Badge, FPS
        cv2.putText(
            annotated,
            "OMNISENSE VISION",
            (15, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 240, 180),
            2,
            cv2.LINE_AA
        )

        count_text = f"COUNT: {person_count}"
        cv2.putText(
            annotated,
            count_text,
            (210, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        density_text = f"DENSITY: {density_level.upper()}"
        cv2.putText(
            annotated,
            density_text,
            (350, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            badge_color,
            2,
            cv2.LINE_AA
        )

        if fps > 0:
            fps_text = f"{fps:.1f} FPS"
            cv2.putText(
                annotated,
                fps_text,
                (w - 90, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (180, 180, 180),
                1,
                cv2.LINE_AA
            )

        return annotated
