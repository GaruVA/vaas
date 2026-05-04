"""VAAS production server — Waitress WSGI (Windows-native, no Werkzeug).

  python serve.py                ← normal start (reads .env automatically)
  python serve.py --check-env    ← validate config then exit, without starting

Why Waitress instead of `flask run`
-------------------------------------
  Werkzeug's dev server is single-threaded. VAAS needs concurrent connections:
  two persistent MJPEG sockets + one SSE socket + normal HTTP requests at the
  same time. Waitress handles all of these on a thread pool with no extra config.
"""
from __future__ import annotations

# ── 1. Load .env FIRST — before any other import touches os.environ ──────────
# Belt-and-suspenders: src/config.py also calls load_dotenv(), but serve.py
# reads PORT/THREADS/HOST from os.environ directly, so we need dotenv here too.
from pathlib import Path as _Path
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=_Path(__file__).parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv missing — shell env / defaults will be used

# ── 2. Standard library ────────────────────────────────────────────────────────
import logging
import os
import signal
import sys

# ── 3. Logging (configure before importing project modules) ──────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("vaas.serve")

# ── 4. Waitress availability check ────────────────────────────────────────────
try:
    from waitress import serve as waitress_serve
except ImportError:
    logger.error(
        "Waitress is not installed.\n"
        "  Fix:  pip install waitress>=3.0.0\n"
        "  Or:   pip install -r requirements.txt"
    )
    sys.exit(1)

# ── 5. Project imports (config.py load_dotenv() is a no-op here; env already set)
from src.config import CAMERA_INDEX_GATE_A, CAMERA_INDEX_GATE_B, HARDWARE_MODE
from webapp import create_app
from webapp.routes.operator import start_camera_worker, stop_camera_worker

# ── 6. Runtime configuration (read from env / .env) ──────────────────────────
HOST       = os.environ.get("VAAS_HOST",    "0.0.0.0")
PORT       = int(os.environ.get("VAAS_PORT",    "5000"))
THREADS    = int(os.environ.get("VAAS_THREADS", "32"))
GATE_A_DIR = os.environ.get("VAAS_GATE_A_DIR", "ENTRY")
GATE_B_DIR = os.environ.get("VAAS_GATE_B_DIR", "EXIT")
SECRET_KEY = os.environ.get("VAAS_SECRET_KEY", "vaas-dev-secret-change-me")

# ── 7. Pre-flight validation ──────────────────────────────────────────────────
_ERRORS   = []
_WARNINGS = []

if SECRET_KEY in ("vaas-dev-secret-change-me", "CHANGE_ME_generate_with_secrets_token_hex_32", ""):
    _ERRORS.append(
        "VAAS_SECRET_KEY is not set or still has the placeholder value.\n"
        "  Generate a key:  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "  Then add it to your .env file:  VAAS_SECRET_KEY=<generated-value>"
    )

if HARDWARE_MODE not in ("LIVE", "MOCK"):
    _ERRORS.append(f"VAAS_HW_MODE='{HARDWARE_MODE}' is invalid.  Must be LIVE or MOCK.")

if HARDWARE_MODE == "MOCK":
    _WARNINGS.append(
        "VAAS_HW_MODE=MOCK — cameras and Arduino are disabled.\n"
        "  MJPEG streams will show a placeholder image.\n"
        "  Change to VAAS_HW_MODE=LIVE in your .env for production."
    )

env_file = _Path(__file__).parent / ".env"
if not env_file.exists():
    _WARNINGS.append(
        ".env file not found.  Copy .env.example and edit it:\n"
        "  copy .env.example .env"
    )

check_only = "--check-env" in sys.argv

for w in _WARNINGS:
    logger.warning(w)

if _ERRORS:
    for e in _ERRORS:
        logger.error(e)
    if not check_only:
        logger.error("Startup aborted — fix the errors above, then re-run serve.py.")
        sys.exit(1)

if check_only:
    if _ERRORS:
        logger.error("Environment check FAILED — %d error(s) above.", len(_ERRORS))
        sys.exit(1)
    logger.info("Environment check PASSED (HW_MODE=%s, PORT=%d).", HARDWARE_MODE, PORT)
    sys.exit(0)

# ── 8. Create Flask app ────────────────────────────────────────────────────────
logger.info("Creating VAAS Flask application (HW_MODE=%s)", HARDWARE_MODE)
app = create_app(
    hardware_mode=HARDWARE_MODE,
    start_overstay_monitor=True,
)

# ── 9. Launch live camera workers ─────────────────────────────────────────────
if HARDWARE_MODE == "LIVE":
    logger.info(
        "Starting camera workers: GATE_A → cam%d (%s),  GATE_B → cam%d (%s)",
        CAMERA_INDEX_GATE_A, GATE_A_DIR,
        CAMERA_INDEX_GATE_B, GATE_B_DIR,
    )
    start_camera_worker(gate_id="GATE_A", camera_index=CAMERA_INDEX_GATE_A,
                        direction=GATE_A_DIR, app=app)
    start_camera_worker(gate_id="GATE_B", camera_index=CAMERA_INDEX_GATE_B,
                        direction=GATE_B_DIR, app=app)
else:
    logger.warning("Camera workers not started (MOCK mode).")

# ── 10. Graceful shutdown handler ─────────────────────────────────────────────
def _shutdown(sig, frame):
    logger.info("Shutdown signal — stopping workers …")
    stop_camera_worker("GATE_A")
    stop_camera_worker("GATE_B")
    engine = app.config.get("VAAS_ENGINE")
    if engine:
        engine.shutdown()
    barrier = app.config.get("VAAS_BARRIER")
    if barrier:
        barrier.shutdown()
    logger.info("VAAS stopped cleanly.")
    sys.exit(0)

signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

# ── 11. Start Waitress ────────────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("  VAAS  •  http://localhost:%d  •  Waitress %d threads", PORT, THREADS)
logger.info("  Hardware mode : %s", HARDWARE_MODE)
logger.info("  Arduino port  : %s", os.environ.get("VAAS_ARDUINO_PORT", "COM3"))
logger.info("  Camera A      : index %d  direction %s", CAMERA_INDEX_GATE_A, GATE_A_DIR)
logger.info("  Camera B      : index %d  direction %s", CAMERA_INDEX_GATE_B, GATE_B_DIR)
logger.info("=" * 60)

waitress_serve(
    app,
    host=HOST,
    port=PORT,
    threads=THREADS,
    channel_timeout=300,   # keep MJPEG + SSE sockets alive for long-lived connections
    # connection_limit: max simultaneous sockets before Waitress starts refusing new
    # connections. 200 is a safe ceiling; each MJPEG/SSE stream occupies one slot.
    connection_limit=200,
    # asyncore_use_poll is a Linux/macOS tuning knob; on Windows Waitress always uses
    # select(), so this parameter has no effect and is omitted intentionally.
    ident="VAAS/1.0",
)
