"""SQLite WAL database layer (Appendix B schema)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.config import DB_PATH

# ---------------------------------------------------------------------------
# Vehicle categories and types — used in forms and analytics
# ---------------------------------------------------------------------------
VEHICLE_CATEGORIES = ("STAFF", "CONTRACTOR", "MANAGEMENT", "FLEET",
                      "VISITOR", "EMERGENCY", "MAINTENANCE")
VEHICLE_TYPES      = ("CAR", "VAN", "TRUCK", "MOTORCYCLE", "UTILITY")

# ---------------------------------------------------------------------------
# Initial schema — CREATE IF NOT EXISTS, safe to run on any new database
# ---------------------------------------------------------------------------
SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS registered_vehicles (
    plate_number        TEXT PRIMARY KEY,
    vehicle_category    TEXT NOT NULL DEFAULT 'CONTRACTOR',
    vehicle_type        TEXT NOT NULL DEFAULT 'CAR',
    contractor_name     TEXT,
    department          TEXT,
    make_model          TEXT,
    registration_status TEXT NOT NULL DEFAULT 'ACTIVE'
                        CHECK(registration_status IN ('ACTIVE','SUSPENDED','EXPIRED')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS shifts (
    shift_id             TEXT PRIMARY KEY,
    shift_name           TEXT NOT NULL,
    start_time           TEXT NOT NULL,
    end_time             TEXT NOT NULL,
    days_of_week         TEXT NOT NULL,
    permitted_gates      TEXT NOT NULL,
    grace_period_minutes INTEGER NOT NULL DEFAULT 10
);

CREATE TABLE IF NOT EXISTS vehicle_shifts (
    plate_number TEXT NOT NULL REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,
    shift_id     TEXT NOT NULL REFERENCES shifts(shift_id) ON DELETE CASCADE,
    PRIMARY KEY (plate_number, shift_id)
);

-- Driver / user → vehicle assignments (many-to-many with history)
CREATE TABLE IF NOT EXISTS vehicle_assignments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT NOT NULL REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    is_active    INTEGER NOT NULL DEFAULT 1,
    notes        TEXT
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
    row_hash           TEXT    NOT NULL,
    plate_crop_b64     TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    full_name     TEXT,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'OPERATOR'
                  CHECK(role IN ('ADMIN','MANAGER','OPERATOR')),
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS gate_rejections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number     TEXT,
    timestamp        TEXT NOT NULL,
    gate_id          TEXT NOT NULL,
    reason           TEXT NOT NULL,
    confidence_score REAL
);

-- Admin action log — tamper-evident trail of every CRUD operation
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    user_id     INTEGER,
    username    TEXT,
    action      TEXT NOT NULL,      -- CREATE | UPDATE | DELETE | ASSIGN | UNASSIGN
    entity_type TEXT NOT NULL,      -- VEHICLE | SHIFT | USER | ASSIGNMENT
    entity_id   TEXT NOT NULL,
    details     TEXT                -- JSON summary of changed values
);

CREATE INDEX IF NOT EXISTS idx_access_log_plate     ON access_log(plate_number);
CREATE INDEX IF NOT EXISTS idx_access_log_timestamp ON access_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_access_log_gate      ON access_log(gate_id);
CREATE INDEX IF NOT EXISTS idx_va_plate             ON vehicle_assignments(plate_number);
CREATE INDEX IF NOT EXISTS idx_va_user              ON vehicle_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_va_active            ON vehicle_assignments(is_active);
CREATE INDEX IF NOT EXISTS idx_aal_occurred         ON admin_audit_log(occurred_at);
"""

# ---------------------------------------------------------------------------
# Incremental migrations — safe to run on existing databases
# ADD COLUMN is idempotent (error = column already exists → ignored)
# ---------------------------------------------------------------------------
_MIGRATIONS = [
    "ALTER TABLE registered_vehicles ADD COLUMN vehicle_type TEXT NOT NULL DEFAULT 'CAR'",
    "ALTER TABLE registered_vehicles ADD COLUMN department TEXT",
    "ALTER TABLE registered_vehicles ADD COLUMN make_model TEXT",
    "ALTER TABLE users ADD COLUMN full_name TEXT",
]


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = str(db_path) if db_path else str(DB_PATH)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables from scratch.  Safe on an empty or partially-built DB."""
    conn.executescript(SCHEMA)


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply incremental column additions to an *existing* database.

    Each ALTER TABLE is attempted individually; the OperationalError raised
    when a column already exists is silently swallowed so the function is
    idempotent.
    """
    # First ensure new tables exist
    conn.executescript(SCHEMA)
    # Then add any new columns to existing tables
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass   # column already present


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Cursor]:
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        yield cur
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    finally:
        cur.close()
