"""CLAHE contrast enhancement (FR-01.2, §6.2.2)."""
from __future__ import annotations

import cv2
import numpy as np

from src.config import CLAHE_CLIP_LIMIT, CLAHE_TILE_SIZE


def apply_clahe(plate_crop: np.ndarray) -> np.ndarray:
    if plate_crop.ndim == 2:
        gray = plate_crop
    else:
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_SIZE)
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
