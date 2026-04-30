"""YOLOv8 plate detection - Stage 1 of ALPR pipeline (FR-01.1)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from src.config import PLATE_CONF_THRESHOLD, PLATE_DETECTOR


@dataclass
class PlateDetection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    crop: np.ndarray


class PlateDetector:
    def __init__(self, model_path: Optional[Path] = None,
                 conf_threshold: float = PLATE_CONF_THRESHOLD):
        from ultralytics import YOLO
        self.model_path = Path(model_path) if model_path else PLATE_DETECTOR
        if not self.model_path.exists():
            raise FileNotFoundError(f"Plate detector model not found: {self.model_path}")
        self.model = YOLO(str(self.model_path))
        self.conf_threshold = conf_threshold

    def detect(self, frame: np.ndarray) -> list[PlateDetection]:
        if frame is None or frame.size == 0:
            return []
        results = self.model.predict(frame, verbose=False, conf=self.conf_threshold)
        detections: list[PlateDetection] = []
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                conf = float(box.conf[0]) if box.conf is not None else 0.0
                if conf < self.conf_threshold:
                    continue
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                x1, y1 = max(0, x1), max(0, y1)
                x2 = min(frame.shape[1], x2)
                y2 = min(frame.shape[0], y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                crop = frame[y1:y2, x1:x2].copy()
                detections.append(PlateDetection(
                    bbox=(x1, y1, x2, y2),
                    confidence=conf,
                    crop=crop,
                ))
        return detections
