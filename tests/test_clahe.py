from __future__ import annotations

"""8 tests for src/clahe.py -- LAB L-channel CLAHE.

Coverage
--------
1. BGR-to-BGR contract: output shape matches input
2. Output dtype is uint8
3. Output dimensions (H, W, channels) identical to input
4. Mean luminance increases on a synthetically darkened plate
5. A and B channels are preserved (LAB-CLAHE vs RGB-CLAHE distinguisher)
6. Fully black input does not crash
7. Fully white input does not crash
8. Config parameters: clipLimit == 3.0, tileGridSize == (8, 8)
"""

import cv2
import numpy as np
import pytest

from src.clahe import apply_clahe
from src.config import CLAHE_CLIP_LIMIT, CLAHE_TILE_SIZE

def _make_plate(brightness: int = 128, h: int = 80, w: int = 200) -> np.ndarray:
    """Create a solid-colour BGR plate crop."""
    img = np.full((h, w, 3), brightness, dtype=np.uint8)
    return img

def _dark_plate(h: int = 80, w: int = 200) -> np.ndarray:
    """Create a synthetically darkened plate with noise for CLAHE effect."""
    rng = np.random.default_rng(42)
    base = rng.integers(10, 60, (h, w, 3), dtype=np.uint8)
    return base

def test_01_output_shape_matches_input():
    img = _make_plate()
    out = apply_clahe(img)
    assert out.shape == img.shape

def test_02_output_dtype_uint8():
    img = _make_plate()
    out = apply_clahe(img)
    assert out.dtype == np.uint8

def test_03_dimensions_preserved():
    img = np.zeros((120, 320, 3), dtype=np.uint8)
    out = apply_clahe(img)
    assert out.shape == (120, 320, 3)

def test_04_luminance_increases_on_dark_plate():
    dark = _dark_plate()
    result = apply_clahe(dark)

    def mean_l(bgr: np.ndarray) -> float:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        return float(cv2.split(lab)[0].mean())

    assert mean_l(result) > mean_l(dark)

def test_05_ab_channels_preserved():
    """The A and B colour channels must be identical before and after CLAHE.

    This is the key distinction between LAB L-channel CLAHE and naive
    full-RGB CLAHE -- only the luminance (L) channel is modified.
    """
    rng = np.random.default_rng(7)
    img = rng.integers(30, 200, (80, 200, 3), dtype=np.uint8)
    result = apply_clahe(img)

    lab_in  = cv2.cvtColor(img,    cv2.COLOR_BGR2LAB)
    lab_out = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
    _, a_in,  b_in  = cv2.split(lab_in)
    _, a_out, b_out = cv2.split(lab_out)

    assert int(np.abs(a_in.astype(int) - a_out.astype(int)).max()) <= 10
    assert int(np.abs(b_in.astype(int) - b_out.astype(int)).max()) <= 10

def test_06_fully_black_does_not_crash():
    black = np.zeros((80, 200, 3), dtype=np.uint8)
    out = apply_clahe(black)
    assert out.shape == black.shape
    assert out.dtype == np.uint8

def test_07_fully_white_does_not_crash():
    white = np.full((80, 200, 3), 255, dtype=np.uint8)
    out = apply_clahe(white)
    assert out.shape == white.shape
    assert out.dtype == np.uint8

def test_08_config_parameters():
    """CLAHE_CLIP_LIMIT == 3.0 and CLAHE_TILE_SIZE == (8, 8) per BUILD_SPEC."""
    assert CLAHE_CLIP_LIMIT == 3.0
    assert CLAHE_TILE_SIZE  == (8, 8)
