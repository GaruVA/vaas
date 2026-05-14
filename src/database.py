from __future__ import annotations

"""SQLite WAL database layer -- 12-table VAAS schema.

Tables
------
Core (8): registered_vehicles, shifts, vehicle_shifts, vehicle_assignments,
          access_log, users, gate_rejections, admin_audit_log
CDL  (4): cdl_zones, subcontractor_companies, projects, project_vehicle_assignments

References: section 5 of BUILD_SPEC.md
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from src.config import DB_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL -- separated from PRAGMA so executescript does not conflict
# with an already-open WAL connection.
# ---------------------------------------------------------------------------

_DDL_SQL = """
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
    shift_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_name           TEXT NOT NULL,
    start_time           TEXT NOT NULL,
    end_time             TEXT NOT NULL,
    days_of_week         TEXT NOT NULL,
    permitted_gates      TEXT NOT NULL,
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
    zone_id            TEXT,
    project_code       TEXT,
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
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    user_id     INTEGER REFERENCES users(id),
    username    TEXT    NOT NULL,
    action      TEXT    NOT NULL CHECK(action IN ('CREATE','UPDATE','DELETE','ASSIGN')),
    entity_type TEXT    NOT NULL,
    entity_id   TEXT,
    delta_json  TEXT
);

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
"""

# ---------------------------------------------------------------------------
# Constants extracted from schema CHECK constraints
# ---------------------------------------------------------------------------

VEHICLE_CATEGORIES = ("STAFF", "CONTRACTOR", "MANAGEMENT", "FLEET", "VISITOR", "EMERGENCY", "MAINTENANCE")
VEHICLE_TYPES = ("CAR", "VAN", "TRUCK", "MOTORCYCLE", "UTILITY")
VEHICLE_STATUSES = ("ACTIVE", "SUSPENDED", "EXPIRED")
DIRECTIONS = ("ENTRY", "EXIT")
USER_ROLES = ("ADMIN", "MANAGER", "OPERATOR")
ZONE_TYPES = ("DRYDOCK", "BERTH", "WORKSHOP", "ADMIN", "SECURITY")
PROJECT_STATUSES = ("ACTIVE", "CLOSED")
COMPANY_STATUSES = ("APPROVED", "SUSPENDED", "EXPIRED")
ASSIGNMENT_ROLES = ("EMPLOYEE", "SUBCONTRACTOR", "SUPERVISOR", "VISITOR")
ADMIN_ACTIONS = ("CREATE", "UPDATE", "DELETE", "ASSIGN")

# ---------------------------------------------------------------------------
# Migrations -- keyed by int, applied idempotently.
# Keys are sequential; append at the end for future additions.
# ---------------------------------------------------------------------------

_MIGRATIONS: dict[int, str] = {
    # Add CDL columns to access_log for pre-CDL databases
    1: "ALTER TABLE access_log ADD COLUMN zone_id TEXT",
    2: "ALTER TABLE access_log ADD COLUMN project_code TEXT",
    # Add employee_no to users for older schemas
    3: "ALTER TABLE users ADD COLUMN employee_no TEXT",
    # Add plate_crop_b64 to gate_rejections for older schemas
    4: "ALTER TABLE gate_rejections ADD COLUMN plate_crop_b64 TEXT",
}


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection, preferring WAL journal mode.

    Falls back to MEMORY journal mode on file-systems that do not support
    WAL's shared-memory sidecar files (e.g. certain overlay mounts used in
    development containers).  In-memory databases (``":memory:"``) are
    unaffected.

    Parameters
    ----------
    db_path:
        Filesystem path or ``':memory:'`` for an in-memory database.
        Defaults to ``DB_PATH`` from config.
    """
    path = str(db_path) if db_path is not None else str(DB_PATH)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.isolation_level = None   # autocommit
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        # FS does not support WAL shm files -- use in-process journal
        conn.execute("PRAGMA journal_mode = MEMORY")
        logger.warning("WAL journal unavailable; using MEMORY journal mode")
    conn.execute("PRAGMA synchronous  = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    """Apply the base schema from scratch.  Safe on a fresh database."""
    conn.executescript(_DDL_SQL)
    logger.debug("VAAS schema initialised")


def migrate_db(conn: sqlite3.Connection) -> None:
    """Apply base schema then run incremental migrations idempotently.

    Each migration in ``_MIGRATIONS`` is attempted in key order.
    ``sqlite3.OperationalError`` is silently swallowed when the message
    contains any of:

    - ``"duplicate column name"`` -- column already exists (fresh DB)
    - ``"no such column"``        -- rename of non-existent column
    - ``"no such table"``         -- table not yet created

    This makes the function safe on both fresh databases (base DDL already
    names columns correctly) and legacy databases (ALTER TABLE is needed).
    """
    # Ensure base schema is present
    conn.executescript(_DDL_SQL)

    # Apply incremental migrations
    for key in sorted(_MIGRATIONS):
        sql = _MIGRATIONS[key]
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if (
                "duplicate column name" in msg
                or "no such column" in msg
                or "no such table" in msg
            ):
                pass  # idempotent -- already applied or not applicable
            else:
                raise
    logger.debug("VAAS migrations complete")


# ---------------------------------------------------------------------------
# Transaction context manager
# ---------------------------------------------------------------------------

@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Cursor, None, None]:
    """Explicit BEGIN / COMMIT / ROLLBACK context manager.

    Usage::

        with transaction(conn) as cur:
            cur.execute(...)
    """
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
