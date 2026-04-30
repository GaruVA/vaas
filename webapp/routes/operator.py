"""Operator blueprint: live dashboard, exception disposition, SSE, MJPEG stream.

Sprint 3.3 — LIVE bounding-box stream
--------------------------------------
`start_camera_worker(gate_id, camera_index, direction, app_context)` launches a
background daemon thread that:
  1. Opens a real USBCamera (Logitech C920 / any V4L2 / DirectShow device)
  2. Reads frames continuously
  3. Runs the PlateDetector on every frame
  4. Draws bounding boxes + confidence labels onto the frame
  5. For every detected plate, runs the full ALPR pipeline (CLAHE → CharClassifier
     → AttendanceEngine.process_gate_event)
  6. Stores the annotated frame in _LATEST_FRAMES so the MJPEG endpoint can serve it

The MJPEG endpoint (/operator/stream/<gate_id>.mjpg) reads from _LATEST_FRAMES and
yields multipart JPEG data at ~10 fps.  No mock frames are served in production.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Optional

import cv2
import numpy as np
from flask import (
    Blueprint, Response, current_app, jsonify, render_template, request,
    session, stream_with_context, url_for,
)

from src.clahe import apply_clahe
from src.config import CAMERA_INDEX_GATE_A, CAMERA_INDEX_GATE_B
from src.pipeline import draw_overlays

logger = logging.getLogger(__name__)
operator_bp = Blueprint("operator", __name__, url_prefix="/operator")

# ── Per-gate latest annotated frame (thread-safe via lock) ─────────────────
_FRAME_LOCK = threading.Lock()
_LATEST_FRAMES: dict[str, np.ndarray] = {}

# ── Per-gate camera-worker stop events ─────────────────────────────────────
_WORKER_STOP: dict[str, threading.Event] = {}


def publish_overlay_frame(gate_id: str, frame: np.ndarray) -> None:
    with _FRAME_LOCK:
        _LATEST_FRAMES[gate_id] = frame


def _latest_frame(gate_id: str) -> Optional[np.ndarray]:
    with _FRAME_LOCK:
        f = _LATEST_FRAMES.get(gate_id)
        return f.copy() if f is not None else None


# ── Live camera worker ──────────────────────────────────────────────────────

def _camera_worker(gate_id: str, camera_index: int, direction: str,
                   stop_event: threading.Event, app) -> None:
    """Background thread: read live frames, detect plates, draw overlays, run pipeline."""
    from src.camera import USBCamera
    from src.classifier import CharClassifier
    from src.detection import PlateDetection, PlateDetector

    logger.info("[%s] Camera worker starting (index=%d, direction=%s)",
                gate_id, camera_index, direction)

    # Load models once inside this thread (YOLO is thread-safe after loading)
    try:
        detector = PlateDetector()
        classifier = CharClassifier()
    except Exception as exc:
        logger.error("[%s] Model load failed: %s", gate_id, exc)
        return

    # Open camera with retries
    cam: Optional[USBCamera] = None
    for attempt in range(5):
        try:
            cam = USBCamera(index=camera_index)
            logger.info("[%s] Camera opened on index %d", gate_id, camera_index)
            break
        except Exception as exc:
            logger.warning("[%s] Camera open attempt %d failed: %s", gate_id, attempt + 1, exc)
            time.sleep(2)

    if cam is None:
        logger.error("[%s] Could not open camera — worker exiting", gate_id)
        return

    with app.app_context():
        engine = current_app.config["VAAS_ENGINE"]

        while not stop_event.is_set():
            frame = cam.read()
            if frame is None:
                logger.warning("[%s] Camera read returned None — retrying", gate_id)
                time.sleep(0.1)
                continue

            t0 = time.perf_counter()

            # ── Stage 1: plate detection ────────────────────────────────
            detections: list[PlateDetection] = detector.detect(frame)

            # ── Draw bbox overlays onto a copy ───────────────────────────
            labels: list[str] = []
            for det in detections:
                labels.append(f"{det.confidence:.2f}")

            annotated = draw_overlays(frame, detections, labels=labels)
            publish_overlay_frame(gate_id, annotated)

            # ── Stage 2-4: CLAHE → classify → attendance, per detection ─
            for det in detections:
                try:
                    enhanced = apply_clahe(det.crop)
                    raw, conf = classifier.classify(enhanced)
                    if not raw:
                        continue
                    ok, buf = cv2.imencode(".jpg", det.crop,
                                          [cv2.IMWRITE_JPEG_QUALITY, 85])
                    jpeg_bytes = buf.tobytes() if ok else b""
                    result = engine.process_gate_event(
                        raw, conf, gate_id, direction, jpeg_bytes
                    )
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    logger.info("[%s] %s → %s (%.0f ms)",
                                gate_id, raw, result.outcome, elapsed_ms)
                except Exception as exc:
                    logger.error("[%s] Pipeline error: %s", gate_id, exc)

            # ── Throttle to ~10 fps ──────────────────────────────────────
            elapsed = time.perf_counter() - t0
            sleep_for = max(0.0, 0.1 - elapsed)
            if sleep_for:
                time.sleep(sleep_for)

    cam.release()
    logger.info("[%s] Camera worker stopped", gate_id)


def start_camera_worker(gate_id: str, camera_index: int,
                        direction: str, app) -> threading.Thread:
    """Launch (or restart) the live camera worker for *gate_id*.

    Called from the production runner (app.py) after create_app().
    Safe to call multiple times — previous worker is stopped first.
    """
    stop_camera_worker(gate_id)
    stop_event = threading.Event()
    _WORKER_STOP[gate_id] = stop_event
    t = threading.Thread(
        target=_camera_worker,
        args=(gate_id, camera_index, direction, stop_event, app),
        daemon=True,
        name=f"cam-{gate_id}",
    )
    t.start()
    return t


def stop_camera_worker(gate_id: str) -> None:
    ev = _WORKER_STOP.get(gate_id)
    if ev is not None:
        ev.set()


# ── Flask routes ────────────────────────────────────────────────────────────

def _requires_login(fn):
    from functools import wraps
    from flask import redirect, url_for
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


@operator_bp.route("/dashboard")
@_requires_login
def dashboard():
    conn = current_app.config["VAAS_DB"]
    recent = conn.execute(
        "SELECT id, plate_number, timestamp, gate_id, direction, "
        "       status, confidence_score "
        "FROM access_log ORDER BY id DESC LIMIT 20"
    ).fetchall()
    pending = conn.execute(
        "SELECT id, plate_number, timestamp, gate_id, confidence_score "
        "FROM access_log WHERE status='VISITOR' ORDER BY id DESC"
    ).fetchall()
    return render_template("operator/dashboard.html",
                           recent=recent, pending=pending)


@operator_bp.route("/sse")
@_requires_login
def sse():
    """Server-Sent Events stream (pushes new gate events to the dashboard)."""
    broker = current_app.config["VAAS_BROKER"]
    q = broker.subscribe()

    @stream_with_context
    def _gen():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    evt = q.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(evt)}\n\n"
        finally:
            broker.unsubscribe(q)

    return Response(
        _gen(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@operator_bp.route("/exception/<int:access_log_id>/dispose", methods=["POST"])
@_requires_login
def dispose(access_log_id: int):
    body = request.get_json(silent=True) or request.form
    disposition = (body.get("disposition") or "REJECT").upper()
    if disposition not in ("ADMIT", "REJECT", "REGISTER"):
        return jsonify({"error": "invalid disposition"}), 400

    engine = current_app.config["VAAS_ENGINE"]
    new_status = engine.dispose_exception(
        access_log_id, disposition,
        operator_user_id=session.get("user_id"),
    )

    if disposition == "REGISTER":
        row = current_app.config["VAAS_DB"].execute(
            "SELECT plate_number FROM access_log WHERE id=?", (access_log_id,)
        ).fetchone()
        plate = row["plate_number"] if row else ""
        return jsonify({
            "status": new_status,
            "redirect": url_for("admin.new_vehicle", plate=plate),
        })

    return jsonify({"status": new_status})


@operator_bp.route("/stream/<gate_id>.mjpg")
@_requires_login
def stream(gate_id: str):
    """MJPEG live stream with ALPR bounding-box overlays (Sprint 3.3).

    Yields annotated frames from _LATEST_FRAMES, which are populated by the
    background camera worker threads.  If the worker hasn't produced a frame
    yet a 'waiting' placeholder is served so the <img> tag is never broken.
    """
    if gate_id not in ("GATE_A", "GATE_B"):
        return "Unknown gate", 404

    BOUNDARY = b"--vaasframe"
    TARGET_FPS = 10
    FRAME_INTERVAL = 1.0 / TARGET_FPS

    def _gen():
        while True:
            t_start = time.monotonic()
            frame = _latest_frame(gate_id)

            if frame is None:
                # Placeholder until the camera worker delivers its first real frame
                frame = np.zeros((360, 640, 3), dtype=np.uint8)
                cv2.putText(frame,
                            f"{gate_id} — waiting for camera ({CAMERA_INDEX_GATE_A if gate_id == 'GATE_A' else CAMERA_INDEX_GATE_B})",
                            (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (180, 180, 180), 2)
                cv2.putText(frame,
                            "Check VAAS_HW_MODE and camera index",
                            (20, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                            (120, 120, 120), 1)

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                time.sleep(FRAME_INTERVAL)
                continue

            jpg = buf.tobytes()
            yield (
                b"\r\n" + BOUNDARY + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(jpg)}\r\n\r\n".encode()
                + jpg
            )

            elapsed = time.monotonic() - t_start
            sleep_for = max(0.0, FRAME_INTERVAL - elapsed)
            if sleep_for:
                time.sleep(sleep_for)

    return Response(
        _gen(),
        mimetype="multipart/x-mixed-replace; boundary=vaasframe",
        headers={"Cache-Control": "no-cache"},
    )
