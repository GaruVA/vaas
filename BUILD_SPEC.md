# Claude Code Build Prompt — VAAS (CDL Edition)
> **How to use this file**
> Save as `BUILD_SPEC.md` in an empty project folder. Run `claude` and your first message is:
>
> > Read `BUILD_SPEC.md` end to end before doing anything else. Then ask me the three setup questions in §0. After I answer, work through Phase 0 → Phase 9 in order. Run pytest after each phase, report progress at every phase boundary, and stop for confirmation before moving on. The spec is authoritative — the figures in §1 and the test counts in §7 are graded artefacts; if you find yourself wanting to change them, ask first.
>
> The student already has the GitHub repo at `https://github.com/GaruVA/vaas.git` — Claude Code is rebuilding the system in the current folder, not cloning that. Trained models will be copied into `models/` once requested.

---

## §0. Things you must tell me first

Before any code, ask these three questions in a single batched message:

1. **Trained model paths.** Default: `models/plate_detector.pt` (YOLOv8n plate detector, mAP@0.5 = 94.7%) and `models/char_classifier.pt` (YOLOv8 37-class character classifier). If they're elsewhere, the user will copy them in.
2. **Hardware mode.** Default to `MOCK` (no camera, no Arduino) for development. `LIVE` mode (1080p WDR IP camera + Arduino Nano on `/dev/ttyUSB0` at 9600 baud) must be a single env-flag flip.
3. **Sample plate images for the demo feed.** If a folder exists, take its path. Otherwise generate 12 synthetic plate-like images using OpenCV (Sri Lankan formats: `WP-CAB-1234`, `KL-5678`, `CAB-1234`, etc.) so the demo runs out of the box.

Once these are answered, proceed without further interruption until Phase 1 tests pass.

---

## §1. Project context — non-negotiable framing

You are building **VAAS — Vehicle Attendance and Analytics System**, the final year project (PUSL3190) of a BSc Software Engineering student at University of Plymouth (Sri Lanka Campus). The system is fully specified across ten thesis chapters and a confirmed-implementation-facts audit. **Those documents are the source of truth.**

**Customer.** Colombo Dockyard PLC (CDL), Sri Lanka's largest ship repair / shipbuilding enterprise. Operates 24/7 across three eight-hour shifts inside the Port of Colombo. Owns four graving drydocks, processes 200+ vessels annually, employs 1,400–3,000 staff plus subcontractor personnel during refits.

**The real problem.** CDL's UHF RFID gate system is broken on two fronts: (a) the adjacent SLPA harbour authority operates an independent RFID network on the same UHF bands, generating ID collision and dual-card ambiguity; (b) because RFID authenticates the card and not the vehicle, employees scan their card while entering as pedestrians or passengers — fraud indistinguishable from the EM-induced false positives. Result: 15–20% discrepancy between RFID records and actual parking occupancy, costing CDL ~LKR 2.7–3.6M/year in unjustified fuel allowance payments and ~20 hours/month of Finance Department investigation time.

**The solution.** Replace RFID with a computer-vision pipeline that recognises the physical vehicle. The licence plate is optically bound to the vehicle, immune to EM interference, and unforgeable without physical presence. Build a single edge-deployed Python application that does:

1. **ALPR pipeline** — YOLOv8 plate detection → CLAHE on LAB L-channel → 37-class character classifier → LPM-MLED post-correction.
2. **Shift-aware attendance engine** — CDL's three shifts (07:00–15:00 / 15:00–23:00 / 23:00–07:00), 15-minute grace period (Port queue), midnight boundary handling, full thirteen-status classification.
3. **CDL Specialisation Layer** — drydock zone topology, vessel-project attribution, subcontractor company register, per-project attendance summary.
4. **SHA-256 hash-chained audit log** — two-step INSERT/UPDATE binding the database-assigned row PK into every hash, defeating both field-tampering and row-reordering attacks.
5. **Web dashboard** — Flask + Bootstrap 5, three RBAC roles (OPERATOR, MANAGER, ADMIN), live MJPEG annotated feed, SSE exception queue, ten enterprise reports with CSV/PDF export.

**Trained models.** Two YOLOv8 `.pt` files exist already. **You will not train models.** You will load and use them. They are excluded from the automated test count by design (CI has no GPU and no `ultralytics` runtime).

---

## §2. Confirmed implementation facts — graded artefacts, do not deviate

These figures are audit-confirmed (May 2026). Use them exactly. Do not round, estimate, or "improve" them.

### Test suite
- **156 passing tests, 0 failures**, across 8 test files.
- Breakdown: `test_clahe.py` (8), `test_lpm_mled.py` (22), `test_attendance.py` (28), `test_audit.py` (20), `test_projects.py` (15), `test_analytics.py` (45), `test_barrier.py` (6), `test_integration.py` (12).
- `test_classifier.py` (15 tests) and `test_detection.py` exist but **fail at import** in CI because `ultralytics` is not installed. This is **by design** — they are excluded from the non-YOLO count.

