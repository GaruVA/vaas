"""VAAS production runner.

Usage
-----
  python app.py

Environment variables (all optional — defaults shown):
  VAAS_SECRET_KEY        Flask session secret (REQUIRED in production)
  VAAS_HW_MODE           LIVE | MOCK  (default: LIVE)
  VAAS_ARDUINO_PORT      Serial port for Arduino Nano (default: COM3)
  VAAS_CAM_A             Camera index for GATE_A (default: 0)
  VAAS_CAM_B             Camera index for GATE_B (default: 1)
  VAAS_GATE_A_DIR        ENTRY | EXIT direction for GATE_A (default: ENTRY)
  VAAS_GATE_B_DIR        ENTRY | EXIT direction for GATE_B (default: EXIT)
  VAAS_PORT              Flask listen port (default: 5000)
  VAAS_HOST              Flask listen host (default: 0.0.0.0)

This runner:
  1. Creates the Flask app with the LIVE barrier (Arduino via PySerial)
  2. Starts two background camera-worker threads (one per gate) that:
       - Read live frames from the two USB webcams
       - Run YOLOv8 plate detection
       - Draw bounding-box overlays (served by /operator/stream/<gate>.mjpg)
       - Run the full ALPR pipeline and call AttendanceEngine per detection
  3. Starts the overstay-monitor background thread
  4. Launches Flask (single-threaded; use gunicorn for multi-worker prod)
"""
from __future__ import annotations

import logging
import os
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("vaas")

from src.config import CAMERA_INDEX_GATE_A, CAMERA_INDEX_GATE_B, HARDWARE_MODE
from webapp import create_app
from webapp.routes.operator import start_camera_worker, stop_camera_worker

GATE_A_DIR = os.environ.get("VAAS_GATE_A_DIR", "ENTRY")
GATE_B_DIR = os.environ.get("VAAS_GATE_B_DIR", "EXIT")
HOST = os.environ.get("VAAS_HOST", "0.0.0.0")
PORT = int(os.environ.get("VAAS_PORT", "5000"))

app = create_app(
    hardware_mode=HARDWARE_MODE,   # LIVE → real Arduino barrier
    start_overstay_monitor=True,
)

# ── Launch camera workers only in LIVE mode ──────────────────────────────
if HARDWARE_MODE == "LIVE":
    logger.info("Starting LIVE camera workers …")
    worker_a = start_camera_worker(
        gate_id="GATE_A",
        camera_index=CAMERA_INDEX_GATE_A,
        direction=GATE_A_DIR,
        app=app,
    )
    worker_b = start_camera_worker(
        gate_id="GATE_B",
        camera_index=CAMERA_INDEX_GATE_B,
        direction=GATE_B_DIR,
        app=app,
    )
    logger.info(
        "Camera workers: GATE_A→cam%d (%s), GATE_B→cam%d (%s)",
        CAMERA_INDEX_GATE_A, GATE_A_DIR,
        CAMERA_INDEX_GATE_B, GATE_B_DIR,
    )
else:
    logger.warning("VAAS_HW_MODE=%s — camera workers NOT started", HARDWARE_MODE)


def _shutdown(sig, frame):
    logger.info("Shutting down …")
    stop_camera_worker("GATE_A")
    stop_camera_worker("GATE_B")
    engine = app.config.get("VAAS_ENGINE")
    if engine:
        engine.shutdown()
    barrier = app.config.get("VAAS_BARRIER")
    if barrier:
        barrier.shutdown()
    sys.exit(0)


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

if __name__ == "__main__":
    logger.info("VAAS starting on http://%s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, threaded=True, debug=False)
