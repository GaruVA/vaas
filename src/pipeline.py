from __future__ import annotations

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
    logger.info("Pipeline started: gate=%s direction=%s", gate_id, direction)

    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("Pipeline stop_event set — exiting loop")
            break

        frame = camera.read()
        if frame is None:
            logger.debug("Camera returned None — stopping pipeline")
            break

        if frame_callback is not None:
            try:
                frame_callback(frame)
            except Exception:
                logger.exception("frame_callback raised an exception")

        try:
            detections = detector.detect(frame)
        except Exception:
            logger.exception("Detector raised — skipping frame")
            continue

        if not detections:
            logger.debug("No plates detected in frame")
            continue

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

DEFAULT_COOLDOWN_SECONDS = 3.0

class PlateDebouncer:

    def __init__(self, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS):
        self.cooldown_seconds = cooldown_seconds
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def should_process(self, plate: str) -> bool:
        with self._lock:
            now = time.time()
            last_time = self._last_seen.get(plate, now - self.cooldown_seconds - 1)
            is_fresh = (now - last_time) >= self.cooldown_seconds

            if is_fresh:
                self._last_seen[plate] = now

            return is_fresh

    def snooze(self, plate: str, seconds: float) -> None:
        with self._lock:
            now = time.time()
            self._last_seen[plate] = now - self.cooldown_seconds + seconds

class PlateResult:
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
    results = []
    t_start = time.perf_counter()

    try:
        detections = detector.detect(frame)
    except Exception as exc:
        logger.exception("Detector failed: %s", exc)
        return results

    if not detections:
        return results

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

        if debouncer is not None:
            is_debounced = not debouncer.should_process(raw_plate)

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
    if debounced_indices is None:
        debounced_indices = set()

    output = frame.copy()

    for i, det in enumerate(detections):

        if hasattr(det, "xyxy") and det.xyxy is not None:
            x1, y1, x2, y2 = (int(v) for v in det.xyxy)
        elif hasattr(det, "x1"):
            x1, y1, x2, y2 = int(det.x1), int(det.y1), int(det.x2), int(det.y2)
        elif hasattr(det, "bbox") and det.bbox is not None:
            x1, y1, x2, y2 = (int(v) for v in det.bbox)
        else:
            logger.warning("Detection %d has no bounding box", i)
            continue

        is_debounced = i in debounced_indices
        color = (128, 128, 128) if is_debounced else (0, 255, 0)

        cv2.rectangle(output, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)

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
