from __future__ import annotations

"""YOLOv8 37-class character classifier (Stage 2 of the ALPR pipeline).

Intentionally imports ``ultralytics`` at module level WITHOUT a try/except
guard -- CI exclusion is by design (see BUILD_SPEC §6.4).

The classifier detects individual characters within a cropped plate image
and sorts them by the **x-coordinate of each bounding-box centre** before
concatenating to form the plate string.

37 classes: 0-9 (10) + A-Z (26) + hyphen '-' (1) = 37.

References: section 6.4 of BUILD_SPEC.md
"""

import logging
from pathlib import Path

import numpy as np
from ultralytics import YOLO

from src.config import CHAR_CLASSIFIER, CHAR_CONF_THRESHOLD

logger = logging.getLogger(__name__)

# 37-class label list ordered to match model training: hyphen first, then 0-9, then A-Z.
# Model class 0 = '-', 1 = '0', ..., 10 = '9', 11 = 'A', ..., 36 = 'Z'
_LABELS: list[str] = ["-"] + [str(i) for i in range(10)] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


class CharClassifier:
    """Wraps the 37-class YOLOv8 character classifier.

    Parameters
    ----------
    model_path:
        Path to ``char_classifier.pt``.  Defaults to config.CHAR_CLASSIFIER.
    conf_threshold:
        Minimum confidence to accept a character detection.
        Defaults to config.CHAR_CONF_THRESHOLD (0.65).
    """

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
        """Classify characters in *plate_crop* and return the plate string.

        Characters are sorted by the x-coordinate of their bounding-box
        centre before concatenation.

        Parameters
        ----------
        plate_crop:
            BGR ``uint8`` crop of the detected plate region.

        Returns
        -------
        str
            Concatenated character string (e.g. ``"WP-CAB-1234"``).
        """
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
        # Sort by x-centre to maintain left-to-right reading order
        chars.sort(key=lambda t: t[0])
        return "".join(c for _, c in chars)
