# VAAS — Vehicle Attendance and Analytics System

Final-year project — BSc Software Engineering, University of Plymouth (Sri Lanka Campus).  
Python 3.13 · YOLOv8 · Flask · SQLite WAL · Arduino Nano

---

## Hardware requirements

| Item | Detail |
|---|---|
| Camera × 2 | Logitech C920 (or any DirectShow/V4L2 USB webcam) |
| Microcontroller | Arduino Nano — flash `firmware/vaas_barrier.ino` |
| Barrier servo | Connected to **D9** (GATE_A) and **D10** (GATE_B) |
| Host machine | Windows 10/11 with Python 3.11+ |

---

## Quick start

### 1 — Install dependencies

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2 — Flash the Arduino

Open `firmware/vaas_barrier.ino` in the Arduino IDE (or VS Code + PlatformIO).  
Select **Arduino Nano** / **ATmega328P**.  Upload.  
The serial monitor should print `VAAS_BARRIER_READY` at 9600 baud.

### 3 — Seed the database

```bash
python scripts/seed_db.py
```

You will be prompted for an admin password.  
Auto-generated passwords for `manager` and `operator` are printed once — save them.

The seed creates:
- 2 shifts: `DAY_SHIFT` (08:00–17:00 Mon–Fri), `NIGHT_SHIFT` (20:00–05:00 Mon–Sat)
- 10 demo vehicles (Sri Lankan plate formats) assigned to those shifts
- 3 user accounts: `admin`, `manager`, `operator`

### 4 — Configure environment variables

```bash
# Required in production
set VAAS_SECRET_KEY=<random-string-32-chars>

# Hardware (defaults shown)
set VAAS_HW_MODE=LIVE          # LIVE | MOCK
set VAAS_ARDUINO_PORT=COM3     # Windows serial port for Arduino Nano
set VAAS_CAM_A=0               # Camera index for GATE_A
set VAAS_CAM_B=1               # Camera index for GATE_B
set VAAS_GATE_A_DIR=ENTRY      # ENTRY | EXIT
set VAAS_GATE_B_DIR=EXIT       # ENTRY | EXIT
```

On Linux replace `set` with `export` and `COM3` with `/dev/ttyUSB0`.

### 5 — Run the server

```bash
python app.py
```

Open http://localhost:5000 in a browser.

---

## Running tests

```bash
# All 129 unit tests (models required for CV tests)
pytest --no-cov

# 12 integration / system tests
pytest -m integration --no-cov

# Full suite with coverage report
pytest
```

Expected results: **129 unit tests + 12 integration tests — all pass**.

---

## Scripts

| Script | Purpose |
|---|---|
| `python scripts/seed_db.py` | Create tables + seed users + 10 demo vehicles + 2 shifts |
| `python scripts/verify_chain.py` | Verify SHA-256 audit chain on `data/vaas.db` |
| `python scripts/verify_chain.py path/to/other.db` | Verify a specific DB |
| `python scripts/generate_sample_plates.py` | Generate synthetic plate images for MOCK camera |
| `python scripts/run_demo.py --gate GATE_A --direction ENTRY` | Run pipeline in MOCK mode |

---

## Web application — role guide

| URL | Roles |
|---|---|
| `/operator/dashboard` | OPERATOR, MANAGER, ADMIN |
| `/operator/stream/GATE_A.mjpg` | Live MJPEG with bbox overlays |
| `/operator/stream/GATE_B.mjpg` | Live MJPEG with bbox overlays |
| `/manager/reports/daily` | MANAGER, ADMIN |
| `/manager/reports/<type>/export.csv` | Download CSV |
| `/manager/reports/<type>/export.pdf` | Download PDF |
| `/manager/audit/verify` | SHA-256 chain verification UI |
| `/admin/vehicles` | ADMIN |
| `/admin/shifts` | ADMIN |
| `/admin/users` | ADMIN |

---

## LPM-MLED threshold note

`LPM_THRESHOLD = 0.5` (normalised weighted edit distance).  
A single confusion-pair substitution on an 8-character plate scores **0.0125** (well inside threshold).  
A single non-confusion substitution on a 2-character string scores **0.5** (at boundary → rejected).  
Adjust `src/config.py : LPM_THRESHOLD` if your environment produces more OCR noise.

---

## Audit chain

Every `access_log` INSERT is linked to the previous row's SHA-256 hash:

```
hash_n = SHA-256( JSON({ plate, timestamp, gate_id, direction, hash_{n-1} }) )
```

Row 1 uses `GENESIS_SALT = "VAAS-GENESIS-2026"` as `hash_0`.

To tamper-check after modifying a row in SQLite:

```bash
# Modify a row
sqlite3 data/vaas.db "UPDATE access_log SET plate_number='HACK' WHERE id=1"

# Verify — will report the first broken row
python scripts/verify_chain.py
```

---

## Project structure

```
vaas/
├── app.py              ← Production server (Flask + live camera workers)
├── firmware/
│   └── vaas_barrier.ino  ← Arduino Nano sketch (OPEN/CLOSE servo)
├── src/                ← Core library modules
│   ├── config.py       ← All constants and thresholds
│   ├── database.py     ← SQLite WAL schema + helpers
│   ├── audit.py        ← SHA-256 hash chain
│   ├── lpm_mled.py     ← Weighted Levenshtein plate matching
│   ├── clahe.py        ← Contrast enhancement
│   ├── detection.py    ← YOLOv8 plate detector
│   ├── classifier.py   ← YOLOv8 character classifier
│   ├── attendance.py   ← Shift-aware gate event engine
│   ├── analytics.py    ← SQL aggregations + CSV/PDF export
│   ├── barrier.py      ← Arduino serial controller
│   ├── camera.py       ← USB camera abstraction
│   └── pipeline.py     ← Frame → plate → attendance (end-to-end)
├── webapp/             ← Flask blueprints + Jinja2 templates
│   ├── __init__.py     ← Application factory (create_app)
│   ├── auth.py         ← Session auth + role decorators
│   └── routes/
│       ├── operator.py ← Dashboard + SSE + MJPEG stream
│       ├── manager.py  ← Reports + audit
│       ├── admin.py    ← CRUD: vehicles / shifts / users
│       └── api.py      ← JSON REST endpoints
├── tests/              ← 129 unit + 12 integration tests
├── scripts/            ← seed_db, verify_chain, run_demo
├── models/             ← plate_detection.pt, character_recognition.pt
└── data/
    ├── vaas.db         ← SQLite WAL database
    └── sample_plates/  ← Synthetic test images
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `FileNotFoundError: plate_detection.pt` | Confirm `models/` contains `plate_detection.pt` and `character_recognition.pt` |
| Arduino not found on COM3 | Set `VAAS_ARDUINO_PORT=COMx` to your actual port (check Device Manager) |
| Camera index error | Set `VAAS_CAM_A` / `VAAS_CAM_B` to the correct DirectShow index |
| Stream shows "waiting for camera" | Camera worker thread starting — wait 3–5 s for model load |
| `VAAS_SECRET_KEY` warning | Set a 32+ char random string as an environment variable |
| Tests fail on CV files | YOLOv8 model files must be in `models/` for detection/classifier tests |
