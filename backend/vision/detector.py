import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from ultralytics import YOLO, YOLOWorld

from backend.config import settings
from backend.monitoring.base import DetectionBox

logger = logging.getLogger(__name__)


class UniversalWorldDetector:
    """
    Open-Vocabulary Vision Detector backed by YOLO-World + OpenVINO Static INT8.

    Tiered Execution:
      - Fast INT8 Path (~172ms CPU): Uses OpenVINO Static INT8 compiled graph
        when all requested classes are covered by the compiled vocabulary.
      - Dynamic Open-Vocabulary Path (~284ms CPU): Uses PyTorch YOLOWorldv2 with
        cached CLIP ViT-B/32 embeddings to encode any arbitrary text target
        (e.g., "ceiling fan", "helmet", "guitar") while preserving base classes.
    """

    _instance: Optional["UniversalWorldDetector"] = None
    _init_lock = threading.Lock()

    DEFAULT_OV_INT8_DIR = "yolov8s-worldv2_int8_openvino_model"
    DEFAULT_WORLD_WEIGHTS = "yolov8s-worldv2.pt"

    def __init__(
        self,
        world_weights: str = DEFAULT_WORLD_WEIGHTS,
        ov_int8_dir: str = DEFAULT_OV_INT8_DIR,
    ):
        self._infer_lock = threading.Lock()
        self.world_weights = world_weights
        self.ov_int8_dir = ov_int8_dir

        self._ov_model: Optional[YOLO] = None
        self._ov_names: Dict[int, str] = {}
        self._ov_name_set: set[str] = set()

        self._world_model: Optional[YOLOWorld] = None
        self._base_txt_feats: Optional[torch.Tensor] = None
        self._base_names: List[str] = []
        self._custom_text_cache: Dict[str, torch.Tensor] = {}
        self._active_custom_classes: List[str] = []

        self._load_models()

    def _load_models(self):
        # 1. Load OpenVINO Static INT8 model if present on disk
        if Path(self.ov_int8_dir).exists():
            try:
                self._ov_model = YOLO(self.ov_int8_dir, task="detect")
                self._ov_names = dict(self._ov_model.names)
                self._ov_name_set = {str(v).lower() for v in self._ov_names.values()}
                logger.info(
                    f"Loaded OpenVINO INT8 detector from '{self.ov_int8_dir}' "
                    f"({len(self._ov_names)} compiled classes)."
                )
            except Exception as e:
                logger.warning(f"Could not load OpenVINO INT8 model ({e}); will use PyTorch YOLOWorld.")
                self._ov_model = None

        # 2. If OpenVINO INT8 wasn't available, eagerly load PyTorch YOLOWorld
        if self._ov_model is None:
            self._ensure_world_model()

    def _ensure_world_model(self):
        if self._world_model is not None:
            return
        logger.info(f"Loading open-vocabulary YOLOWorld model '{self.world_weights}'...")
        self._world_model = YOLOWorld(self.world_weights)
        # Keep immutable copy of pre-baked base text embeddings & class names (80 base classes)
        self._base_txt_feats = self._world_model.model.txt_feats.clone()
        self._base_names = [str(v) for v in self._world_model.names.values()]
        logger.info(f"YOLOWorld ready with {len(self._base_names)} base classes + open CLIP vocabulary.")

    @classmethod
    def get_instance(cls) -> "UniversalWorldDetector":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def is_in_int8_vocabulary(self, classes: Optional[List[str]]) -> bool:
        """Check whether every requested class is already inside the OpenVINO INT8 graph."""
        if not self._ov_model:
            return False
        if not classes:
            return True
        return all(c.strip().lower() in self._ov_name_set for c in classes if c.strip())

    def _bind_custom_classes(self, custom_classes: List[str]):
        """
        Append any custom open-vocabulary classes to the base 80 embeddings
        using cached CLIP text encoding (~150ms per unseen word after CLIP warm-up).
        """
        self._ensure_world_model()
        normalized = []
        base_lower = {b.lower() for b in self._base_names}
        for c in custom_classes:
            clean = c.strip().lower()
            if clean and clean not in base_lower and clean not in normalized:
                normalized.append(clean)

        if normalized == self._active_custom_classes:
            return

        if not normalized:
            # Restore pure base embeddings
            self._world_model.model.txt_feats = self._base_txt_feats.clone()
            self._world_model.model.model[-1].nc = len(self._base_names)
            self._world_model.model.names = {i: n for i, n in enumerate(self._base_names)}
            self._active_custom_classes = []
            return

        feats_to_cat = [self._base_txt_feats]
        unseen = [c for c in normalized if c not in self._custom_text_cache]
        if unseen:
            t0 = time.time()
            encoded = self._world_model.model.get_text_pe(unseen, cache_clip_model=True)
            for idx, label in enumerate(unseen):
                self._custom_text_cache[label] = encoded[:, idx:idx + 1, :].clone()
            logger.info(
                f"Encoded {len(unseen)} open-vocabulary class(es) {unseen} in {(time.time() - t0)*1000:.1f}ms"
            )

        for c in normalized:
            feats_to_cat.append(self._custom_text_cache[c].to(self._base_txt_feats.device))

        combined = torch.cat(feats_to_cat, dim=1)
        all_names = self._base_names + normalized
        self._world_model.model.txt_feats = combined
        self._world_model.model.model[-1].nc = len(all_names)
        self._world_model.model.names = {i: n for i, n in enumerate(all_names)}
        self._active_custom_classes = normalized

    def detect_all(
        self,
        frame: np.ndarray,
        target_classes: Optional[List[str]] = None,
        conf_threshold: float = 0.22,
        imgsz: int = 320,
    ) -> Tuple[List[DetectionBox], str, float]:
        """
        Detect all visible objects in the frame (base scene + any custom target_classes).

        Returns:
            (detections, engine_used, latency_ms)
        """
        if frame is None or frame.size == 0:
            return [], "none", 0.0

        with self._infer_lock:
            t0 = time.time()
            use_int8 = self.is_in_int8_vocabulary(target_classes)

            if use_int8 and self._ov_model is not None:
                model = self._ov_model
                engine = "openvino_int8"
            else:
                self._bind_custom_classes(target_classes or [])
                model = self._world_model
                engine = "yoloworld_open_vocab"

            results = model.predict(
                source=frame,
                conf=conf_threshold,
                imgsz=imgsz,
                verbose=False,
            )
            latency_ms = (time.time() - t0) * 1000

        detections: List[DetectionBox] = []
        if not results:
            return detections, engine, latency_ms

        first_res = results[0]
        boxes = first_res.boxes
        if boxes is None or len(boxes) == 0:
            return detections, engine, latency_ms

        names_map = first_res.names or model.names
        for box in boxes:
            cls_id = int(box.cls[0].item())
            cls_name = str(names_map.get(cls_id, f"object_{cls_id}")).lower()
            conf = float(box.conf[0].item())
            xyxy = box.xyxy[0].tolist()
            x1, y1, x2, y2 = [int(v) for v in xyxy]

            detections.append(
                DetectionBox(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    confidence=round(conf, 3),
                    class_id=cls_id,
                    class_name=cls_name,
                )
            )

        return detections, engine, latency_ms


