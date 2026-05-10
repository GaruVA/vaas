from __future__ import annotations

"""VAAS configuration constants.  Override via environment variables.

References: §6.1 of BUILD_SPEC.md
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Model paths (FR-01)
MODELS_DIR      = PROJECT_ROOT / "models"
PLATE_DETECTOR  = MODELS_DIR / "plate_detector.pt"
CHAR_CLASSIFIER = MODELS_DIR / "char_classifier.pt"

# Database
DB_PATH = Path(os.environ.get("VAAS_DB_PATH", str(PROJECT_ROOT / "data" / "vaas.db")))

# Detection / classification (FR-01)
PLATE_CONF_THRESHOLD = 0.70
CHAR_CONF_THRESHOLD  = 0.65

# CLAHE (FR-02)
CLAHE_CLIP_LIMIT = 3.0
CLAHE_TILE_SIZE  = (8, 8)

# LPM-MLED (FR-03)
CONFUSION_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({"8", "B"}),
    frozenset({"0", "O"}),
    frozenset({"1", "I"}),
    frozenset({"5", "S"}),
})
CONFUSION_COST = 0.1
FULL_COST      = 1.0
LPM_THRESHOLD  = 0.5  # strict <

# Audit chain
GENESIS_PREV_HASH = "0" * 64

# Attendance (FR-04)
EXCEPTION_TIMEOUT_SECONDS  = 30
OVERSTAY_THRESHOLD_MINUTES = 120

# Hardware
HARDWARE_MODE = os.environ.get("VAAS_HW_MODE", "MOCK")
ARDUINO_PORT  = os.environ.get("VAAS_ARDUINO_PORT", "/dev/ttyUSB0")
ARDUINO_BAUD  = 9600
CAMERA_INDEX  = int(os.environ.get("VAAS_CAMERA_INDEX", "0"))
CAMERA_INDEX_GATE_A = int(os.environ.get("VAAS_CAM_A", "0"))
CAMERA_INDEX_GATE_B = int(os.environ.get("VAAS_CAM_B", "1"))
SAMPLE_IMAGE_DIR = PROJECT_ROOT / "data" / "sample_plates"

# Privacy (PDPA 2022)
PLATE_CROP_RETENTION_DAYS = 90

# Auth / session
SECRET_KEY            = os.environ.get("VAAS_SECRET_KEY", "vaas-dev-secret-change-me")
SESSION_TIMEOUT_HOURS = 8
BCRYPT_COST           = 12

# CDL branding
CDL_FUN_BLUE   = "#1B3F95"
CDL_YELLOW     = "#f4bd0f"
CDL_SAFETY_GRN = "#76bd33"
