"""12 tests for YOLOv8 plate detection (FR-01.1).

Tests skip cleanly if the model file isn't present.
"""
from __future__ import annotations

import numpy as np
import pytest

from tests.conftest import models_present

pytestmark = pytest.mark.skipif(
    not models_present(), reason="YOLOv8 model files not present"
)


@pytest.fixture(scope="module")
def detector():
    from src.detection import PlateDetector
    return PlateDetector()


def test_yolo_loads_correctly(detector):
    assert detector.model is not None


def test_threshold_set_to_default(detector):
    from src.config import PLATE_CONF_THRESHOLD
    assert detector.conf_threshold == PLATE_CONF_THRESHOLD


def test_returns_list_for_blank_frame(detector):
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = detector.detect(blank)
    assert isinstance(detections, list)


def test_empty_frame_returns_empty(detector):
    assert detector.detect(np.array([], dtype=np.uint8).reshape(0, 0, 3)) == []


def test_handles_none_frame(detector):
    assert detector.detect(None) == []


def test_detection_dataclass_shape(detector, sample_plate_image):
    dets = detector.detect(sample_plate_image)
    for d in dets:
        assert hasattr(d, "bbox") and len(d.bbox) == 4
        assert hasattr(d, "confidence")
        assert hasattr(d, "crop")


def test_bbox_within_frame(detector, sample_plate_image):
    h, w = sample_plate_image.shape[:2]
    for d in detector.detect(sample_plate_image):
        x1, y1, x2, y2 = d.bbox
        assert 0 <= x1 < x2 <= w
        assert 0 <= y1 < y2 <= h


def test_confidence_above_threshold(detector, sample_plate_image):
    for d in detector.detect(sample_plate_image):
        assert d.confidence >= detector.conf_threshold


def test_crop_shape_matches_bbox(detector, sample_plate_image):
    for d in detector.detect(sample_plate_image):
        x1, y1, x2, y2 = d.bbox
        assert d.crop.shape[0] == y2 - y1
        assert d.crop.shape[1] == x2 - x1


def test_higher_threshold_yields_fewer_or_equal(sample_plate_image):
    from src.detection import PlateDetector
    a = PlateDetector(conf_threshold=0.30)
    b = PlateDetector(conf_threshold=0.95)
    assert len(b.detect(sample_plate_image)) <= len(a.detect(sample_plate_image))


def test_model_path_attribute(detector):
    assert detector.model_path.exists()


def test_idempotent_on_repeat(detector, sample_plate_image):
    a = detector.detect(sample_plate_image)
    b = detector.detect(sample_plate_image)
    assert len(a) == len(b)
