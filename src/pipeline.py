"""End-to-end ALPR pipeline: frame -> plate -> gate event (§5.3)."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import cv2
import numpy as np

from src.attendance import AttendanceEngine, GateEventResult
from src.classifier import CharClassifier
from src.clahe import apply_clahe
from src.detection import PlateDetection, PlateDetector

logger = logging.getLogger(__name__)

# Default debounce window in seconds (configurable via PlateDebouncer constructor)
DEFAULT_COOLDOWN_SECONDS = 15


class PlateDebouncer:
    """Prevents the same plate from being submitted to the attendance engine
    multiple times within *cooldown_seconds*.

    Thread-safe — the CameraWorker runs in a background daemon thread.

    Debouncing rules
    ----------------
    * A plate string is considered "seen" once ``record(plate)`` is called.
    * Any subsequent ``is_duplicate(plate)`` call within the cooldown window
      returns ``True`` — the caller should skip the event.
    * After the cooldown expires the plate is eligible again (e.g., a genuine
      second entry on the next shift or a vehicle that left and returned).
    * The internal registry is pruned on every ``is_duplicate`` call so memory
      does not grow unbounded during long sessions.
    """

    def __init__(self, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS) -> None:
        self.cooldown = cooldown_seconds
        self._last_seen: dict[str, float] = {}   # plate → monotonic timestamp
        self._lock = threading.Lock()

    def is_duplicate(self, plate: str) -> bool:
        """Return True if *plate* was processed within the cooldown window."""
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            last = self._last_seen.get(plate)
            return last is not None and (now - last) < self.cooldown

    def record(self, plate: str) -> None:
        """Mark *plate* as just-processed."""
        now = time.monotonic()
        with self._lock:
            self._last_seen[plate] = now

    def reset(self, plate: str) -> None:
        """Explicitly clear a plate's cooldown (e.g., after manual disposition)."""
        with self._lock:
            self._last_seen.pop(plate, None)

    def _prune(self, now: float) -> None:
        """Remove entries that have expired (must be called under self._lock)."""
        cutoff = now - self.cooldown
        expired = [p for p, t in self._last_seen.items() if t < cutoff]
        for p in expired:
            del self._last_seen[p]

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._last_seen)


@dataclass
class PipelineResult:
    plate_detection: PlateDetection
    raw_plate: str
    confidence: float
    gate_event: Optional[GateEventResult]
    timings_ms: dict
    debounced: bool = False   # True when the plate was suppressed by debouncer


def process_frame(frame: np.ndarray,
                  detector: PlateDetector,
                  classifier: CharClassifier,
                  engine: AttendanceEngine,
                  gate_id: str,
                  direction: str,
                  debouncer: Optional[PlateDebouncer] = None) -> list[PipelineResult]:
    """Process one camera frame through the full ALPR pipeline.

    Args:
        debouncer: If provided, plates seen within the cooldown window are
                   skipped — the returned PipelineResult has debounced=True
                   and gate_event=None for those entries.
    """
    results: list[PipelineResult] = []
    if frame is None:
        return results

    t0 = time.perf_counter()
    detections = detector.detect(frame)
    t1 = time.perf_counter()

    for det in detections:
        enhanced = apply_clahe(det.crop)
        t2 = time.perf_counter()
        raw, conf = classifier.classify(enhanced)
        t3 = time.perf_counter()
        if not raw:
            continue

        # ── Debounce check ────────────────────────────────────────────────
        if debouncer is not None and debouncer.is_duplicate(raw):
            logger.debug("[%s] DEBOUNCED %s (within %ss cooldown)",
                         gate_id, raw, debouncer.cooldown)
            results.append(PipelineResult(
                plate_detection=det,
                raw_plate=raw,
                confidence=conf,
                gate_event=None,
                timings_ms={},
                debounced=True,
            ))
            continue

        ok, jpg = cv2.imencode(".jpg", det.crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        jpeg_bytes = jpg.tobytes() if ok else b""
        evt = engine.process_gate_event(raw, conf, gate_id, direction, jpeg_bytes)
        t4 = time.perf_counter()

        # Record in debouncer AFTER a successful engine call
        if debouncer is not None:
            debouncer.record(raw)

        results.append(PipelineResult(
            plate_detection=det,
            raw_plate=raw,
            confidence=conf,
            gate_event=evt,
            timings_ms={
                "detect":   round((t1 - t0) * 1000, 1),
                "clahe":    round((t2 - t1) * 1000, 1),
                "classify": round((t3 - t2) * 1000, 1),
                "engine":   round((t4 - t3) * 1000, 1),
                "total":    round((t4 - t0) * 1000, 1),
            },
        ))

    return results


def run_pipeline(camera,
                 detector: PlateDetector,
                 classifier: CharClassifier,
                 engine: AttendanceEngine,
                 gate_id: str,
                 direction: str,
                 debouncer: Optional[PlateDebouncer] = None,
                 frame_callback: Optional[Callable[[np.ndarray, list[PlateDetection]], None]] = None,
                 stop_event=None,
                 max_frames: Optional[int] = None) -> int:
    """Continuous pipeline loop (used by run_demo.py and tests)."""
    if debouncer is None:
        debouncer = PlateDebouncer()
    n = 0
    while True:
        if stop_event is not None and stop_event.is_set():
            break
        if max_frames is not None and n >= max_frames:
            break
        frame = camera.read()
        if frame is None:
            break
        results = process_frame(frame, detector, classifier, engine,
                                gate_id, direction, debouncer)
        if frame_callback is not None:
            dets = [r.plate_detection for r in results]
            frame_callback(frame, dets)
        n += 1
    return n


def draw_overlays(frame: np.ndarray,
                  detections: list[PlateDetection],
                  labels: Optional[list[str]] = None,
                  debounced_indices: Optional[set[int]] = None) -> np.ndarray:
    """Draw bounding boxes on *frame*.

    Debounced plates are drawn in grey instead of green so the operator can
    see the camera is detecting without confusion about repeated DB writes.
    """
    out = frame.copy()
    for i, det in enumerate(detections):
        x1, y1, x2, y2 = det.bbox
        suppressed = debounced_indices is not None and i in debounced_indices
        colour = (160, 160, 160) if suppressed else (0, 255, 0)
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
        label = labels[i] if labels and i < len(labels) else f"{det.confidence:.2f}"
        if suppressed:
            label = f"[cd] {label}"
        cv2.putText(out, label, (x1, max(15, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 2)
    return out
