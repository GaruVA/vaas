"""VAAS configuration constants. All thresholds/paths from thesis Ch.6."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
# Note: actual filenames in the supplied models/ directory
PLATE_DETECTOR = MODELS_DIR / "plate_detection.pt"
CHAR_CLASSIFIER = MODELS_DIR / "character_recognition.pt"
DB_PATH = PROJECT_ROOT / "data" / "vaas.db"

# Detection / classification thresholds (FR-01)
PLATE_CONF_THRESHOLD = 0.70
CHAR_CONF_THRESHOLD = 0.65

# CLAHE (FR-01.2)
CLAHE_CLIP_LIMIT = 3.0
CLAHE_TILE_SIZE = (8, 8)

# LPM-MLED (FR-01.4)
CONFUSION_PAIRS = {
    frozenset({'8', 'B'}),
    frozenset({'0', 'O'}),
    frozenset({'1', 'I'}),
    frozenset({'5', 'S'}),
}
CONFUSION_COST = 0.1
FULL_COST = 1.0
LPM_THRESHOLD = 0.5

# Audit chain (FR-05.1)
GENESIS_SALT = "VAAS-GENESIS-2026"

# Attendance (FR-02)
EXCEPTION_TIMEOUT_SECONDS = 30
OVERSTAY_CHECK_INTERVAL_S = 300

# Hardware
HARDWARE_MODE = os.environ.get("VAAS_HW_MODE", "LIVE")  # 'MOCK' or 'LIVE'
ARDUINO_PORT = os.environ.get("VAAS_ARDUINO_PORT", "COM3")
ARDUINO_BAUD = 9600
CAMERA_INDEX_GATE_A = int(os.environ.get("VAAS_CAM_A", "0"))
CAMERA_INDEX_GATE_B = int(os.environ.get("VAAS_CAM_B", "1"))
SAMPLE_IMAGE_DIR = PROJECT_ROOT / "data" / "sample_plates"

# Plate retention (NFR-03)
PLATE_CROP_RETENTION_DAYS = 90

# Auth
SESSION_TIMEOUT_HOURS = 8
SECRET_KEY = os.environ.get("VAAS_SECRET_KEY", "vaas-dev-secret-change-me")