class PersonDetector:
    """
    Backward-compatible facade delegating to UniversalWorldDetector.
    Preserves existing legacy worker/test contracts without maintaining a separate model.
    """

    _instance: Optional["PersonDetector"] = None

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.YOLO_MODEL_NAME
        self._world = UniversalWorldDetector.get_instance()
        self.person_class_id = 0

    @classmethod
    def get_instance(cls, model_name: Optional[str] = None) -> "PersonDetector":
        if cls._instance is None:
            cls._instance = cls(model_name)
        return cls._instance

    def detect(self, frame: np.ndarray, conf_threshold: float = 0.22, imgsz: int = 320) -> List[DetectionBox]:
        detections, _, _ = self._world.detect_all(frame, target_classes=["person"], conf_threshold=conf_threshold, imgsz=imgsz)
        return [d for d in detections if d.class_name == "person"]

    def detect_classes(
        self,
        frame: np.ndarray,
        target_classes: dict,
        conf_threshold: float = 0.22,
        imgsz: int = 320,
    ) -> List[DetectionBox]:
        wanted = [str(v).lower() for v in target_classes.values()]
        detections, _, _ = self._world.detect_all(frame, target_classes=wanted, conf_threshold=conf_threshold, imgsz=imgsz)
        wanted_set = set(wanted)
        return [d for d in detections if d.class_name in wanted_set]

    def detect_threats(
        self,
        frame: np.ndarray,
        conf_threshold: float = 0.20,
        imgsz: int = 320,
    ) -> Tuple[List[DetectionBox], List[DetectionBox]]:
        threat_labels = ["person", "baseball bat", "knife", "scissors"]
        detections, _, _ = self._world.detect_all(frame, target_classes=threat_labels, conf_threshold=conf_threshold, imgsz=imgsz)
        persons = [d for d in detections if d.class_name == "person"]
        weapons = [d for d in detections if d.class_name in {"baseball bat", "knife", "scissors"}]
        return persons, weapons

    def annotate(
        self,
        frame: np.ndarray,
        detections: List[DetectionBox],
        person_count: int,
        density_level: str = "low",
        fps: float = 0.0,
    ) -> np.ndarray:
        """Draw clean bounding boxes, banners, and density badges on frame."""
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        density_colors = {
            "low": (0, 200, 100),
            "medium": (0, 180, 255),
            "high": (50, 50, 240),
        }
        badge_color = density_colors.get(density_level.lower(), (0, 200, 100))

        for det in detections:
            cv2.rectangle(annotated, (det.x1, det.y1), (det.x2, det.y2), badge_color, 2)
            label = f"{det.class_name.title()} {int(det.confidence * 100)}%"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            tag_y1 = max(det.y1 - 18, 0)
            cv2.rectangle(annotated, (det.x1, tag_y1), (det.x1 + label_size[0] + 6, det.y1), badge_color, -1)
            cv2.putText(
                annotated,
                label,
                (det.x1 + 3, det.y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (w, 50), (20, 20, 25), -1)
        cv2.addWeighted(overlay, 0.75, annotated, 0.25, 0, annotated)

        cv2.putText(annotated, "OMNISENSE VISION", (15, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 240, 180), 2, cv2.LINE_AA)
        cv2.putText(annotated, f"COUNT: {person_count}", (210, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(annotated, f"DENSITY: {density_level.upper()}", (350, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, badge_color, 2, cv2.LINE_AA)

        if fps > 0:
            cv2.putText(annotated, f"{fps:.1f} FPS", (w - 90, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1, cv2.LINE_AA)

        return annotated