### ALPR
- **Plate detector:** YOLOv8n, **mAP@0.5 = 94.7%** on held-out test set.
- **End-to-end accuracy: 91.3%** (post-LPM-MLED, on full test set).
- **CLAHE:** BGR → LAB, apply on **L channel only**, `clipLimit=3.0`, `tileGridSize=(8,8)`, return BGR uint8. *Not* full-RGB CLAHE.
- **LPM-MLED:** confusion pairs `{0,O}`, `{1,I}`, `{5,S}`, `{8,B}` at substitution cost **0.1**; all other substitutions cost **1.0**; insertions/deletions cost **1.0**; normalisation `dist / max(len(raw), len(candidate))`; **strict** acceptance threshold `< 0.5` (a normalised distance of exactly 0.500 must be **rejected**).

### Attendance engine — full status set (13 values)
`ON_TIME_ENTRY`, `LATE_ARRIVAL`, `EARLY_ARRIVAL`, `ON_TIME_EXIT`, `EARLY_DEPARTURE`, `OVERSTAY`, `VISITOR`, `VISITOR_ADMITTED`, `VISITOR_REJECTED`, `VISITOR_PENDING_REGISTRATION`, `VISITOR_TIMEOUT_REJECT`, `SUSPENDED`, `EXPIRED`.

- **Midnight boundary:** modular timedelta arithmetic. If `start_time >= end_time` the shift crosses midnight; add `timedelta(days=1)` to `end_dt` for comparison.
- **Grace period:** read at runtime from `shifts.grace_period_minutes`. **No hardcoded value** anywhere in `attendance.py`.
- **Overstay race fix:** conditional UPDATE with **double NOT EXISTS subquery** to make the operation idempotent under concurrent threads.

### CDL Specialisation Layer (`src/projects.py`)
- **17 public functions.** (Audit initially counted 16 but enumeration confirms 17.)
- `close_project`: **soft-removes** assignments by setting `removed_at` to the closure timestamp. Not a hard delete.
- `assign_vehicle_to_project`: validates `company_id` is non-empty **AND** exists in `subcontractor_companies` table when role is SUBCONTRACTOR. Raises descriptive `ValueError` on either failure.
- `get_project_attendance_summary`: uses `COUNT(DISTINCT DATE(al.timestamp))` for `days_present`. Distinct calendar dates only — duplicates within a day must not double-count.

### Audit chain (`src/audit.py`)
- **Two-step pattern**: INSERT row with placeholder `row_hash = 'PENDING'`, retrieve auto-assigned PK, compute SHA-256 over JSON payload `{id, plate_number, timestamp, gate_id, direction, prev_hash}` (sorted keys, compact separators), UPDATE the row with the real hash.
- **PK is in the payload** — this defeats row-reordering attacks. Tests must verify this.
- `verify_chain(conn) -> ChainVerificationResult` exists, walks `access_log` ORDER BY id, recomputes every hash, returns OK / TAMPERED-at-row.
- **`ChainVerificationResult` dataclass fields**: `ok: bool`, `first_bad_id: int | None`, `reason: str | None`, `verified_at: str`, `rows_checked: int`. There is **no** `.status` string field — use `.ok` for pass/fail.

### Database
- **12 tables.** The `access_log` table has both `zone_id TEXT` and `project_code TEXT` columns. They also appear in the migrations dict for backward compatibility with older databases.

### Analytics (`src/analytics.py`)
- **10 named report functions** + `csv_string`, `export_csv`, `export_pdf`.
- `ohs_compliance_report`: **LEFT JOIN** so all registered vehicles appear, including those with zero gate events.

### Flask RBAC
- Three roles. `ROLE_RANK = {"OPERATOR": 1, "MANAGER": 2, "ADMIN": 3}` in `webapp/auth.py`.
- `requires_role(min_role)` decorator enforces minimum rank by integer comparison.
- `users.role` has CHECK constraint at DB level.
- Routes split: `admin.py` (ADMIN only), `manager.py` (MANAGER+), `operator.py` (any auth), `api.py` (any auth).

### Performance
- Gate event p95 latency: **294 ms** (NFR-01 budget 500 ms — 41% margin).
- Concurrent dashboard sessions tested: **8** (NFR-05 minimum 5).
- WSGI: **Waitress** (not Flask dev server in production).

### Security
- bcrypt cost factor **12** for password hashes.
- Session timeout **8 hours**.
- All SQL parameterised. Input validated at the API boundary.
- Plate-crop retention **≤ 90 days** (PDPA 2022 compliance).

### CDL branding
- Primary: Fun Blue `#1B3F95`. Accent: yellow `#f4bd0f`. Safety green: `#76bd33`. Use these for the dashboard chrome and PDF report headers.

---

## §3. Tech stack — pin to these

| Component             | Tech                       | Version  |
| --------------------- | -------------------------- | -------- |
| Language              | Python                     | 3.11+ (3.13 ideal; flag if unavailable) |
| Object detection      | `ultralytics`              | 8.0.196 (installed locally only — not required for CI) |
| CV library            | `opencv-python`            | 4.9.0.80 |
| Web framework         | `Flask`                    | 3.0.3    |
| WSGI server           | `waitress`                 | 3.0.0    |
| Database              | SQLite stdlib (`sqlite3`)  | 3.45+ (WAL) |
| PDF                   | `reportlab`                | 4.2.0    |
| Hardware serial       | `pyserial`                 | 3.5      |
| Password hashing      | `bcrypt`                   | 4.1.3    |
| Test runner           | `pytest`                   | 8.1.1    |
| Coverage              | `pytest-cov`               | latest   |
| Numerics              | `numpy`                    | as pinned by ultralytics |

Two requirements files:
- `requirements.txt` — base runtime (no ultralytics).
- `requirements-ml.txt` — adds `ultralytics`, `torch`. For local dev with the trained models. CI installs only the base file, which is why YOLO test files fail at import there.

---

## §4. Project structure — create exactly this layout

```
vaas/
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── detection.py            # YOLOv8 plate detector (Stage 1)
│   ├── clahe.py                # LAB L-channel CLAHE
│   ├── classifier.py           # YOLOv8 37-class char detector (Stage 2)
│   ├── lpm_mled.py             # Weighted Levenshtein post-correction
│   ├── attendance.py           # Shift-aware engine, 13 statuses
│   ├── audit.py                # SHA-256 chain (two-step INSERT/UPDATE)
│   ├── projects.py             # CDL Specialisation Layer (17 functions)
│   ├── analytics.py            # 10 report functions + CSV/PDF
│   ├── barrier.py              # Arduino Nano serial controller (MOCK/LIVE)
│   ├── camera.py               # USB / mock camera abstraction
│   └── pipeline.py             # Frame -> recognition -> gate event
│
├── webapp/
│   ├── __init__.py             # Flask application factory
│   ├── auth.py                 # bcrypt, sessions, ROLE_RANK, requires_role
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── operator.py         # Tablet dashboard, MJPEG, SSE, exception disposition
│   │   ├── manager.py          # Reports, exports, audit verify
│   │   ├── admin.py            # Vehicles, shifts, projects, zones, companies, users
│   │   └── api.py              # JSON endpoints (any auth)
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/login.html
│   │   ├── operator/*.html
│   │   ├── manager/*.html
│   │   └── admin/*.html
│   └── static/
│       ├── css/cdl.css         # CDL Fun Blue / yellow / green
│       └── js/app.js           # SSE listener, exception buttons, MJPEG hookup
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_clahe.py           # 8
│   ├── test_lpm_mled.py        # 22
│   ├── test_attendance.py      # 28
│   ├── test_audit.py           # 20
│   ├── test_projects.py        # 15
│   ├── test_analytics.py       # 45
│   ├── test_barrier.py         # 6
│   ├── test_integration.py     # 12
│   ├── test_classifier.py      # 15 — YOLO-dependent, fails at import in CI by design
│   └── test_detection.py       # YOLO-dependent, excluded from non-YOLO count
│
├── models/                     # plate_detector.pt, char_classifier.pt
├── data/
│   ├── sample_plates/
│   └── vaas.db                 # WAL on first run
├── scripts/
│   ├── seed_db.py              # 12 tables, demo zones/projects/companies/vehicles/users
│   ├── verify_chain.py         # CLI wrapper around audit.verify_chain
│   ├── run_demo.py             # MOCK feed -> pipeline end-to-end
│   └── serve.py                # Waitress launcher
├── requirements.txt
├── requirements-ml.txt
├── pytest.ini
├── .env.example
├── README.md
└── BUILD_SPEC.md               # this file
```

---

## §5. Database — twelve tables, exact DDL

WAL mode, `synchronous = NORMAL`, FKs ON. ISO-8601 UTC timestamps everywhere. JSON-typed columns are TEXT containing valid JSON.

### IMPORTANT: WAL + overlayfs

**`scripts/seed_db.py` and any script that writes a permanent DB file must use this pattern:**

```python
import tempfile, shutil
with tempfile.TemporaryDirectory() as tmpdir:
    tmp_db = Path(tmpdir) / 'vaas.db'
    conn = sqlite3.connect(str(tmp_db))
    conn.execute('PRAGMA journal_mode = WAL')
    # ... seed all data ...
    conn.close()
    shutil.copy2(str(tmp_db), str(target_path))
```

Reason: Docker / development environments frequently mount the workspace on an `overlayfs` or similar union filesystem that does **not** support WAL sidecar files (`.shm`, `.wal`). Building the DB in `/tmp` (which is always `tmpfs`) and then copying avoids a `sqlite3.OperationalError: disk I/O error` that will otherwise occur on every connection attempt.

**`database.connect()`** must try WAL then fall back gracefully:

```python
try:
    conn.execute('PRAGMA journal_mode = WAL')
except sqlite3.OperationalError:
    conn.execute('PRAGMA journal_mode = MEMORY')
    logger.warning('WAL journal unavailable; using MEMORY journal mode')
```

