from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

_orig_torch_load = torch.load

def _torch_load_compat(f, *args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _orig_torch_load(f, *args, **kwargs)

torch.load = _torch_load_compat

from src.config import PLATE_DETECTOR, PLATE_CONF_THRESHOLD

logger = logging.getLogger(__name__)

@dataclass
class PlateDetection:
    xyxy: tuple[float, float, float, float]
    confidence: float
    crop: np.ndarray

class PlateDetector:

    def __init__(
        self,
        model_path: Path | None = None,
        conf_threshold: float = PLATE_CONF_THRESHOLD,
    ) -> None:
        path = model_path or PLATE_DETECTOR
        logger.info("Loading plate detector from %s", path)
        self._model = YOLO(str(path))
        self.conf_threshold = conf_threshold

    def detect(self, frame: np.ndarray) -> list[PlateDetection]:
        results = self._model(frame, verbose=False)[0]
        detections: list[PlateDetection] = []
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < self.conf_threshold:
                continue
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            crop = frame[y1:y2, x1:x2].copy()
            detections.append(PlateDetection(
                xyxy=(x1, y1, x2, y2),
                confidence=conf,
                crop=crop,
            ))
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections
