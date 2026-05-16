from __future__ import annotations

"""VAAS configuration constants.  Override via environment variables.

References: §6.1 of BUILD_SPEC.md
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODELS_DIR      = PROJECT_ROOT / "models"
PLATE_DETECTOR  = MODELS_DIR / "plate_detector.pt"
CHAR_CLASSIFIER = MODELS_DIR / "char_classifier.pt"

DB_PATH = Path(os.environ.get("VAAS_DB_PATH", str(PROJECT_ROOT / "data" / "vaas.db")))

PLATE_CONF_THRESHOLD = 0.70
CHAR_CONF_THRESHOLD  = 0.65

LOW_CONF_GATE_THRESHOLD = float(os.environ.get("VAAS_LOW_CONF_GATE_THRESHOLD", PLATE_CONF_THRESHOLD))

CLAHE_CLIP_LIMIT = 3.0
CLAHE_TILE_SIZE  = (8, 8)

CONFUSION_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({"8", "B"}),
    frozenset({"0", "O"}),
    frozenset({"1", "I"}),
    frozenset({"5", "S"}),
})
CONFUSION_COST = 0.1
FULL_COST      = 1.0
LPM_THRESHOLD  = 0.5

GENESIS_PREV_HASH = "0" * 64

EXCEPTION_TIMEOUT_SECONDS  = 30
OVERSTAY_THRESHOLD_MINUTES = 120

HARDWARE_MODE = os.environ.get("VAAS_HW_MODE", "MOCK")
ARDUINO_PORT  = os.environ.get("VAAS_ARDUINO_PORT", "/dev/ttyUSB0")
ARDUINO_BAUD  = 9600
CAMERA_INDEX  = int(os.environ.get("VAAS_CAMERA_INDEX", "0"))
CAMERA_INDEX_GATE_A = int(os.environ.get("VAAS_CAM_A", "0"))
CAMERA_INDEX_GATE_B = int(os.environ.get("VAAS_CAM_B", "1"))
SAMPLE_IMAGE_DIR = PROJECT_ROOT / "data" / "sample_plates"

PLATE_CROP_RETENTION_DAYS = 90

SECRET_KEY            = os.environ.get("VAAS_SECRET_KEY", "vaas-dev-secret-change-me")
SESSION_TIMEOUT_HOURS = 8
BCRYPT_COST           = 12

CDL_FUN_BLUE   = "#1B3F95"
CDL_YELLOW     = "#f4bd0f"
CDL_SAFETY_GRN = "#76bd33"

# ── Personal Vehicle Allowance Rates ─────────────────────────────────────────
# Daily allowance in LKR, keyed by (vehicle_category, vehicle_type).
# Edit the values below to reflect CDL's actual rate schedule.
# Any unlisted combination falls back to ALLOWANCE_DEFAULT_LKR.
ALLOWANCE_DEFAULT_LKR: int = 2678

ALLOWANCE_RATES: dict[tuple[str, str], int] = {
    # ── STAFF ────────────────────────────────────────────────────
    ("STAFF",       "CAR"):        2678,
    ("STAFF",       "VAN"):        2678,
    ("STAFF",       "TRUCK"):      2678,
    ("STAFF",       "MOTORCYCLE"): 2678,
    ("STAFF",       "UTILITY"):    2678,
    # ── CONTRACTOR ───────────────────────────────────────────────
    ("CONTRACTOR",  "CAR"):        2678,
    ("CONTRACTOR",  "VAN"):        2678,
    ("CONTRACTOR",  "TRUCK"):      2678,
    ("CONTRACTOR",  "MOTORCYCLE"): 2678,
    ("CONTRACTOR",  "UTILITY"):    2678,
    # ── MANAGEMENT ───────────────────────────────────────────────
    ("MANAGEMENT",  "CAR"):        2678,
    ("MANAGEMENT",  "VAN"):        2678,
    ("MANAGEMENT",  "TRUCK"):      2678,
    ("MANAGEMENT",  "MOTORCYCLE"): 2678,
    ("MANAGEMENT",  "UTILITY"):    2678,
    # ── FLEET ────────────────────────────────────────────────────
    ("FLEET",       "CAR"):        2678,
    ("FLEET",       "VAN"):        2678,
    ("FLEET",       "TRUCK"):      2678,
    ("FLEET",       "MOTORCYCLE"): 2678,
    ("FLEET",       "UTILITY"):    2678,
    # ── VISITOR ──────────────────────────────────────────────────
    ("VISITOR",     "CAR"):        2678,
    ("VISITOR",     "VAN"):        2678,
    ("VISITOR",     "TRUCK"):      2678,
    ("VISITOR",     "MOTORCYCLE"): 2678,
    ("VISITOR",     "UTILITY"):    2678,
    # ── EMERGENCY ────────────────────────────────────────────────
    ("EMERGENCY",   "CAR"):        2678,
    ("EMERGENCY",   "VAN"):        2678,
    ("EMERGENCY",   "TRUCK"):      2678,
    ("EMERGENCY",   "MOTORCYCLE"): 2678,
    ("EMERGENCY",   "UTILITY"):    2678,
    # ── MAINTENANCE ──────────────────────────────────────────────
    ("MAINTENANCE", "CAR"):        2678,
    ("MAINTENANCE", "VAN"):        2678,
    ("MAINTENANCE", "TRUCK"):      2678,
    ("MAINTENANCE", "MOTORCYCLE"): 2678,
    ("MAINTENANCE", "UTILITY"):    2678,
}