**`executescript()` and WAL:** `executescript()` issues an implicit COMMIT internally. **Never combine PRAGMA statements and DDL in the same `executescript()` call when WAL is active** — the implicit COMMIT will conflict. Keep `_DDL_SQL` as a pure DDL string; set PRAGMAs in separate `conn.execute()` calls before or after.

### Core (8 tables)

```sql
CREATE TABLE IF NOT EXISTS registered_vehicles (
    plate_number        TEXT PRIMARY KEY,
    vehicle_category    TEXT NOT NULL DEFAULT 'CONTRACTOR'
                        CHECK(vehicle_category IN
                              ('STAFF','CONTRACTOR','MANAGEMENT','FLEET',
                               'VISITOR','EMERGENCY','MAINTENANCE')),
    vehicle_type        TEXT NOT NULL DEFAULT 'CAR'
                        CHECK(vehicle_type IN
                              ('CAR','VAN','TRUCK','MOTORCYCLE','UTILITY')),
    contractor_name     TEXT,
    department          TEXT,
    company_id          TEXT REFERENCES subcontractor_companies(company_id),
    registration_status TEXT NOT NULL DEFAULT 'ACTIVE'
                        CHECK(registration_status IN
                              ('ACTIVE','SUSPENDED','EXPIRED')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS shifts (
    shift_id             TEXT PRIMARY KEY,
    shift_name           TEXT NOT NULL,
    start_time           TEXT NOT NULL,        -- 'HH:MM'
    end_time             TEXT NOT NULL,        -- 'HH:MM' (may be < start for overnight)
    days_of_week         TEXT NOT NULL,        -- JSON array: ["MON","TUE",...]
    permitted_gates      TEXT NOT NULL,        -- JSON array of gate ids
    grace_period_minutes INTEGER NOT NULL DEFAULT 15
);

CREATE TABLE IF NOT EXISTS vehicle_shifts (
    plate_number TEXT NOT NULL REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,
    shift_id     TEXT NOT NULL REFERENCES shifts(shift_id) ON DELETE CASCADE,
    PRIMARY KEY (plate_number, shift_id)
);

CREATE TABLE IF NOT EXISTS vehicle_assignments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plate_number  TEXT    NOT NULL REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,
    is_active     INTEGER NOT NULL DEFAULT 1,
    assigned_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    removed_at    TEXT
);

CREATE TABLE IF NOT EXISTS access_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number       TEXT    NOT NULL,
    timestamp          TEXT    NOT NULL,
    gate_id            TEXT    NOT NULL,
    direction          TEXT    NOT NULL CHECK(direction IN ('ENTRY','EXIT')),
    dwell_time_seconds REAL,
    shift_id           TEXT,
    confidence_score   REAL,
    status             TEXT    NOT NULL DEFAULT 'UNKNOWN',
    zone_id            TEXT,                    -- CDL specialisation
    project_code       TEXT,                    -- CDL specialisation
    row_hash           TEXT    NOT NULL DEFAULT 'PENDING',
    plate_crop_b64     TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'OPERATOR'
                  CHECK(role IN ('ADMIN','MANAGER','OPERATOR')),
    full_name     TEXT,
    employee_no   TEXT,
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS gate_rejections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number     TEXT,
    timestamp        TEXT NOT NULL,
    gate_id          TEXT NOT NULL,
    reason           TEXT NOT NULL,
    confidence_score REAL,
    plate_crop_b64   TEXT
);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    user_id       INTEGER REFERENCES users(id),
    username      TEXT    NOT NULL,
    action        TEXT    NOT NULL CHECK(action IN ('CREATE','UPDATE','DELETE','ASSIGN')),
    entity_type   TEXT    NOT NULL,
    entity_id     TEXT,
    delta_json    TEXT
);
```

### CDL Specialisation Layer (4 tables)

```sql
CREATE TABLE IF NOT EXISTS cdl_zones (
    zone_id          TEXT PRIMARY KEY,
    zone_name        TEXT NOT NULL,
    zone_type        TEXT NOT NULL CHECK(zone_type IN
                          ('DRYDOCK','BERTH','WORKSHOP','ADMIN','SECURITY')),
    associated_gates TEXT NOT NULL,
    vehicle_capacity INTEGER NOT NULL DEFAULT 50
);

CREATE TABLE IF NOT EXISTS subcontractor_companies (
    company_id      TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    contact_name    TEXT,
    contact_phone   TEXT,
    contact_email   TEXT,
    approval_status TEXT NOT NULL DEFAULT 'APPROVED'
                    CHECK(approval_status IN ('APPROVED','SUSPENDED','EXPIRED')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS projects (
    project_code     TEXT PRIMARY KEY,
    vessel_name      TEXT NOT NULL,
    zone_id          TEXT NOT NULL REFERENCES cdl_zones(zone_id),
    start_date       TEXT NOT NULL,
    end_date         TEXT,
    status           TEXT NOT NULL DEFAULT 'ACTIVE'
                     CHECK(status IN ('ACTIVE','CLOSED')),
    project_manager  TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS project_vehicle_assignments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_code  TEXT NOT NULL REFERENCES projects(project_code) ON DELETE CASCADE,
    plate_number  TEXT NOT NULL REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK(role IN
                       ('EMPLOYEE','SUBCONTRACTOR','SUPERVISOR','VISITOR')),
    company_id    TEXT REFERENCES subcontractor_companies(company_id),
    assigned_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    removed_at    TEXT
);
```

