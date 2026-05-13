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
    Blueprint, Response, current_app, g, jsonify, render_template, request,
    session, stream_with_context, url_for,
)

from src.clahe import apply_clahe
from src.config import CAMERA_INDEX_GATE_A, CAMERA_INDEX_GATE_B
from src.pipeline import DEFAULT_COOLDOWN_SECONDS, PlateDebouncer, draw_overlays, process_frame

logger = logging.getLogger(__name__)
operator_bp = Blueprint("operator", __name__, url_prefix="/operator")

# ── Per-gate latest annotated frame (thread-safe via lock) ─────────────────
_FRAME_LOCK = threading.Lock()
_LATEST_FRAMES: dict[str, np.ndarray] = {}

# ── Per-gate camera-worker stop events ─────────────────────────────────────
_WORKER_STOP: dict[str, threading.Event] = {}

# ── Shared model singletons (loaded once, reused by all camera workers) ─────
# Both GATE_A and GATE_B workers use the same detector and classifier instances.
# YOLO models are thread-safe for concurrent inference after loading.
_MODEL_LOCK = threading.Lock()
_SHARED_DETECTOR = None
_SHARED_CLASSIFIER = None


def _get_models():
    """Return (detector, classifier), loading from disk only on the first call."""
    global _SHARED_DETECTOR, _SHARED_CLASSIFIER
    if _SHARED_DETECTOR is not None:
        return _SHARED_DETECTOR, _SHARED_CLASSIFIER          # fast path — already loaded
    with _MODEL_LOCK:
        if _SHARED_DETECTOR is None:                         # re-check after acquiring lock
            from src.detection import PlateDetector
            from src.classifier import CharClassifier
            logger.info("Loading shared ALPR models (first worker to start)…")
            _SHARED_DETECTOR  = PlateDetector()
            _SHARED_CLASSIFIER = CharClassifier()
            logger.info("Shared ALPR models ready.")
    return _SHARED_DETECTOR, _SHARED_CLASSIFIER


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
    from src.detection import PlateDetection

    logger.info("[%s] Camera worker starting (index=%d, direction=%s, cooldown=%ds)",
                gate_id, camera_index, direction, DEFAULT_COOLDOWN_SECONDS)

    # Use the shared model singleton — avoids loading the same weights twice.
    try:
        detector, classifier = _get_models()
    except Exception as exc:
        logger.error("[%s] Model load failed: %s", gate_id, exc)
        return

    # One debouncer per gate — prevents the same plate string being submitted
    # to the attendance engine multiple times within the cooldown window.
    debouncer = PlateDebouncer(cooldown_seconds=DEFAULT_COOLDOWN_SECONDS)

    # Open camera with retries
    cam: Optional[USBCamera] = None
    for attempt in range(5):
        try:
            cam = USBCamera(index=camera_index)
            logger.info("[%s] Camera opened on index %d", gate_id, camera_index)
            break
        except Exception as exc:
            logger.warning("[%s] Camera open attempt %d failed: %s",
                           gate_id, attempt + 1, exc)
            time.sleep(2)

    if cam is None:
        logger.error("[%s] Could not open camera — worker exiting", gate_id)
        return

    with app.app_context():
        engine = app.config.get("VAAS_ENGINE")
        if engine is None:
            logger.error("[%s] VAAS_ENGINE not initialized", gate_id)
            return

        while not stop_event.is_set():
            frame = cam.read()
            if frame is None:
                logger.warning("[%s] Camera read returned None — retrying", gate_id)
                time.sleep(0.05)
                continue

            t0 = time.perf_counter()

            # ── Stages 1-4: detect → CLAHE → classify → engine (with debounce) ─
            try:
                results = process_frame(
                    frame, detector, classifier, engine,
                    gate_id, direction, debouncer=debouncer,
                )
            except Exception as exc:
                logger.error("[%s] process_frame error: %s", gate_id, exc)
                results = []

            # ── Build overlay labels (grey for debounced, green for new) ────
            detections = [r.plate_detection for r in results]
            debounced_idx = {i for i, r in enumerate(results) if r.debounced}
            labels = []
            for i, r in enumerate(results):
                tag = "[cd]" if r.debounced else ""
                labels.append(f"{tag}{r.raw_plate} {r.confidence:.2f}" if r.raw_plate
                               else f"{r.plate_detection.confidence:.2f}")

            annotated = draw_overlays(frame, detections,
                                      labels=labels,
                                      debounced_indices=debounced_idx)
            publish_overlay_frame(gate_id, annotated)

            # ── Log and broadcast non-debounced events ───────────────────
            broker = app.config.get("VAAS_BROKER")
            for r in results:
                if not r.debounced and r.gate_event is not None:
                    outcome_val = (
                        r.gate_event.outcome.value
                        if hasattr(r.gate_event.outcome, "value")
                        else str(r.gate_event.outcome)
                    )
                    logger.info("[%s] %s → %s (%.0f ms total)",
                                gate_id, r.raw_plate, outcome_val,
                                r.timings_ms.get("total", 0))

                    # Visitor exceptions are broadcast by AttendanceEngine via
                    # sse_callback; skip them here to avoid duplicate events.
                    if "EXCEPTION" in outcome_val:
                        continue

                    if broker is not None:
                        status_val = (
                            r.gate_event.status.value
                            if hasattr(r.gate_event, "status") and hasattr(r.gate_event.status, "value")
                            else outcome_val
                        )
                        evt = {
                            "type":       "gate_event",
                            "gate_id":    gate_id,
                            "plate":      r.raw_plate,
                            "status":     status_val,
                            "confidence": round(r.confidence, 3),
                            "direction":  direction,
                            "timestamp":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                        broker.publish(evt)
                        logger.debug("[%s] SSE gate_event published: %s %s",
                                     gate_id, status_val, r.raw_plate)

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
    recent = g.db.execute(
        "SELECT id, plate_number, timestamp, gate_id, direction, "
        "       status, confidence_score "
        "FROM access_log ORDER BY id DESC LIMIT 20"
    ).fetchall()
    pending = g.db.execute(
        "SELECT id, plate_number, timestamp, gate_id, confidence_score "
        "FROM access_log WHERE status='VISITOR' ORDER BY id DESC"
    ).fetchall()
    return render_template("operator/dashboard.html",
                           recent=recent, pending=pending)


@operator_bp.route("/sse")
@_requires_login
def sse():
    """Server-Sent Events stream (pushes new gate events to the dashboard)."""
    broker = g.get("VAAS_BROKER") or current_app.config.get("VAAS_BROKER")
    if broker is None:
        logger.error("VAAS_BROKER not initialized")
        return jsonify({"error": "Event broker not available"}), 503
    q = broker.subscribe()

    @stream_with_context
    def _gen():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    # 2s timeout (was 15s): GeneratorExit is only raised at a yield
                    # point, so a long blocking get() keeps the Waitress thread
                    # reserved for up to <timeout> seconds after the client drops.
                    # 2s means threads are recycled within one tick of the event loop.
                    evt = q.get(timeout=2)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(evt)}\n\n"
        except GeneratorExit:
            logger.debug("SSE client disconnected — releasing Waitress thread")
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
    from flask import current_app
    body = request.get_json(silent=True) or request.form
    disposition = (body.get("disposition") or "REJECT").upper()
    if disposition not in ("ADMIT", "REJECT", "REGISTER"):
        return jsonify({"error": "invalid disposition"}), 400

    engine = current_app.config.get("VAAS_ENGINE")
    if engine is None:
        return jsonify({"error": "Attendance engine not initialized"}), 503
    engine.dispose_exception(
        access_log_id, disposition,
        operator_user_id=session.get("user_id"),
    )

    # Broadcast the disposition to all connected SSE clients so every open
    # dashboard tab removes the exception row and updates the status badge.
    _DISPOSITION_STATUS = {
        "ADMIT":    "VISITOR_ADMITTED",
        "REJECT":   "VISITOR_REJECTED",
        "REGISTER": "VISITOR_PENDING_REGISTRATION",
    }
    broker = current_app.config.get("VAAS_BROKER")
    if broker:
        row_meta = current_app.config["VAAS_DB"].execute(
            "SELECT gate_id, plate_number FROM access_log WHERE id=?",
            (access_log_id,),
        ).fetchone()
        broker.publish({
            "type":       "exception_disposed",
            "id":         access_log_id,
            "gate_id":    row_meta["gate_id"] if row_meta else None,
            "new_status": _DISPOSITION_STATUS.get(disposition, ""),
        })

    if disposition == "REGISTER":
        row = current_app.config["VAAS_DB"].execute(
            "SELECT plate_number FROM access_log WHERE id=?", (access_log_id,)
        ).fetchone()
        plate = row["plate_number"] if row else ""
        return jsonify({
            "redirect": url_for("admin.new_vehicle", plate=plate),
        })

    return jsonify({"status": "ok"})


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
        try:
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
        except GeneratorExit:
            # Client navigated away or closed the browser tab.  Python raises
            # GeneratorExit at the generator's last yield point, so we get here
            # quickly (within one FRAME_INTERVAL ~100ms) and the Waitress thread
            # is released back to the pool immediately.
            logger.debug("[%s] MJPEG client disconnected — releasing Waitress thread", gate_id)
        finally:
            logger.debug("[%s] MJPEG stream closed", gate_id)

    return Response(
        _gen(),
        mimetype="multipart/x-mixed-replace; boundary=vaasframe",
        headers={"Cache-Control": "no-cache"},
    )
