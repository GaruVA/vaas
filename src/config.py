"""VAAS configuration constants (thesis Ch.6).

python-dotenv is loaded here — this module is the first import in every
entry point, so .env values are available to all subsequent os.environ.get()
calls throughout the application.

Priority (highest → lowest):
  1. Real shell / OS environment variables   (set in PowerShell / CMD / systemd)
  2. Values in the .env file in PROJECT_ROOT (loaded below via dotenv)
  3. Hard-coded defaults in this file
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Load .env before ANY os.environ.get() call ───────────────────────────────
# override=False means a real shell variable always wins over .env, so you can
# still do  set VAAS_HW_MODE=MOCK  in a shell without editing the file.
try:
    from dotenv import load_dotenv
    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=_ENV_FILE, override=False)
    if _ENV_FILE.exists():
        import logging as _log
        _log.getLogger(__name__).info("Loaded environment from %s", _ENV_FILE)
except ImportError:
    pass  # python-dotenv not installed — fall back to shell env / defaults


# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR   = PROJECT_ROOT / "models"
PLATE_DETECTOR  = MODELS_DIR / "plate_detection.pt"
CHAR_CLASSIFIER = MODELS_DIR / "character_recognition.pt"
DB_PATH         = PROJECT_ROOT / "data" / "vaas.db"

# ── Detection / classification thresholds (FR-01) ────────────────────────────
PLATE_CONF_THRESHOLD = float(os.environ.get("VAAS_PLATE_CONF", "0.70"))
CHAR_CONF_THRESHOLD  = float(os.environ.get("VAAS_CHAR_CONF",  "0.65"))

# ── CLAHE (FR-01.2) ───────────────────────────────────────────────────────────
CLAHE_CLIP_LIMIT = 3.0
CLAHE_TILE_SIZE  = (8, 8)

# ── LPM-MLED confusion pairs (FR-01.4, §6.3) ─────────────────────────────────
CONFUSION_PAIRS = {
    frozenset({'8', 'B'}),
    frozenset({'0', 'O'}),
    frozenset({'1', 'I'}),
    frozenset({'5', 'S'}),
}
CONFUSION_COST = 0.1
FULL_COST      = 1.0
LPM_THRESHOLD  = 0.5

# ── Audit chain (FR-05.1) ─────────────────────────────────────────────────────
GENESIS_SALT = "VAAS-GENESIS-2026"

# ── Attendance engine (FR-02) ─────────────────────────────────────────────────
EXCEPTION_TIMEOUT_SECONDS = int(os.environ.get("VAAS_EXCEPTION_TIMEOUT", "30"))
OVERSTAY_CHECK_INTERVAL_S = 300

# ── Hardware ──────────────────────────────────────────────────────────────────
HARDWARE_MODE       = os.environ.get("VAAS_HW_MODE",       "LIVE")   # LIVE | MOCK
ARDUINO_PORT        = os.environ.get("VAAS_ARDUINO_PORT",  "COM3")
ARDUINO_BAUD        = 9600
CAMERA_INDEX_GATE_A = int(os.environ.get("VAAS_CAM_A", "0"))
CAMERA_INDEX_GATE_B = int(os.environ.get("VAAS_CAM_B", "1"))
SAMPLE_IMAGE_DIR    = PROJECT_ROOT / "data" / "sample_plates"

# ── Plate retention (NFR-03) ──────────────────────────────────────────────────
PLATE_CROP_RETENTION_DAYS = 90

# ── Auth / session ────────────────────────────────────────────────────────────
SESSION_TIMEOUT_HOURS = int(os.environ.get("VAAS_SESSION_HOURS", "8"))
SECRET_KEY = os.environ.get("VAAS_SECRET_KEY", "vaas-dev-secret-change-me")
