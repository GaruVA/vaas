from __future__ import annotations

"""src/pipeline.py — ALPR pipeline: frame → gate event.

run_pipeline(camera, detector, classifier, attendance_engine,
             gate_id, direction, stop_event, frame_callback) -> None

References: §6.11 of BUILD_SPEC.md.
"""

import logging
import threading
import time
from typing import Callable, Literal, Optional

import cv2
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


# ---------------------------------------------------------------------------
# Debouncer: prevent rapid re-submission of the same plate
# ---------------------------------------------------------------------------

DEFAULT_COOLDOWN_SECONDS = 3.0


class PlateDebouncer:
    """Rate-limiting cache: track recently seen plates to prevent duplicates."""

    def __init__(self, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS):
        self.cooldown_seconds = cooldown_seconds
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def should_process(self, plate: str) -> bool:
        """Return True if *plate* should be processed (not in cooldown window)."""
        with self._lock:
            now = time.time()
            last_time = self._last_seen.get(plate, now - self.cooldown_seconds - 1)
            is_fresh = (now - last_time) >= self.cooldown_seconds

            if is_fresh:
                self._last_seen[plate] = now

            return is_fresh


# ---------------------------------------------------------------------------
# Frame processing pipeline helper structures
# ---------------------------------------------------------------------------

class PlateResult:
    """Result from detecting and classifying a single plate in a frame."""
    def __init__(
        self,
        plate_detection,
        raw_plate: str,
        confidence: float,
        debounced: bool,
        gate_event: Optional[object] = None,
        timings_ms: Optional[dict] = None,
    ):
        self.plate_detection = plate_detection
        self.raw_plate = raw_plate
        self.confidence = confidence
        self.debounced = debounced
        self.gate_event = gate_event
        self.timings_ms = timings_ms or {}


def process_frame(
    frame: np.ndarray,
    detector,
    classifier,
    engine,
    gate_id: str,
    direction: str,
    debouncer: Optional[PlateDebouncer] = None,
) -> list[PlateResult]:
    """Process a single frame through the full ALPR pipeline.

    Detects plates, classifies them, optionally debounces, and submits to engine.

    Parameters
    ----------
    frame : np.ndarray
        BGR video frame
    detector
        PlateDetector instance with detect(frame) method
    classifier
        CharClassifier instance with classify(crop) method
    engine
        AttendanceEngine instance
    gate_id : str
        Gate identifier (e.g. "GATE-A")
    direction : str
        "ENTRY" or "EXIT"
    debouncer : Optional[PlateDebouncer]
        Optional debouncer to prevent rapid re-submissions

    Returns
    -------
    list[PlateResult]
        List of detection results (including debounced ones)
    """
    results = []
    t_start = time.perf_counter()

    # ── Detection ────────────────────────────────────────────────────────
    try:
        detections = detector.detect(frame)
    except Exception as exc:
        logger.exception("Detector failed: %s", exc)
        return results

    if not detections:
        return results

    # ── Classification & Submission ──────────────────────────────────────
    for det in detections:
        t_det = time.perf_counter()

        try:
            crop = apply_clahe(det.crop)
            raw_plate = classifier.classify(crop)
        except Exception as exc:
            logger.exception("Classification failed: %s", exc)
            continue

        if not raw_plate:
            continue

        confidence = float(getattr(det, "confidence", 0.0))
        is_debounced = False
        gate_event = None
        timings = {}

        # ── Debounce check ───────────────────────────────────────────────
        if debouncer is not None:
            is_debounced = not debouncer.should_process(raw_plate)

        # ── Submit to engine if not debounced ────────────────────────────
        if not is_debounced:
            try:
                t_engine = time.perf_counter()
                gate_event = engine.process_gate_event(
                    raw_plate=raw_plate,
                    confidence=confidence,
                    gate_id=gate_id,
                    direction=direction,
                    plate_crop_jpeg_bytes=b"",
                )
                timings["engine_ms"] = (time.perf_counter() - t_engine) * 1000
            except Exception as exc:
                logger.exception("process_gate_event failed: %s", exc)

        timings["total"] = (time.perf_counter() - t_start) * 1000
        timings["detect_and_classify"] = (time.perf_counter() - t_det) * 1000

        result = PlateResult(
            plate_detection=det,
            raw_plate=raw_plate,
            confidence=confidence,
            debounced=is_debounced,
            gate_event=gate_event,
            timings_ms=timings,
        )
        results.append(result)

    return results


def draw_overlays(
    frame: np.ndarray,
    detections: list,
    labels: Optional[list[str]] = None,
    debounced_indices: Optional[set[int]] = None,
) -> np.ndarray:
    """Draw bounding boxes and labels on a frame.

    Parameters
    ----------
    frame : np.ndarray
        Input BGR frame
    detections : list
        List of detection objects (each with .bbox or .x1, .y1, .x2, .y2)
    labels : Optional[list[str]]
        Optional labels (one per detection); if None, draw confidence scores
    debounced_indices : Optional[set[int]]
        Indices of debounced detections (drawn in grey instead of green)

    Returns
    -------
    np.ndarray
        Annotated frame (copy of input with overlays)
    """
    if debounced_indices is None:
        debounced_indices = set()

    output = frame.copy()

    for i, det in enumerate(detections):
        # Extract bounding box (try multiple attribute names)
        bbox = getattr(det, "bbox", None)
        if bbox is None and hasattr(det, "x1"):
            x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2
        elif bbox is not None:
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        else:
            logger.warning("Detection %d has no bounding box", i)
            continue

        # Color: grey for debounced, green for fresh
        is_debounced = i in debounced_indices
        color = (128, 128, 128) if is_debounced else (0, 255, 0)  # BGR

        # Draw rectangle
        cv2.rectangle(output, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)

        # Draw label
        if labels and i < len(labels):
            label = labels[i]
        else:
            confidence = getattr(det, "confidence", 0.0)
            label = f"{confidence:.2f}"

        cv2.putText(
            output,
            label,
            (int(x1), int(y1) - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
        )

    return output