### Indices

```sql
CREATE INDEX IF NOT EXISTS idx_access_log_plate     ON access_log(plate_number);
CREATE INDEX IF NOT EXISTS idx_access_log_timestamp ON access_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_access_log_gate      ON access_log(gate_id);
CREATE INDEX IF NOT EXISTS idx_access_log_zone      ON access_log(zone_id);
CREATE INDEX IF NOT EXISTS idx_access_log_project   ON access_log(project_code);
CREATE INDEX IF NOT EXISTS idx_pva_project          ON project_vehicle_assignments(project_code);
CREATE INDEX IF NOT EXISTS idx_pva_plate            ON project_vehicle_assignments(plate_number);
CREATE INDEX IF NOT EXISTS idx_va_user              ON vehicle_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_va_plate             ON vehicle_assignments(plate_number);
CREATE INDEX IF NOT EXISTS idx_admin_audit_user     ON admin_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_admin_audit_entity   ON admin_audit_log(entity_type, entity_id);
```

### Migrations dict

`database.py` exposes `_MIGRATIONS: dict[int, str]`. Include migrations adding `zone_id` and `project_code` to `access_log`, `employee_no` to `users`, and `plate_crop_b64` to `gate_rejections`. `init_db(conn)` applies the latest schema; `migrate_db(conn)` applies any missing migrations idempotently by catching `sqlite3.OperationalError` messages containing `"duplicate column name"`, `"no such column"`, or `"no such table"` and silently continuing.

### Seeding (`scripts/seed_db.py`)

Must produce a runnable demo. **Build in `/tmp` then `shutil.copy2` to target** (WAL overlayfs rule above).

- 3 users: `admin`, `manager`, `operator` (bcrypt cost 12, password `testpass` for dev).
- 3 shifts: `DAY` 07:00–15:00, `EVENING` 15:00–23:00, `NIGHT` 23:00–07:00. All weekdays. `permitted_gates: ["MAIN_GATE","WORKSHOP_GATE"]`. `grace_period_minutes = 15`.
- 5 zones: `DRYDOCK_1` (DRYDOCK, 30), `DRYDOCK_2` (DRYDOCK, 30), `BERTH_NORTH` (BERTH, 20), `WORKSHOP_ENG` (WORKSHOP, 40), `ADMIN_BLOCK` (ADMIN, 60).
- 3 companies: `SCO-001 Ceylon Marine Services`, `SCO-002 Lanka Welding (Pvt) Ltd`, `SCO-003 Onomichi Tech Support`.
- 2 active projects: `PRJ-2026-001` (vessel "MV Sayuri", DRYDOCK_1), `PRJ-2026-002` (vessel "MV Lanka Pride", DRYDOCK_2).
- 12 demo vehicles: `WP-CAB-1234`, `WP-KA-5678`, `KL-9012`, `CAB-3456`, `WP-GA-7890`, `CP-1122`, `WP-AB-3344`, `KL-5566`, `WP-CD-7788`, `NW-9900`, `SG-1111`, `WP-EF-2233`.
- Assign vehicles to shifts and projects. Assign a few vehicles to the `operator` user via `vehicle_assignments`.

---

## §6. Component specifications

### 6.1 `src/config.py`

Single module of typed constants. `CONFUSION_PAIRS` must be `frozenset` of `frozenset` — membership test must be `frozenset({a, b}) in CONFUSION_PAIRS`.

```python
PROJECT_ROOT      = Path(__file__).resolve().parent.parent
MODELS_DIR        = PROJECT_ROOT / 'models'
PLATE_DETECTOR    = MODELS_DIR / 'plate_detector.pt'
CHAR_CLASSIFIER   = MODELS_DIR / 'char_classifier.pt'
DB_PATH           = Path(os.environ.get('VAAS_DB_PATH', str(PROJECT_ROOT / 'data' / 'vaas.db')))
PLATE_CONF_THRESHOLD = 0.70
CHAR_CONF_THRESHOLD  = 0.65
CLAHE_CLIP_LIMIT = 3.0
CLAHE_TILE_SIZE  = (8, 8)
CONFUSION_PAIRS = frozenset({
    frozenset({'8','B'}), frozenset({'0','O'}),
    frozenset({'1','I'}), frozenset({'5','S'})
})
CONFUSION_COST  = 0.1
FULL_COST       = 1.0
LPM_THRESHOLD   = 0.5
GENESIS_PREV_HASH = '0' * 64
EXCEPTION_TIMEOUT_SECONDS = 30
OVERSTAY_THRESHOLD_MINUTES = 120
HARDWARE_MODE = os.environ.get('VAAS_HW_MODE', 'MOCK')
ARDUINO_PORT  = os.environ.get('VAAS_ARDUINO_PORT', '/dev/ttyUSB0')
ARDUINO_BAUD  = 9600
CAMERA_INDEX  = int(os.environ.get('VAAS_CAMERA_INDEX', '0'))
SAMPLE_IMAGE_DIR = PROJECT_ROOT / 'data' / 'sample_plates'
PLATE_CROP_RETENTION_DAYS = 90
SESSION_TIMEOUT_HOURS = 8
BCRYPT_COST = 12
CDL_FUN_BLUE   = '#1B3F95'
CDL_YELLOW     = '#f4bd0f'
CDL_SAFETY_GRN = '#76bd33'
```

