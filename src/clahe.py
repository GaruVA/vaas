from __future__ import annotations

"""LAB L-channel CLAHE pre-processing for licence plate crops.

Algorithm
---------
1. Convert BGR -> LAB colour space.
2. Apply CLAHE **only on the L (luminance) channel**.
3. Merge back and convert LAB -> BGR.

This is distinct from full-RGB or full-BGR CLAHE: the A and B (colour)
channels are left unchanged, preserving colour saturation while improving
plate character contrast.

Parameters from config:
    CLAHE_CLIP_LIMIT = 3.0
    CLAHE_TILE_SIZE  = (8, 8)

References: section 6.2 of BUILD_SPEC.md
"""

import logging

import cv2
import numpy as np

from src.config import CLAHE_CLIP_LIMIT, CLAHE_TILE_SIZE

logger = logging.getLogger(__name__)

def apply_clahe(plate_crop: np.ndarray) -> np.ndarray:
    """Apply CLAHE to the L channel of a BGR plate-crop image.

    Parameters
    ----------
    plate_crop:
        BGR ``uint8`` image array (H x W x 3).  May be any spatial size.

    Returns
    -------
    np.ndarray
        BGR ``uint8`` image with equalised luminance channel.  Same shape
        and dtype as the input.
    """
    if plate_crop.dtype != np.uint8:
        raise TypeError(f"Expected uint8 input, got {plate_crop.dtype}")
    if plate_crop.ndim != 3 or plate_crop.shape[2] != 3:
        raise ValueError(f"Expected BGR (H,W,3) image, got shape {plate_crop.shape}")

    lab = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_SIZE)
    l_eq = clahe.apply(l_ch)
    lab_eq = cv2.merge((l_eq, a_ch, b_ch))
    return cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)
