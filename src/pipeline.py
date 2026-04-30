"""End-to-end ALPR pipeline: frame -> plate -> gate event (§5.3)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np

from src.attendance import AttendanceEngine, GateEventResult
from src.classifier import CharClassifier
from src.clahe import apply_clahe
from src.detection import PlateDetection, PlateDetector

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    plate_detection: PlateDetection
    raw_plate: str
    confidence: float
    gate_event: Optional[GateEventResult]
    timings_ms: dict


def process_frame(frame: np.ndarray,
                  detector: PlateDetector,
                  classifier: CharClassifier,
                  engine: AttendanceEngine,
                  gate_id: str,
                  direction: str) -> list[PipelineResult]:
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
        ok, jpg = cv2.imencode(".jpg", det.crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        jpeg_bytes = jpg.tobytes() if ok else b""
        evt = engine.process_gate_event(raw, conf, gate_id, direction, jpeg_bytes)
        t4 = time.perf_counter()
        results.append(PipelineResult(
            plate_detection=det,
            raw_plate=raw,
            confidence=conf,
            gate_event=evt,
            timings_ms={
                "detect": round((t1 - t0) * 1000, 1),
                "clahe": round((t2 - t1) * 1000, 1),
                "classify": round((t3 - t2) * 1000, 1),
                "engine": round((t4 - t3) * 1000, 1),
                "total": round((t4 - t0) * 1000, 1),
            },
        ))
    return results


def run_pipeline(camera, detector: PlateDetector, classifier: CharClassifier,
                 engine: AttendanceEngine, gate_id: str, direction: str,
                 frame_callback: Optional[Callable[[np.ndarray, list[PlateDetection]], None]] = None,
                 stop_event=None,
                 max_frames: Optional[int] = None) -> int:
    """Continuous loop. Optionally calls frame_callback(frame_with_overlays, detections)."""
    n = 0
    while True:
        if stop_event is not None and stop_event.is_set():
            break
        if max_frames is not None and n >= max_frames:
            break
        frame = camera.read()
        if frame is None:
            break
        results = process_frame(frame, detector, classifier, engine, gate_id, direction)
        if frame_callback is not None:
            dets = [r.plate_detection for r in results]
            frame_callback(frame, dets)
        n += 1
    return n


def draw_overlays(frame: np.ndarray, detections: list[PlateDetection],
                  labels: Optional[list[str]] = None) -> np.ndarray:
    out = frame.copy()
    for i, det in enumerate(detections):
        x1, y1, x2, y2 = det.bbox
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = labels[i] if labels and i < len(labels) else f"{det.confidence:.2f}"
        cv2.putText(out, label, (x1, max(15, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return out