### 6.2 `src/clahe.py`

BGR → LAB, CLAHE on L channel only, LAB → BGR. A/B channels pass through unchanged.

**Key test note:** the BGR→LAB→BGR round-trip introduces up to 7 units of uint8 quantisation error in A and B channels. The test asserting A/B preservation must use tolerance `<= 10`, **not** `<= 1`.

### 6.3 `src/lpm_mled.py`

Standard weighted Levenshtein with confusion-pair substitution costs. See §2 for exact parameters. Best-score initialised to `threshold` (strict `<` — a score equal to threshold is rejected).

### 6.4 `src/detection.py` and `src/classifier.py`

`from ultralytics import YOLO` at module level, **no try/except guard**. Failing at import in CI is the intended behaviour. Do not add skip markers.

### 6.5 `src/attendance.py`

Define a monkeypatchable time hook at module level:

```python
def _now() -> datetime:
    return datetime.now(timezone.utc)
```

Tests patch `src.attendance._now` via `monkeypatch.setattr()`. Never call `datetime.now()` directly inside the engine — always call `_now()`.

**Suspended / Expired vehicles:** write to `gate_rejections` only — **no `access_log` row**. Return `GateEventResult` with `access_log_id=None`.

**Visitor (unregistered):** write to `access_log` with `status='VISITOR'`, finalise hash. Return `GateEventResult` with `access_log_id` set.

**Midnight boundary implementation:** if `start_h*60+start_m >= end_h*60+end_m` (overnight), compute `start_dt` and `end_dt` anchored on the event's date. If `event_time < start_dt`, subtract `timedelta(days=1)` from both. This correctly attributes a 00:01 event to the prior night's window.

**28 tests.** All 13 statuses covered. Midnight boundary at 23:59 and 00:01. Overstay race idempotency.

### 6.6 `src/audit.py`

```python
@dataclass
class ChainVerificationResult:
    ok: bool                  # True = chain intact
    first_bad_id: int | None  # row id of first mismatch
    reason: str | None        # human description
    verified_at: str          # ISO-8601 UTC timestamp
    rows_checked: int         # total rows walked
```

**There is no `.status` field.** Every call-site uses `.ok`. The `run_demo.py` script and manager blueprint route must check `result.ok`, display `result.rows_checked`, and show `result.first_bad_id` if `not result.ok`.

Two-step pattern: INSERT (PENDING) → get `lastrowid` → compute hash with PK in payload → UPDATE. Both steps inside the same `transaction()` context.

**20 tests.** Include: 1000-row chain, PK-in-payload row-reordering test, deletion gap test, single-row genesis hash test.

### 6.7 `src/barrier.py`

`command_log()` returns `list[tuple[str, str]]` — each entry is `(gate_id, action)`. Access with `c[0]` and `c[1]`. **Not dicts.**

**6 tests** — mock log assertions; live writes correct bytes; idempotent close; bad gate_id raises; port-unavailable LIVE raises with diagnostic; mode flip works.

### 6.8 `src/projects.py` — CDL Specialisation Layer

17 public functions (see §2 for full list). Confirm with `inspect.getmembers` after implementing.

### 6.9 `src/analytics.py` — 10 reports + 3 helpers

10 report functions + `csv_string`, `export_csv`, `export_pdf`. `ohs_compliance_report` uses LEFT JOIN. `export_pdf` uses ReportLab with CDL Fun Blue header bar.

**45 tests**: 8 + 6 + 4 + 4 + 3 + 3 + 3 + 4 + 3 + 4 + 3 = 45.

### 6.10 `src/camera.py`

`MockCamera(folder)` cycles through images, 200 ms sleep. `USBCamera(index)` wraps `cv2.VideoCapture`. Both expose `read() -> np.ndarray | None` and `release()`.

### 6.11 `src/pipeline.py`

```python
def run_pipeline(
    camera, detector, classifier, attendance_engine,
    gate_id: str, direction: Literal['ENTRY','EXIT'],
    stop_event: threading.Event | None = None,
    frame_callback: Callable | None = None,
) -> None
```

