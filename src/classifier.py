"""YOLOv8 character classification - Stage 2 of ALPR pipeline (FR-01.3)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from src.config import CHAR_CONF_THRESHOLD, CHAR_CLASSIFIER


class CharClassifier:
    def __init__(self, model_path: Optional[Path] = None,
                 conf_threshold: float = CHAR_CONF_THRESHOLD):
        from ultralytics import YOLO
        self.model_path = Path(model_path) if model_path else CHAR_CLASSIFIER
        if not self.model_path.exists():
            raise FileNotFoundError(f"Character classifier model not found: {self.model_path}")
        self.model = YOLO(str(self.model_path))
        self.conf_threshold = conf_threshold

    def classify(self, plate_crop: np.ndarray) -> tuple[str, float]:
        if plate_crop is None or plate_crop.size == 0:
            return "", 0.0
        results = self.model.predict(plate_crop, verbose=False, conf=self.conf_threshold)
        chars: list[tuple[int, str, float]] = []
        for r in results:
            if r.boxes is None:
                continue
            names = r.names if hasattr(r, "names") else {}
            for box in r.boxes:
                conf = float(box.conf[0]) if box.conf is not None else 0.0
                if conf < self.conf_threshold:
                    continue
                cls_id = int(box.cls[0]) if box.cls is not None else -1
                label = names.get(cls_id, str(cls_id))
                # The 37-class model's "background" class should be ignored.
                if label.lower() in ("background", "bg", "_"):
                    continue
                xyxy = box.xyxy[0].cpu().numpy()
                x_centre = int((xyxy[0] + xyxy[2]) / 2)
                chars.append((x_centre, label, conf))
        if not chars:
            return "", 0.0
        chars.sort(key=lambda c: c[0])
        plate_str = "".join(c[1] for c in chars)
        mean_conf = float(np.mean([c[2] for c in chars]))
        return plate_str, mean_conf
