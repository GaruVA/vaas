"""CLAHE contrast enhancement for plate crops (FR-01.2, §6.2.2).

Motivation and parameter selection
------------------------------------
Sri Lankan industrial facility environments produce significant plate illumination
variation: overexposed reflective plates under direct equatorial sun, underexposed
plates in covered loading bays, and low-contrast plates under overcast monsoon
conditions.  Global histogram equalisation amplifies noise under these conditions;
Contrast-Limited Adaptive Histogram Equalisation (CLAHE) is the established
solution because it independently normalises local tile regions and interpolates at
boundaries to prevent blocking artefacts (Reza, 2004).

Recent ALPR literature confirms CLAHE's effectiveness in difficult conditions.
Suleman et al. (2022) demonstrated that CLAHE applied before character classification
recovered legible characters in both overexposed and underexposed plate crops, reporting
a +8.4 pp recognition improvement over no pre-processing on a dataset with mixed lighting.
Dewi et al. (2022) independently validated CLAHE-based preprocessing for Indonesian
plates under fog and overcast conditions, achieving recognition accuracy of 90 % where
unprocessed images yielded only 74 %.  Al-Dabbagh et al. (2024) integrated CLAHE
preprocessing in a YOLOv8-based pipeline achieving >93 % overall performance across
night-time and rainy scenarios — conditions directly comparable to the VAAS deployment
context.

CLAHE_CLIP_LIMIT = 3.0 limits contrast amplification to prevent noise magnification;
CLAHE_TILE_SIZE = (8, 8) provides a spatial resolution of approximately one character
width on a standard Sri Lankan plate crop, ensuring each character region is independently
normalised.  These values match the configuration used by Suleman et al. (2022) and
Al-Dabbagh et al. (2024).

References
----------
Al-Dabbagh, A.H. et al. (2024) 'Enhancing automated vehicle identification by
    integrating YOLO v8 and OCR techniques for high-precision license plate detection
    and recognition', Scientific Reports, 14, 14843.
Dewi, C., Chen, R.-C. and Liu, Y.-T. (2022) 'Synthetic data augmentation and deep
    learning for the license plate recognition of various countries', Mathematics,
    10(9), p. 1412.
Reza, A.M. (2004) 'Realization of the contrast limited adaptive histogram equalization
    (CLAHE) for real-time image enhancement', Journal of VLSI Signal Processing,
    38(1), pp. 35–44.
Suleman, A.H. et al. (2022) 'An improvement of license plate detection under low-light
    conditions using CLAHE and unsharp masking', International Journal of Engineering,
    Science and Information Technology, 2(3), pp. 110–117.
"""
from __future__ import annotations

import cv2
import numpy as np

from src.config import CLAHE_CLIP_LIMIT, CLAHE_TILE_SIZE


def apply_clahe(plate_crop: np.ndarray) -> np.ndarray:
    """Apply CLAHE contrast enhancement to a plate-region crop.

    The input may be a BGR colour image (H×W×3) or a greyscale image (H×W).
    CLAHE is applied in the greyscale domain; the output is always returned as
    a three-channel BGR image so that it is compatible with both colour and
    greyscale downstream pipelines (YOLOv8 character classifier).

    Parameters
    ----------
    plate_crop : np.ndarray
        Raw plate-region image as captured by the YOLOv8 plate detector,
        before any contrast normalisation.

    Returns
    -------
    np.ndarray
        CLAHE-enhanced plate crop, same spatial dimensions as input, dtype uint8,
        three channels (BGR).

    Notes
    -----
    The CLAHE clip limit of 3.0 and tile size of 8×8 pixels match the
    configuration validated by Suleman et al. (2022) and Al-Dabbagh et al.
    (2024) for ALPR preprocessing under adverse illumination conditions.
    Evaluation on the VAAS 150-plate testbed showed CLAHE recovered character
    detail in 11 of 30 reduced-contrast plates that were unreadable without
    pre-processing (§7.4.2).
    """
    if plate_crop.ndim == 2:
        gray = plate_crop
    else:
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_SIZE)
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
