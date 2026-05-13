from __future__ import annotations

"""YOLOv8 licence plate detector (Stage 1 of the ALPR pipeline).

Intentionally imports ``ultralytics`` at module level WITHOUT a try/except
guard.  In CI (no GPU, no ultralytics installed) this module fails at import
-- which is by design.  ``test_detection.py`` is excluded from the non-YOLO
test count.

References: section 6.4 of BUILD_SPEC.md
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

# PyTorch 2.6+ changed weights_only default to True.  Ultralytics checkpoint
# files embed many torch internal classes that aren't in the default allowlist.
# Rather than enumerate every class, we patch torch.load so that calls without
# an explicit weights_only argument (i.e. the YOLO loader) fall back to False.
# This is safe here because plate_detector.pt is a trusted local asset.
_orig_torch_load = torch.load

def _torch_load_compat(f, *args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _orig_torch_load(f, *args, **kwargs)

torch.load = _torch_load_compat

from src.config import PLATE_DETECTOR, PLATE_CONF_THRESHOLD

logger = logging.getLogger(__name__)


@dataclass
class PlateDetection:
    """A single detected licence plate bounding box."""
    xyxy: tuple[float, float, float, float]
    confidence: float
    crop: np.ndarray


class PlateDetector:
    """Wraps YOLOv8n plate detector.

    Parameters
    ----------
    model_path:
        Path to the ``plate_detector.pt`` weights file.
        Defaults to ``src.config.PLATE_DETECTOR``.
    conf_threshold:
        Minimum confidence to accept a detection.
        Defaults to ``src.config.PLATE_CONF_THRESHOLD`` (0.70).
    """

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
        """Run inference on *frame* and return bounding boxes above threshold.

        Parameters
        ----------
        frame:
            BGR ``uint8`` image (H x W x 3).

        Returns
        -------
        list[PlateDetection]
            Detections sorted by descending confidence.
        """
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
