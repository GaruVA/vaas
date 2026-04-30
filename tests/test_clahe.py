"""8 tests for CLAHE (FR-01.2)."""
from __future__ import annotations

import cv2
import numpy as np

from src.clahe import apply_clahe


def test_output_shape_matches_input(sample_plate_image):
    out = apply_clahe(sample_plate_image)
    assert out.shape == sample_plate_image.shape


def test_output_dtype_uint8(sample_plate_image):
    assert apply_clahe(sample_plate_image).dtype == np.uint8


def test_grayscale_input_handled():
    gray = np.full((50, 100), 120, dtype=np.uint8)
    out = apply_clahe(gray)
    assert out.shape == (50, 100, 3)


def test_low_contrast_input_increases_contrast():
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    img[40:60, 40:60] = 138  # subtle bump
    enh = apply_clahe(img)
    g_in = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g_out = cv2.cvtColor(enh, cv2.COLOR_BGR2GRAY)
    assert g_out.std() >= g_in.std()


def test_returns_3channel_bgr(sample_plate_image):
    out = apply_clahe(sample_plate_image)
    assert out.ndim == 3 and out.shape[2] == 3


def test_idempotent_on_uniform_image():
    img = np.full((20, 20, 3), 200, dtype=np.uint8)
    out = apply_clahe(img)
    assert out.shape == img.shape


def test_handles_small_crop():
    img = np.full((10, 10, 3), 100, dtype=np.uint8)
    out = apply_clahe(img)
    assert out.shape == (10, 10, 3)


def test_output_range_valid():
    img = np.random.randint(0, 256, (60, 200, 3), dtype=np.uint8)
    out = apply_clahe(img)
    assert out.min() >= 0 and out.max() <= 255
