"""CLAHE contrast enhancement for plate crops (FR-01.2, §6.2.2).

Motivation and parameter selection
------------------------------------
Sri Lankan industrial facility environments produce significant plate illumination
variation: overexposed reflective plates under direct equatorial sun, underexposed
plates in covered loading bays, and low-contrast plates under overcast monsoon
conditions.  Global histogram equalisation (GHE) amplifies noise under these
conditions because it redistributes pixel intensities across the full dynamic range
without regard to local structure, causing bright halos around plate characters in
high-contrast regions and washing out detail in uniform-illumination areas.

Contrast-Limited Adaptive Histogram Equalisation (CLAHE) (Zuiderveld, 1994) divides
the image into a grid of non-overlapping tiles and performs histogram equalisation
independently in each tile, then bilinearly interpolates across tile boundaries to
eliminate blocking artefacts.  Contrast amplification is capped at a user-specified
clip limit, which suppresses noise amplification in near-uniform regions — the chief
failure mode of GHE on industrial plates.

Parameter selection — CLAHE_CLIP_LIMIT = 3.0, CLAHE_TILE_SIZE = (8, 8) — follows
the systematic grid search reported in §7.2.  On the 150-plate testbed (§7.2),
clip_limit = 3.0 with tile_size = (8, 8) maximised character-classifier accuracy
at 91.3 %, compared with 87.6 % for clip_limit = 2.0 and 89.4 % for clip_limit = 4.0
(the latter over-saturating high-contrast edges).  The (8, 8) tile grid divides a
typical 160×50-pixel plate crop into tiles of approximately 20×6 pixels, matching
the spatial scale of individual plate characters and preserving inter-character
contrast differences.

Colour-space handling — BGR plates are converted to LAB before enhancement.  CLAHE
is applied only to the L (luminance) channel; the a and b chrominance channels are
left unchanged.  This preserves the colour information of the plate background and
characters while enhancing luminance contrast, avoiding the colour-shift artefacts
that occur when CLAHE is applied independently to each BGR channel.

References
----------
Pizer, S. M. et al. (1987) 'Adaptive histogram equalization and its variations',
    Computer Vision, Graphics, and Image Processing, 39(3), pp. 355–368.
Reza, A. M. (2004) 'Realization of the contrast limited adaptive histogram
    equalization (CLAHE) for real-time image enhancement', Journal of VLSI Signal
    Processing Systems, 38(1), pp. 35–44.
Zuiderveld, K. (1994) 'Contrast limited adaptive histogram equalization', in
    Heckbert, P. S. (ed.) Graphics Gems IV. Academic Press, pp. 474–485.
"""
from __future__ import annotations

import cv2
import numpy as np

from src.config import CLAHE_CLIP_LIMIT, CLAHE_TILE_SIZE


def apply_clahe(plate_crop: np.ndarray) -> np.ndarray:
    """Apply CLAHE to a plate crop and return an enhanced BGR uint8 array.

    Accepts grayscale (H×W) or BGR (H×W×3) images.  Colour images are
    processed in LAB colour space — CLAHE is applied to the L (luminance)
    channel only, leaving chrominance channels unchanged to prevent colour
    distortion.  Grayscale images are enhanced directly and converted to BGR
    before return so that all downstream consumers receive a consistent
    three-channel array.

    Parameters
    ----------
    plate_crop : np.ndarray
        Input plate crop as a NumPy uint8 array.  Shape must be (H, W) for
        grayscale or (H, W, 3) for BGR colour.

    Returns
    -------
    np.ndarray
        CLAHE-enhanced plate crop as a BGR uint8 array with the same spatial
        dimensions as the input.

    Raises
    ------
    ValueError
        If *plate_crop* is None, empty, or has an unsupported number of
        channels.

    Examples
    --------
    >>> import numpy as np
    >>> img = np.random.randint(0, 256, (60, 200, 3), dtype=np.uint8)
    >>> out = apply_clahe(img)
    >>> out.shape
    (60, 200, 3)
    >>> out.dtype
    dtype('uint8')
    """
    if plate_crop is None or (hasattr(plate_crop, "size") and plate_crop.size == 0):
        raise ValueError("plate_crop is None or empty")

    img: np.ndarray = np.asarray(plate_crop, dtype=np.uint8)

    if img.size == 0:
        raise ValueError("plate_crop is empty after conversion")

    # Instantiate CLAHE with the empirically selected parameters (§7.2)
    clahe = cv2.createCLAHE(
        clipLimit=float(CLAHE_CLIP_LIMIT),
        tileGridSize=tuple(CLAHE_TILE_SIZE),
    )

    if img.ndim == 2:
        # Grayscale (H×W) — enhance directly, return as BGR
        enhanced = clahe.apply(img)
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    if img.ndim == 3 and img.shape[2] == 1:
        # Single-channel array with redundant dimension — squeeze and process
        enhanced = clahe.apply(img[:, :, 0])
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    if img.ndim == 3 and img.shape[2] == 3:
        # BGR colour image — convert to LAB, enhance L only, convert back
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        l_enhanced = clahe.apply(l_channel)
        lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
        return cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    raise ValueError(
        f"Unsupported image shape {img.shape}: expected (H, W) or (H, W, 3)."
    )
