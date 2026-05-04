# VAAS — Vehicle Attendance and Analytics System

> **Final-year project — BSc (Hons) Software Engineering**  
> University of Plymouth (NSBM) · 2026  
> Student ID: 10952592

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-ultralytics-purple)](https://github.com/ultralytics/ultralytics)
[![Flask](https://img.shields.io/badge/Flask-3.0-black?logo=flask)](https://flask.palletsprojects.com/)
[![Waitress](https://img.shields.io/badge/WSGI-Waitress-orange)](https://docs.pylonsproject.org/projects/waitress/)
[![SQLite WAL](https://img.shields.io/badge/SQLite-WAL%20mode-lightblue?logo=sqlite)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/tests-141%20passed-brightgreen)](#running-the-test-suite)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Hardware Requirements](#3-hardware-requirements)
4. [Repository Structure](#4-repository-structure)
5. [One-Click Deployment](#5-one-click-deployment)
6. [Manual Setup](#6-manual-setup)
7. [Environment Variables Reference](#7-environment-variables-reference)
8. [Role-Based Access Control](#8-role-based-access-control)
9. [ALPR Pipeline Detail](#9-alpr-pipeline-detail)
10. [Audit Chain & Data Integrity](#10-audit-chain--data-integrity)
11. [Running the Test Suite](#11-running-the-test-suite)
12. [Arduino Firmware](#12-arduino-firmware)
13. [Utility Scripts](#13-utility-scripts)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Executive Summary

VAAS is a production-grade **Automatic Number Plate Recognition (ANPR) attendance management system** designed for gated facilities such as university campuses, industrial estates, and corporate car parks. It replaces manual vehicle registers with a fully automated, tamper-evident pipeline that runs on commodity hardware.

**Key capabilities at a glance:**

| Capability | Detail |
|---|---|
| Real-time ANPR | Two independent USB camera feeds processed simultaneously at ~10 fps each |
| YOLOv8 detection | Custom-trained `plate_detection.pt` localises plates with ≥ 70% confidence |
| Character recognition | `character_recognition.pt` classifies 37 classes (0–9, A–Z, background) |
| Fuzzy plate matching | LPM-MLED weighted Levenshtein corrects OCR confusion pairs (8↔B, 0↔O, 1↔I, 5↔S) |
| Shift-aware engine | Entry/exit events are classified against configurable work shifts and produce `ON_TIME`, `LATE`, `EARLY`, `VISITOR`, `SUSPENDED`, or `EXPIRED` outcomes |
| Physical barrier | Arduino Nano drives two servo-controlled barriers via PySerial; auto-discovered at startup |
| Tamper-evident log | SHA-256 hash chain across every `access_log` row — any post-hoc modification is detectable |
| Live SOC dashboard | Dark-theme operator console with MJPEG streams, SSE push events, audio ping, and exception queue |
| Analytics & export | Daily, weekly, monthly, and gate-throughput reports exportable as CSV or PDF |
| Role-based access | Three tiers: ADMIN · MANAGER · OPERATOR, each with a dedicated interface |
| Production WSGI | Waitress 32-thread pool; `GeneratorExit` teardown on MJPEG/SSE disconnect; `channel_timeout=300` |

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HARDWARE LAYER                                    │
│                                                                             │
│   USB Camera A (GATE_A)          USB Camera B (GATE_B)                     │
│         │                                │                                  │
│   DirectShow / V4L2            DirectShow / V4L2                            │
│         │                                │                                  │
│   ┌─────▼────────────────────────────────▼──────┐                          │
│   │         USBCamera (src/camera.py)            │                          │
│   └─────────────────────────────────────────────┘                          │
│                                                                             │
│   Arduino Nano (CH340 / ATmega16U2) ←── PySerial ───── BarrierController  │
│     D9 → GATE_A servo                                   (src/barrier.py)   │
│     D10 → GATE_B servo                                                      │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ raw frames (BGR ndarray)
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                          ALPR PIPELINE  (src/pipeline.py)                   │
│                                                                             │
│  Frame ──► PlateDetector ──► CLAHE ──► CharClassifier ──► LPM-MLED         │
│            (YOLOv8 detect)   enhance   (YOLOv8 classify,   (fuzzy plate     │
│            plate_detection.pt          sort left→right)     matching)       │
│                 │                                                │           │
│            PlateDebouncer ◄── 15-second cooldown window ────────┘           │
│                 │ (first occurrence only)                                    │
│                 ▼                                                            │
│          AttendanceEngine ──► GateEventResult                               │
│          (src/attendance.py)   .outcome / .access_log_id                   │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                        PERSISTENCE LAYER                                    │
│                                                                             │
│  SQLite WAL  data/vaas.db                                                   │
│  ┌──────────────────┐  ┌──────────────┐  ┌───────────────┐                 │
│  │ registered_vehicles│  │    shifts    │  │ vehicle_shifts│                │
│  └──────────────────┘  └──────────────┘  └───────────────┘                 │
│  ┌──────────────────┐  ┌──────────────┐  ┌───────────────┐                 │
│  │   access_log     │  │    users     │  │gate_rejections│                 │
│  │  + SHA-256 chain │  │  (bcrypt pw) │  │               │                 │
│  └──────────────────┘  └──────────────┘  └───────────────┘                 │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│                    WEB APPLICATION  (Flask 3 / Waitress)                    │
│                                                                             │
│  Blueprint: operator   ── /operator/dashboard        (dark SOC console)    │
│                        ── /operator/stream/<gate>.mjpg  (MJPEG push)       │
│                        ── /operator/sse               (SSE push events)    │
│                        ── /operator/exception/<id>/dispose                  │
│                                                                             │
│  Blueprint: manager    ── /manager/reports/daily|weekly|monthly            │
│                        ── /manager/reports/.../export.csv|pdf              │
│                        ── /manager/audit/verify                            │
│                                                                             │
│  Blueprint: admin      ── /admin/vehicles  /admin/shifts  /admin/users     │
│                                                                             │
│  Blueprint: api        ── /api/recent   /api/exceptions   (JSON)          │
│                                                                             │
│  SSEBroker (fan-out pub/sub, queue.Queue per subscriber)                   │
│  Waitress 32 threads · channel_timeout=300 · connection_limit=200          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Object detection | Ultralytics YOLOv8 | 8.0.196 |
| Numerical compute | NumPy + OpenCV | latest / 4.9.0.80 |
| Image enhancement | OpenCV CLAHE | — |
| Web framework | Flask | 3.0.3 |
| Production WSGI | Waitress | ≥ 3.0.0 |
| Database | SQLite WAL mode | — |
| Password hashing | bcrypt | 4.1.3 |
| Serial comms | PySerial | 3.5 |
| PDF export | ReportLab | 4.2.0 |
| Config management | python-dotenv | ≥ 1.0.0 |
| Test framework | pytest + pytest-cov | 8.1.1 |

---

## 3. Hardware Requirements

### Minimum Bill of Materials

| # | Component | Specification | Notes |
|---|---|---|---|
| 1 | Host PC | Windows 10/11, Python 3.11+, 4 GB RAM | 8 GB recommended for YOLOv8 inference |
| 2 | USB Webcam × 2 | Any DirectShow-compatible device (e.g. Logitech C920) | One per gate; indices configured in `.env` |
| 3 | Arduino Nano | ATmega328P **or** CH340-based clone | Flash `firmware/vaas_barrier.ino` before first run |
| 4 | Servo motor × 2 | 5V hobby servo (SG90 or equivalent) | GATE_A → pin D9 · GATE_B → pin D10 |
| 5 | USB-A to Mini-B cable | Standard Arduino Nano cable | Powers the board; provides the serial link |

### Camera Placement

```
  [ENTRY LANE]           [EXIT LANE]
       │                      │
  ┌────▼────┐            ┌────▼────┐
  │ Cam A   │            │ Cam B   │
  │ GATE_A  │            │ GATE_B  │
  └────┬────┘            └────┬────┘
  Servo D9                Servo D10
  (barrier arm)          (barrier arm)
       └──────── Arduino Nano ─────┘
                     │
               USB to host PC
```

> **Tip — finding your camera indices:**  
> ```python
> python -c "import cv2; [print(i, cv2.VideoCapture(i).isOpened()) for i in range(4)]"
> ```
> Set the indices that print `True` as `VAAS_CAM_A` and `VAAS_CAM_B` in `.env`.

---

## 4. Repository Structure

```
vaas/
├── start_production.bat        ← One-click Windows launcher (double-click to run)
├── serve.py                    ← Waitress WSGI runner (called by the .bat)
├── app.py                      ← Flask app factory shim for `flask --app app` (tests only)
├── requirements.txt
├── .env.example                ← Copy to .env and edit before first run
│
├── firmware/
│   └── vaas_barrier.ino        ← Arduino Nano sketch (OPEN / CLOSE servo)
│
├── src/                        ← Core library — all business logic
│   ├── config.py               ← Constants, thresholds, env-var loading
│   ├── database.py             ← SQLite WAL schema DDL + helpers
│   ├── audit.py                ← SHA-256 hash-chain functions
│   ├── lpm_mled.py             ← LPM-MLED weighted Levenshtein matcher
│   ├── clahe.py                ← CLAHE contrast enhancement
│   ├── detection.py            ← YOLOv8 plate detector wrapper
│   ├── classifier.py           ← YOLOv8 character classifier wrapper
│   ├── pipeline.py             ← End-to-end frame → plate → event pipeline
│   ├── attendance.py           ← Shift-aware attendance engine + exception handler
│   ├── barrier.py              ← Arduino serial controller (LIVE / MOCK)
│   ├── camera.py               ← USBCamera / MockCamera abstractions
│   └── analytics.py            ← SQL aggregation + CSV / PDF export
│
├── webapp/                     ← Flask application
│   ├── __init__.py             ← create_app() factory, SSEBroker
│   ├── auth.py                 ← Login / logout, requires_role() decorator
│   ├── routes/
│   │   ├── operator.py         ← Dashboard, MJPEG stream, SSE, dispose
│   │   ├── manager.py          ← Reports, CSV/PDF export, audit verify
│   │   ├── admin.py            ← Vehicle / shift / user CRUD
│   │   └── api.py              ← JSON REST endpoints
│   ├── templates/              ← Jinja2 HTML (Bootstrap 5, dark theme)
│   └── static/                 ← app.css (dark SOC theme) · app.js (SSE client)
│
├── models/
│   ├── plate_detection.pt      ← YOLOv8n fine-tuned for licence plates
│   └── character_recognition.pt← YOLOv8n fine-tuned, 37 classes (0-9, A-Z, bg)
│
├── scripts/
│   ├── __init__.py
│   ├── seed_db.py              ← First-run DB seeder (users + demo data)
│   └── find_arduino.py         ← COM-port auto-discovery + .env patcher
│
├── tests/                      ← 141 tests (pytest)
│   ├── conftest.py
│   ├── test_analytics.py       ← 20 tests
│   ├── test_attendance.py      ← 28 tests
│   ├── test_audit.py           ← 18 tests
│   ├── test_barrier.py         ←  6 tests
│   ├── test_clahe.py           ←  8 tests
│   ├── test_classifier.py      ← 15 tests
│   ├── test_detection.py       ← 12 tests
│   ├── test_integration.py     ← 12 tests
│   └── test_lpm_mled.py        ← 22 tests
│
└── data/
    ├── vaas.db                 ← SQLite database (runtime; gitignored)
    └── sample_plates/          ← Plate crop images (runtime; gitignored)
```

---

## 5. One-Click Deployment

**Prerequisites:** Python 3.11+ on PATH · Arduino flashed and plugged in · two USB cameras connected.

```
Double-click  start_production.bat
```

The launcher executes **seven fully automated steps** with no manual intervention required on subsequent runs:

```
[1/7] Checking Python installation ...
[2/7] Setting up virtual environment ...
[3/7] Installing / verifying dependencies ...
[4/7] Checking environment configuration ...
[5/7] Checking database ...
[6/7] Detecting Arduino COM port ...
[7/7] Starting VAAS server ...
```

### What each step does

| Step | Action | First run | Subsequent runs |
|---|---|---|---|
| **1** | Verifies `python` is on PATH; prints version | Required | Instant check |
| **2** | Creates `venv\` if absent; activates it | Creates venv | Activates existing |
| **3** | Runs `pip install -r requirements.txt --quiet` | Downloads all packages | Verifies, no-ops if current |
| **4** | Checks `.env` exists and `VAAS_SECRET_KEY` is not the placeholder | Copies `.env.example` → `.env`, opens Notepad for editing, then **exits** so you can save | Instant check |
| **5** | Seeds `data/vaas.db` if absent | Prompts for admin password, auto-generates manager/operator passwords | Skipped if DB exists |
| **6** | Runs `scripts/find_arduino.py --quiet` | Scans all COM ports, writes detected port to `.env` | Re-scans; updates `.env` if port changed |
| **7** | Runs `python serve.py --check-env` then `python serve.py` | Validates config, starts Waitress | Same |

### First-run walkthrough

1. Double-click `start_production.bat`.
2. Step 4 opens `.env` in Notepad. Set **`VAAS_SECRET_KEY`** to the output of:
   ```
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Save and close Notepad.
3. Re-run `start_production.bat`. Step 5 prompts for an admin password — type one and press Enter. Copy the auto-generated **manager** and **operator** passwords shown on screen.
4. Step 6 detects your Arduino automatically (e.g. `Arduino detected on COM4 — .env updated`).
5. Step 7 starts the server. Open **http://localhost:5000** in your browser.

> **Arduino not found at Step 6?** VAAS continues in software-only mode (barrier commands are logged but the servo does not move). Plug in the Arduino and re-run the launcher to auto-detect it.

---

## 6. Manual Setup

If you prefer a shell-based setup:

```bash
# 1. Clone / unzip the project
cd vaas

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate      # Linux / macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env
copy .env.example .env         # Windows
# cp .env.example .env           # Linux / macOS
# Edit .env — minimum: set VAAS_SECRET_KEY

# 5. (Optional) Auto-detect Arduino COM port
python scripts/find_arduino.py

# 6. Seed the database
python scripts/seed_db.py

# 7. Start the server
python serve.py
```

Navigate to **http://localhost:5000** and log in.

---

## 7. Environment Variables Reference

All variables live in `.env` (created from `.env.example`). Shell / OS environment variables always take precedence over `.env` values.

| Variable | Default | Required | Description |
|---|---|---|---|
| `VAAS_SECRET_KEY` | *(none)* | **Yes** | Flask session signing key. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `VAAS_HW_MODE` | `LIVE` | Yes | `LIVE` — real cameras + Arduino. `MOCK` — placeholder MJPEG, no serial. |
| `VAAS_ARDUINO_PORT` | `COM3` | Yes (LIVE) | Windows COM port of the Arduino Nano. Auto-set by `find_arduino.py`. |
| `VAAS_CAM_A` | `0` | Yes (LIVE) | DirectShow index for the GATE_A camera. |
| `VAAS_CAM_B` | `1` | Yes (LIVE) | DirectShow index for the GATE_B camera. |
| `VAAS_GATE_A_DIR` | `ENTRY` | No | Direction label for GATE_A (`ENTRY` or `EXIT`). |
| `VAAS_GATE_B_DIR` | `EXIT` | No | Direction label for GATE_B (`ENTRY` or `EXIT`). |
| `VAAS_HOST` | `0.0.0.0` | No | Bind address. Use `127.0.0.1` for localhost-only. |
| `VAAS_PORT` | `5000` | No | HTTP port. |
| `VAAS_THREADS` | `32` | No | Waitress thread-pool size. 32 handles 2× MJPEG + SSE + HTTP with headroom. |
| `VAAS_PLATE_CONF` | `0.70` | No | YOLOv8 plate-detection confidence threshold. |
| `VAAS_CHAR_CONF` | `0.65` | No | YOLOv8 character-classifier confidence threshold. |
| `VAAS_DEBOUNCE_SECS` | `15` | No | Seconds to suppress repeat plate events (prevents double-counting). |
| `VAAS_EXCEPTION_TIMEOUT` | `30` | No | Seconds before an unattended VISITOR exception auto-rejects. |
| `VAAS_SESSION_HOURS` | `8` | No | Web session idle timeout in hours. |

---

## 8. Role-Based Access Control

VAAS enforces a three-tier RBAC model. Each role inherits all permissions of the tier below it.

```
ADMIN  ▶  MANAGER  ▶  OPERATOR
```

### OPERATOR — Live Gate Monitor

The operator console is a dark-themed SOC (Security Operations Centre) dashboard designed for sustained eyes-on monitoring.

| Feature | Detail |
|---|---|
| **Live MJPEG streams** | Two side-by-side panels showing annotated camera feeds. Green bounding boxes indicate a freshly read plate; grey boxes indicate a plate suppressed by the debounce cooldown (`[cd]` label). |
| **Gate status indicators** | Pulsing green border = gate open (ADMIT). Pulsing red border = gate alert (REJECT/VISITOR). Auto-resets after 3 seconds. |
| **Real-time event feed** | SSE push from server — new rows appear at the top of the events table without a page reload. A Web Audio API 880 Hz tone plays on each new event. |
| **Exception queue** | Vehicles with `VISITOR` status appear here pending human review. Three actions: **Admit** (opens barrier, updates status), **Reject** (logs rejection), **Register** (redirects to vehicle registration form with plate pre-filled). Unattended exceptions auto-reject after 30 seconds. |
| **UTC clock** | Live UTC timestamp in the navbar header. |

**URL:** `/operator/dashboard`  
**MJPEG streams:** `/operator/stream/GATE_A.mjpg` · `/operator/stream/GATE_B.mjpg`

---

### MANAGER — Analytics & Compliance

The manager dashboard provides read-only reporting and audit access.

| Feature | Detail |
|---|---|
| **Daily report** | Per-vehicle attendance breakdown for a selected date: entry time, exit time, dwell duration, status, compliance flag. |
| **Weekly report** | Aggregated weekly attendance per registered vehicle with compliance rate. |
| **Monthly report** | Month-level aggregation with total days present, average dwell time, and late-arrival count. |
| **Gate throughput** | Hourly/daily vehicle count per gate; average dwell time. |
| **CSV export** | One-click download of any report as a UTF-8 comma-separated file. |
| **PDF export** | One-click download of any report as a formatted A4 PDF via ReportLab. |
| **Audit chain verifier** | Runs `src/audit.verify_chain()` against the live database and displays a pass/fail result with the first broken row highlighted if tampering is detected. |

**URL prefix:** `/manager/`

---

### ADMIN — System Configuration

The admin panel provides full CRUD control over the system configuration.

| Resource | Operations |
|---|---|
| **Vehicles** | List · Add · Edit · Suspend/Reinstate · Delete. Stores plate number, owner name, contact, status (`ACTIVE` / `SUSPENDED` / `EXPIRED`), and shift assignment. |
| **Shifts** | List · Add · Edit · Delete. Each shift has a name, start/end time, and a set of active weekdays. Multiple shifts can be defined to support 24/7 facilities. |
| **Users** | List · Add · Edit · Change password · Delete. Roles: `ADMIN` · `MANAGER` · `OPERATOR`. Passwords are stored as bcrypt hashes (cost factor 12). |

**URL prefix:** `/admin/`

---

### JSON API (all authenticated roles)

| Endpoint | Response |
|---|---|
| `GET /api/recent` | Last 20 `access_log` entries as a JSON array |
| `GET /api/exceptions` | All pending `VISITOR` entries as a JSON array |

---

## 9. ALPR Pipeline Detail

The end-to-end pipeline runs inside a dedicated background thread per gate (`_camera_worker` in `webapp/routes/operator.py`) so it never blocks the Waitress HTTP thread pool.

```
raw frame (BGR ndarray, 640×480 typical)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 1 — Plate Detection  (src/detection.py)      │
│  Model: models/plate_detection.pt  (YOLOv8n)        │
│  Conf threshold: VAAS_PLATE_CONF = 0.70             │
│  Output: list[PlateDetection]                        │
│          .bbox (x1,y1,x2,y2)                        │
│          .confidence                                 │
│          .crop (BGR ndarray)                        │
└──────────────────────┬──────────────────────────────┘
                       │ plate crop(s)
                       ▼
┌─────────────────────────────────────────────────────┐
│  Stage 2 — CLAHE Enhancement  (src/clahe.py)        │
│  BGR → GRAY → CLAHE(clipLimit=3.0, tile=8×8) → BGR  │
│  Normalises uneven lighting across plate characters  │
└──────────────────────┬──────────────────────────────┘
                       │ enhanced crop
                       ▼
┌─────────────────────────────────────────────────────┐
│  Stage 3 — Character Classification (src/classifier) │
│  Model: models/character_recognition.pt  (YOLOv8n)  │
│  Classes: 37  (digits 0-9, letters A-Z, background) │
│  Conf threshold: VAAS_CHAR_CONF = 0.65              │
│  Characters sorted left→right by x-centre           │
│  Output: (raw_plate_string, mean_confidence)         │
└──────────────────────┬──────────────────────────────┘
                       │ e.g. "CB8-1Z34"
                       ▼
┌─────────────────────────────────────────────────────┐
│  Stage 4 — LPM-MLED Correction  (src/lpm_mled.py)  │
│  Weighted Levenshtein edit distance                  │
│  Confusion pairs (cost 0.1): 8↔B  0↔O  1↔I  5↔S   │
│  Other substitutions: cost 1.0                      │
│  Distance normalised by max(len(raw), len(candidate))│
│  Threshold: LPM_THRESHOLD = 0.5                     │
│  Matched against all registered plate numbers       │
│  Output: corrected plate string | None               │
└──────────────────────┬──────────────────────────────┘
                       │ e.g. "CBA-1234" (corrected)
                       ▼
┌─────────────────────────────────────────────────────┐
│  Stage 5 — Plate Debouncer  (src/pipeline.py)       │
│  Thread-safe cooldown dict {plate: monotonic_time}   │
│  Default cooldown: VAAS_DEBOUNCE_SECS = 15s         │
│  Prevents duplicate gate events at 10 fps           │
│  Debounced plates drawn in grey with [cd] label     │
└──────────────────────┬──────────────────────────────┘
                       │ first occurrence only
                       ▼
┌─────────────────────────────────────────────────────┐
│  Stage 6 — Attendance Engine (src/attendance.py)    │
│  Looks up vehicle in registered_vehicles            │
│  Determines active shift for current time           │
│  Classifies outcome:                                │
│    ON_TIME_ENTRY  /  LATE_ARRIVAL  /  EARLY_ARRIVAL │
│    ON_TIME_EXIT   /  EARLY_DEPARTURE                │
│    VISITOR   (unknown plate → exception queue)      │
│    SUSPENDED / EXPIRED  → gate_rejections log       │
│  Publishes event via SSEBroker                      │
│  Commands BarrierController (OPEN / no-op)          │
│  Inserts access_log row + SHA-256 hash              │
└─────────────────────────────────────────────────────┘
```

---

## 10. Audit Chain & Data Integrity

Every row inserted into `access_log` is cryptographically linked to all previous rows via a SHA-256 hash chain, making post-hoc data tampering detectable.

### Hash formula

```
hash_n = SHA256(
    JSON({
        "plate":     plate_number,
        "ts":        timestamp,
        "gate":      gate_id,
        "dir":       direction,
        "prev_hash": hash_{n-1}
    },
    sort_keys=True, separators=(",",":"))
)
```

Row 1 uses `prev_hash = SHA256("VAAS-GENESIS-2026")` as its seed.

### Verification

```bash
# Via the web UI (MANAGER role):
#   Navigate to  Manager → Audit → Verify Chain

# Via command line:
python -c "
import sqlite3, sys
sys.path.insert(0,'.')
from src.database import connect
from src.audit import verify_chain
conn = connect('data/vaas.db')
r = verify_chain(conn)
print('PASS' if r.intact else f'FAIL at row {r.first_broken_id}')
"
```

### Tampering demonstration

```bash
# Corrupt a row
sqlite3 data/vaas.db "UPDATE access_log SET plate_number='TAMPERED' WHERE id=3"

# Verify — reports the first broken link
python -c "
import sqlite3, sys; sys.path.insert(0,'.')
from src.database import connect; from src.audit import verify_chain
r = verify_chain(connect('data/vaas.db'))
print('intact:', r.intact, '| first_broken_id:', r.first_broken_id)
"
# intact: False | first_broken_id: 3
```

---

## 11. Running the Test Suite

141 tests covering all modules — no network access required. YOLOv8 model files in `models/` are required for the detection and classifier tests.

```bash
# Full suite with coverage report (recommended)
pytest

# Quick run — no coverage overhead
pytest --no-cov

# Specific module
pytest tests/test_audit.py -v

# Integration tests only
pytest tests/test_integration.py -v

# Skip tests that need model files
pytest --ignore=tests/test_detection.py --ignore=tests/test_classifier.py --no-cov
```

### Expected results

```
141 passed in ~17 s

Coverage highlights:
  src/audit.py         100%
  src/analytics.py      99%
  src/lpm_mled.py       97%
  src/config.py         95%
  src/classifier.py     90%
  src/barrier.py        86%
  src/database.py       89%
  src/attendance.py     79%
```

---

## 12. Arduino Firmware

File: `firmware/vaas_barrier.ino`

### Upload instructions

1. Open **Arduino IDE 2.x** (or VS Code + Arduino extension).
2. Select board: **Arduino Nano** · Processor: **ATmega328P** (or **ATmega328P Old Bootloader** for clone boards).
3. Select the correct COM port.
4. Click **Upload**.
5. Open Serial Monitor at **9600 baud** — you should see `VAAS_BARRIER_READY`.

### Serial protocol

| Command (host → Arduino) | Effect |
|---|---|
| `OPEN:GATE_A\n` | Rotates GATE_A servo to open position; auto-closes after 5 seconds |
| `CLOSE:GATE_A\n` | Rotates GATE_A servo to closed position immediately |
| `OPEN:GATE_B\n` | Same for GATE_B (pin D10) |
| `CLOSE:GATE_B\n` | Same for GATE_B |

| Response (Arduino → host) | Meaning |
|---|---|
| `ACK:OPEN:GATE_A` | Command acknowledged |
| `ACK:CLOSE:GATE_B` | Command acknowledged |
| `ERR:UNKNOWN` | Unrecognised command received |

> **Clone boards (CH340 chip):** Windows may need the [CH340 driver](https://www.wch-ic.com/downloads/CH341SER_EXE.html) installed. After installation the board appears in Device Manager under *Ports (COM & LPT)*. `find_arduino.py` detects CH340 boards automatically.

---

## 13. Utility Scripts

### `scripts/seed_db.py` — Database seeder

```bash
python scripts/seed_db.py
```

Creates the full schema and inserts:
- **2 shifts:** `DAY_SHIFT` (Mon–Fri 08:00–17:00) · `NIGHT_SHIFT` (Mon–Sat 20:00–05:00)
- **10 demo vehicles** with Sri Lankan plate formats assigned to shifts
- **3 user accounts:** `admin` (password prompted) · `manager` (auto-generated) · `operator` (auto-generated)

Also importable from tests: `from scripts.seed_db import seed`.

---

### `scripts/find_arduino.py` — COM-port auto-discovery

```bash
# Scan + write result to .env (used automatically by start_production.bat)
python scripts/find_arduino.py

# Preview only — no file changes
python scripts/find_arduino.py --dry-run

# Silent mode (for scripting)
python scripts/find_arduino.py --quiet
```

Scans every active COM port using `serial.tools.list_ports` and matches against known Arduino USB-serial chip identifiers:

| Chip | Boards |
|---|---|
| ATmega16U2 | Official Arduino Uno / Nano / Mega |
| CH340 / CH341 | Most Chinese clone Nano boards |
| CP2102 / CP2104 | SparkFun boards, NodeMCU |
| FT232RL | Adafruit boards, older clones |
| PL2303 | Very old USB-serial cables |

**Exit codes:** `0` = found and `.env` updated · `1` = no Arduino found · `0` (with warning) = multiple candidates (first is used).

---

## 14. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `FileNotFoundError: plate_detection.pt` | Models not present | Ensure `models/plate_detection.pt` and `models/character_recognition.pt` exist |
| `VAAS_SECRET_KEY` error at startup | Placeholder value in `.env` | Generate a key: `python -c "import secrets; print(secrets.token_hex(32))"` and paste it into `.env` |
| `Failed to open Arduino on COMx` | Wrong port or missing driver | Run `python scripts/find_arduino.py --dry-run`; install CH340 driver if board not listed |
| Stream shows "waiting for camera" | Camera worker still loading YOLOv8 | Normal on first load — wait 3–5 s for model initialisation |
| Camera index error / black frame | Wrong `VAAS_CAM_A` / `VAAS_CAM_B` | Run `python -c "import cv2; [print(i, cv2.VideoCapture(i).isOpened()) for i in range(4)]"` to list valid indices |
| `Task queue depth` warnings in Waitress | Thread pool under pressure | Increase `VAAS_THREADS` in `.env` (default is already 32; increase to 64 if running many concurrent clients) |
| SSE dashboard not updating | Browser blocked `text/event-stream` | Check browser console; ensure no corporate proxy is buffering the SSE response |
| Audit chain FAIL on fresh DB | Rows inserted outside VAAS | Only insert rows via `AttendanceEngine.process_gate_event()`; direct SQLite edits break the chain |
| `pip install` fails | No internet / proxy | Install offline: `pip install --no-index --find-links=./wheels -r requirements.txt` after pre-downloading wheels |
| Tests fail: `ModuleNotFoundError` | `scripts/__init__.py` missing | File should exist; if absent run `echo.> scripts\__init__.py` |

---

## Licence

This project was developed as an academic submission for the University of Plymouth BSc (Hons) Software Engineering programme. All source code is the original work of the author.

Pre-trained YOLOv8 model weights are derived from [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) (AGPL-3.0). All other dependencies retain their respective licences as listed in `requirements.txt`.

---

*Built with Python · YOLOv8 · Flask · SQLite · Arduino · and a lot of coffee.*