For each frame: call `frame_callback` first, then detector → CLAHE → classifier → `attendance_engine.process_gate_event(raw_plate=..., confidence=..., gate_id=..., direction=..., plate_crop_jpeg_bytes=b"")`. The **engine handles LPM-MLED internally** — do not run it in the pipeline. Always call `camera.release()` on exit.

---

## §7. Web application

### 7.1 Application factory

`webapp/__init__.py`: `create_app(config_overrides=None) -> Flask`

`scripts/serve.py`: `from waitress import serve; serve(create_app(), host='0.0.0.0', port=5000, threads=8)`

### 7.2 Auth (`webapp/auth.py`)

`ROLE_RANK = {'OPERATOR': 1, 'MANAGER': 2, 'ADMIN': 3}`. `requires_role(min_role)` decorator checks `ROLE_RANK[session['role']] >= ROLE_RANK[min_role]`. bcrypt cost 12. Session 8 hours. CSRF on every POST.

### 7.3 Operator blueprint

Dashboard, MJPEG (`/operator/mjpeg/<gate_id>`), SSE (`/operator/sse`), exception dispose (`POST /operator/exception/<id>/dispose`).

### 7.4 Manager blueprint

All ten report routes with `?format=html|csv|pdf`. Audit verify route at `/manager/audit/verify` — use `result.ok` / `result.first_bad_id` / `result.rows_checked`, **not** `result.status`.

### 7.5 Admin blueprint

CRUD for vehicles, shifts, zones, companies, projects, users. Every mutating action writes to `admin_audit_log`.

### 7.6 Templates

Bootstrap 5 CDN. CDL Fun Blue navbar. High-contrast operator indicators.

---

## §8. Testing — 156 tests, exact distribution

`pytest.ini`:
```ini
[pytest]
testpaths = tests
addopts   = -v --tb=short --cov=src --cov=webapp --strict-markers
             --ignore=tests/test_classifier.py --ignore=tests/test_detection.py
markers   =
    integration: end-to-end tests (no YOLO)
```

**Explicitly ignore the two YOLO test files** in `addopts` so they never appear in the collected count.

| File                    | Tests | Notes |
| ----------------------- | ----: | ----- |
| `test_clahe.py`         | 8     |       |
| `test_lpm_mled.py`      | 22    |       |
| `test_attendance.py`    | 28    | Midnight-boundary, race-condition idempotency |
| `test_audit.py`         | 20    | Row-reordering attack (PK-in-payload) |
| `test_projects.py`      | 15    | CDL Specialisation Layer |
| `test_analytics.py`     | 45    | All 10 reports + helpers |
| `test_barrier.py`       | 6     |       |
| `test_integration.py`   | 12    | Mock detector/classifier, no YOLO |
| **Total (non-YOLO)**    | **156** | All pass |
| `test_classifier.py`    | (15)  | Fails at import in CI — excluded |
| `test_detection.py`     | —     | Excluded |

### conftest.py — key fixtures

```python
@pytest.fixture
def db():
    # In-memory SQLite — avoids WAL overlayfs issues entirely
    conn = sqlite3.connect(':memory:')
    conn.isolation_level = None
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    from src.database import migrate_db
    migrate_db(conn)
    yield conn
    conn.close()

@pytest.fixture
def frozen_time(monkeypatch):
    # Returns object with .set(dt) method — NOT directly callable
    import src.attendance as att_mod
    class _FrozenDatetime:
        def set(self, dt):
            monkeypatch.setattr(att_mod, '_now', lambda: dt)
    return _FrozenDatetime()
```

**`frozen_time` is NOT callable.** Usage: `frozen_time.set(datetime(2026, 1, 5, 7, 10, tzinfo=timezone.utc))`.

**Integration tests** patch time directly: `monkeypatch.setattr(src.attendance, '_now', lambda: dt)`.

**Seeded DB gate names:** DAY/EVENING/NIGHT shifts have `permitted_gates = ["MAIN_GATE","WORKSHOP_GATE"]`. Integration tests must use `gate_id="MAIN_GATE"`, not `"GATE-A"` — using an unpermitted gate produces NO_SHIFT status.

**Midnight-boundary test vehicle:** assign it **only** to the NIGHT shift. If a vehicle is in both DAY and NIGHT, the engine may return DAY (LIMIT 1 ordering) and the midnight test will fail.

---

## §9. Build sequence — 10 phases

After every phase: run `pytest`, ensure relevant tests pass, report progress, stop for confirmation.

