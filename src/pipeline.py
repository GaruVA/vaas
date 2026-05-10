from __future__ import annotations

"""src/pipeline.py — ALPR pipeline: frame → gate event.

run_pipeline(camera, detector, classifier, attendance_engine,
             gate_id, direction, stop_event, frame_callback) -> None

References: §6.11 of BUILD_SPEC.md.
"""

import logging
import threading
from typing import Callable, Literal

import numpy as np

from src.clahe import apply_clahe

logger = logging.getLogger(__name__)


def run_pipeline(
    camera,
    detector,
    classifier,
    attendance_engine,
    gate_id: str,
    direction: Literal["ENTRY", "EXIT"],
    stop_event: threading.Event | None = None,
    frame_callback: Callable[[np.ndarray], None] | None = None,
) -> None:
    """Run the ALPR recognition loop until *stop_event* is set.

    Each iteration:
    1. Read a frame from *camera*.
    2. Call *frame_callback* (if provided) with the raw frame.
    3. Run plate *detector* → list of detection objects (each with .crop, .confidence).
    4. Apply CLAHE pre-processing to each crop.
    5. Run character *classifier* on each CLAHE crop → raw OCR string.
    6. Call ``attendance_engine.process_gate_event()`` — the engine handles
       LPM-MLED correction internally before writing to the DB.

    Parameters
    ----------
    camera:
        Object exposing ``read() -> np.ndarray | None`` and ``release()``.
    detector:
        Object exposing ``detect(frame) -> list`` where each element has
        ``.crop`` (np.ndarray) and ``.confidence`` (float) attributes.
    classifier:
        Object exposing ``classify(crop: np.ndarray) -> str``.
    attendance_engine:
        ``AttendanceEngine`` instance with an open DB connection.
    gate_id:
        Gate identifier (e.g. ``"GATE-A"``).
    direction:
        ``"ENTRY"`` or ``"EXIT"``.
    stop_event:
        ``threading.Event``; loop exits when set.  Pass ``None`` to run until
        the camera returns ``None``.
    frame_callback:
        Optional callable invoked with each BGR frame before detection.
    """
    logger.info("Pipeline started: gate=%s direction=%s", gate_id, direction)

    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("Pipeline stop_event set — exiting loop")
            break

        frame = camera.read()
        if frame is None:
            logger.debug("Camera returned None — stopping pipeline")
            break

        # Frame callback is called even if no plates are detected
        if frame_callback is not None:
            try:
                frame_callback(frame)
            except Exception:
                logger.exception("frame_callback raised an exception")

        # --- Detection -------------------------------------------------------
        try:
            detections = detector.detect(frame)
        except Exception:
            logger.exception("Detector raised — skipping frame")
            continue

        if not detections:
            logger.debug("No plates detected in frame")
            continue

        # --- Classification --------------------------------------------------
        for det in detections:
            try:
                crop = apply_clahe(det.crop)
                raw_plate = classifier.classify(crop)
            except Exception:
                logger.exception("Classification failed — skipping detection")
                continue

            if not raw_plate:
                logger.debug("Classifier returned empty string")
                continue

            confidence = float(getattr(det, "confidence", 0.0))

            logger.info(
                "Pipeline: raw=%r gate=%s dir=%s conf=%.3f",
                raw_plate, gate_id, direction, confidence,
            )

            # --- Gate event (engine handles LPM-MLED + DB write) -------------
            try:
                attendance_engine.process_gate_event(
                    raw_plate=raw_plate,
                    confidence=confidence,
                    gate_id=gate_id,
                    direction=direction,
                    plate_crop_jpeg_bytes=b"",
                )
            except Exception:
                logger.exception(
                    "process_gate_event raised for raw_plate=%r", raw_plate
                )

    camera.release()
    logger.info("Pipeline stopped: gate=%s direction=%s", gate_id, direction)
