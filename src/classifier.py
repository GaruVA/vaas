from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from ultralytics import YOLO

from src.config import CHAR_CLASSIFIER, CHAR_CONF_THRESHOLD

logger = logging.getLogger(__name__)

_LABELS: list[str] = ["-"] + [str(i) for i in range(10)] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

class CharClassifier:

    def __init__(
        self,
        model_path: Path | None = None,
        conf_threshold: float = CHAR_CONF_THRESHOLD,
    ) -> None:
        path = model_path or CHAR_CLASSIFIER
        logger.info("Loading character classifier from %s", path)
        self._model = YOLO(str(path))
        self.conf_threshold = conf_threshold

    def classify(self, plate_crop: np.ndarray) -> str:
        results = self._model(plate_crop, verbose=False)[0]
        chars: list[tuple[float, str]] = []
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < self.conf_threshold:
                continue
            cls_idx = int(box.cls[0])
            label = _LABELS[cls_idx] if cls_idx < len(_LABELS) else "?"
            x1, _, x2, _ = box.xyxy[0]
            centre_x = float((x1 + x2) / 2)
            chars.append((centre_x, label))

        chars.sort(key=lambda t: t[0])
        return "".join(c for _, c in chars)