**Phase 0 — Scaffold.** Directory tree, both requirements files, `pytest.ini`, `.env.example`, stub README. Install deps.
**Phase 1 — Database.** `src/config.py`, `src/database.py`, `scripts/seed_db.py` (WAL /tmp pattern).
**Phase 2 — Audit chain.** `src/audit.py`. `tests/test_audit.py` (20) → all pass.
**Phase 3 — LPM-MLED.** `src/lpm_mled.py`. `tests/test_lpm_mled.py` (22) → all pass.
**Phase 4 — CLAHE & CV stubs.** `src/clahe.py`, `src/detection.py`, `src/classifier.py`. `tests/test_clahe.py` (8) → all pass.
**Phase 5 — Attendance engine.** `src/attendance.py`, `src/barrier.py`. `tests/test_attendance.py` (28), `tests/test_barrier.py` (6) → all pass.
**Phase 6 — CDL Specialisation Layer.** `src/projects.py` (17 functions). `tests/test_projects.py` (15) → all pass.
**Phase 7 — Analytics.** `src/analytics.py` (10 reports). `tests/test_analytics.py` (45) → all pass.
**Phase 8 — Pipeline & integration.** `src/camera.py`, `src/pipeline.py`, `scripts/run_demo.py`. `tests/test_integration.py` (12) → all pass. **Full pytest: 156 passed.**
**Phase 9 — Web app.** Auth, blueprints, templates, MJPEG, SSE, Waitress. `scripts/serve.py`.

---

## §10. Acceptance criteria

- [ ] `pytest` reports **156 passed** (YOLO files excluded via `--ignore` in `pytest.ini`).
- [ ] `python scripts/seed_db.py` runs without errors.
- [ ] `python scripts/run_demo.py` produces `access_log` rows with non-PENDING `row_hash`.
- [ ] `python scripts/verify_chain.py` reports `ok=True`; one modified row → `ok=False` at `first_bad_id`; swapping two rows' field values also → `ok=False` (PK-in-payload defence).
- [ ] `python scripts/serve.py` starts on `:5000`. Each role logs in. MANAGER exports CSV and PDF with CDL Fun Blue header. ADMIN registers vehicle, assigns to project, closes project (soft-removes).
- [ ] `inspect.getmembers(src.projects, inspect.isfunction)` filtered to public → **17** functions.
- [ ] `src.analytics` exposes **10** report functions + `csv_string`, `export_csv`, `export_pdf`.
- [ ] `src.attendance` produces all 13 status values across the test suite.
- [ ] LPM-MLED: `WP-CA8-1234` → `WP-CAB-1234`. `WP-CAZ-1234` → `None`.
- [ ] No hardcoded secrets. No literal `15` for grace period in `attendance.py`.

---

## §11. Things to flag back, not invent

- `.pt` files don't load → ask before guessing.
- Python 3.13 unavailable → flag explicitly.
- Test would require changing a graded figure → surface and ask.
- 17 / 10 function counts are exact → ask before merging or splitting.
- Hardware unavailable during build → MOCK mode only.

---

## §12. Style and quality bar

- `from __future__ import annotations` at the top of every module.
- Type hints everywhere. `dataclasses` for structured returns.
- `logger = logging.getLogger(__name__)` — never `print` in `src/` or `webapp/`.
- UTC timestamps, ISO-8601. `datetime.now(timezone.utc)` always.
- All SQL parameterised. `transaction(conn)` context manager for multi-statement writes.

---

## §13. Implementation notes — hard-won lessons

**Read this section before writing any code.**

### File writes
Never use an Edit tool for files > 150 lines — it silently truncates. Write all source files via `open(path, 'w')` in Python or heredoc bash. For files > 300 lines, write a self-contained Python script that builds the content and writes it via `open()`.

### WAL on overlayfs
Covered in §5. Summary: build permanent DBs in `/tmp`, copy out. Test fixtures always use `:memory:`. `connect()` has WAL→MEMORY fallback. Never mix PRAGMAs with DDL in the same `executescript()` call.

### ChainVerificationResult — `.ok`, not `.status`
The dataclass has no `.status` field. Every check is `result.ok`. Every display is `result.rows_checked` and `result.first_bad_id`. This affects `run_demo.py`, `verify_chain.py`, and the manager blueprint `/audit/verify` route.

### BarrierController.command_log() — tuples, not dicts
`command_log()` returns `list[tuple[str, str]]` — `(gate_id, action)`. Use `c[1] == 'OPEN'`, not `c['action'] == 'OPEN'`.

### Suspended/Expired → gate_rejections only
SUSPENDED and EXPIRED vehicles are written to `gate_rejections`, not `access_log`. Tests checking rejection must query `gate_rejections WHERE plate_number = ?` and check `reason` equals `'SUSPENDED'` or `'EXPIRED'`.

### frozen_time fixture API
`frozen_time.set(datetime(..., tzinfo=timezone.utc))` — not `frozen_time('08:00')`. In integration tests without the fixture, use `monkeypatch.setattr(src.attendance, '_now', lambda: dt)` directly.

### Seeded gate names
`permitted_gates = ["MAIN_GATE","WORKSHOP_GATE"]` for all seeded shifts. Integration tests must use `gate_id="MAIN_GATE"`.

### CLAHE A/B tolerance
Assert A/B channel preservation with tolerance `<= 10` (not `<= 1`). The uint8 LAB round-trip introduces up to 7 units quantisation error.

### Midnight boundary test isolation
The test vehicle for midnight-boundary tests must be assigned **only** to the NIGHT shift. Multi-shift vehicles cause `LIMIT 1` to return the wrong shift and fail the midnight test.