"""SQLite WAL database layer (Appendix B schema).

CDL-specific extensions (s6.4):
  - cdl_zones                  : physical zones (drydocks, berths, workshops)
  - projects                   : active vessel/drydock projects
  - project_vehicle_assignments: vehicles linked to projects
  - subcontractor_companies    : approved sub-contracting firms
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.config import DB_PATH

VEHICLE_CATEGORIES = ("STAFF", "CONTRACTOR", "MANAGEMENT", "FLEET",
                      "VISITOR", "EMERGENCY", "MAINTENANCE")
VEHICLE_TYPES      = ("CAR", "VAN", "TRUCK", "MOTORCYCLE", "UTILITY")

CDL_ZONES = (
    "DRYDOCK_1", "DRYDOCK_2", "DRYDOCK_3", "DRYDOCK_4",
    "BERTH_NORTH", "BERTH_SOUTH",
    "WORKSHOP_ENGINEERING", "WORKSHOP_ELECTRICAL",
    "ADMIN_BLOCK", "SECURITY_CHECKPOINT",
)
CDL_PROJECT_STATUSES = ("ACTIVE", "COMPLETED", "SUSPENDED", "PLANNED")
CDL_ASSIGNMENT_ROLES = ("EMPLOYEE", "SUBCONTRACTOR", "SUPERVISOR", "VISITOR")

SCHEMA = (
    "PRAGMA journal_mode = WAL;"
    "PRAGMA synchronous  = NORMAL;"
    "PRAGMA foreign_keys = ON;"
    "CREATE TABLE IF NOT EXISTS registered_vehicles ("
    "    plate_number        TEXT PRIMARY KEY,"
    "    vehicle_category    TEXT NOT NULL DEFAULT 'CONTRACTOR',"
    "    vehicle_type        TEXT NOT NULL DEFAULT 'CAR',"
    "    contractor_name     TEXT,"
    "    department          TEXT,"
    "    make_model          TEXT,"
    "    company_id          TEXT,"
    "    registration_status TEXT NOT NULL DEFAULT 'ACTIVE'"
    "                        CHECK(registration_status IN ('ACTIVE','SUSPENDED','EXPIRED')),"
    "    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),"
    "    notes               TEXT"
    ");"
    "CREATE TABLE IF NOT EXISTS shifts ("
    "    shift_id             TEXT PRIMARY KEY,"
    "    shift_name           TEXT NOT NULL,"
    "    start_time           TEXT NOT NULL,"
    "    end_time             TEXT NOT NULL,"
    "    days_of_week         TEXT NOT NULL,"
    "    permitted_gates      TEXT NOT NULL,"
    "    grace_period_minutes INTEGER NOT NULL DEFAULT 10"
    ");"
    "CREATE TABLE IF NOT EXISTS vehicle_shifts ("
    "    plate_number TEXT NOT NULL REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,"
    "    shift_id     TEXT NOT NULL REFERENCES shifts(shift_id) ON DELETE CASCADE,"
    "    PRIMARY KEY (plate_number, shift_id)"
    ");"
    "CREATE TABLE IF NOT EXISTS vehicle_assignments ("
    "    id           INTEGER PRIMARY KEY AUTOINCREMENT,"
    "    plate_number TEXT NOT NULL REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,"
    "    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
    "    assigned_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),"
    "    is_active    INTEGER NOT NULL DEFAULT 1,"
    "    notes        TEXT"
    ");"
    "CREATE TABLE IF NOT EXISTS access_log ("
    "    id                 INTEGER PRIMARY KEY AUTOINCREMENT,"
    "    plate_number       TEXT    NOT NULL,"
    "    timestamp          TEXT    NOT NULL,"
    "    gate_id            TEXT    NOT NULL,"
    "    direction          TEXT    NOT NULL CHECK(direction IN ('ENTRY','EXIT')),"
    "    dwell_time_seconds REAL,"
    "    shift_id           TEXT,"
    "    confidence_score   REAL,"
    "    status             TEXT    NOT NULL DEFAULT 'UNKNOWN',"
    "    row_hash           TEXT    NOT NULL,"
    "    plate_crop_b64     TEXT,"
    "    zone_id            TEXT,"
    "    project_code       TEXT"
    ");"
    "CREATE TABLE IF NOT EXISTS users ("
    "    id            INTEGER PRIMARY KEY AUTOINCREMENT,"
    "    username      TEXT    NOT NULL UNIQUE,"
    "    full_name     TEXT,"
    "    password_hash TEXT    NOT NULL,"
    "    role          TEXT    NOT NULL DEFAULT 'OPERATOR'"
    "                  CHECK(role IN ('ADMIN','MANAGER','OPERATOR')),"
    "    last_login    TEXT"
    ");"
    "CREATE TABLE IF NOT EXISTS gate_rejections ("
    "    id               INTEGER PRIMARY KEY AUTOINCREMENT,"
    "    plate_number     TEXT,"
    "    timestamp        TEXT NOT NULL,"
    "    gate_id          TEXT NOT NULL,"
    "    reason           TEXT NOT NULL,"
    "    confidence_score REAL"
    ");"
    "CREATE TABLE IF NOT EXISTS admin_audit_log ("
    "    id          INTEGER PRIMARY KEY AUTOINCREMENT,"
    "    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),"
    "    user_id     INTEGER,"
    "    username    TEXT,"
    "    action      TEXT NOT NULL,"
    "    entity_type TEXT NOT NULL,"
    "    entity_id   TEXT NOT NULL,"
    "    details     TEXT"
    ");"
    "CREATE TABLE IF NOT EXISTS cdl_zones ("
    "    zone_id           TEXT PRIMARY KEY,"
    "    zone_name         TEXT NOT NULL,"
    "    zone_type         TEXT NOT NULL CHECK(zone_type IN ('DRYDOCK','BERTH','WORKSHOP','ADMIN','SECURITY')),"
    "    gate_ids          TEXT NOT NULL,"
    "    capacity_vehicles INTEGER NOT NULL DEFAULT 50,"
    "    description       TEXT"
    ");"
    "CREATE TABLE IF NOT EXISTS subcontractor_companies ("
    "    company_id    TEXT PRIMARY KEY,"
    "    company_name  TEXT NOT NULL,"
    "    contact_name  TEXT,"
    "    contact_phone TEXT,"
    "    approved_until TEXT,"
    "    status        TEXT NOT NULL DEFAULT 'APPROVED'"
    "                  CHECK(status IN ('APPROVED','SUSPENDED','EXPIRED'))"
    ");"
    "CREATE TABLE IF NOT EXISTS projects ("
    "    project_code    TEXT PRIMARY KEY,"
    "    project_name    TEXT NOT NULL,"
    "    vessel_name     TEXT,"
    "    zone_id         TEXT NOT NULL REFERENCES cdl_zones(zone_id),"
    "    start_date      TEXT NOT NULL,"
    "    end_date        TEXT,"
    "    status          TEXT NOT NULL DEFAULT 'ACTIVE'"
    "                    CHECK(status IN ('ACTIVE','COMPLETED','SUSPENDED','PLANNED')),"
    "    project_manager TEXT,"
    "    notes           TEXT"
    ");"
    "CREATE TABLE IF NOT EXISTS project_vehicle_assignments ("
    "    id           INTEGER PRIMARY KEY AUTOINCREMENT,"
    "    project_code TEXT NOT NULL REFERENCES projects(project_code) ON DELETE CASCADE,"
    "    plate_number TEXT NOT NULL REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,"
    "    role         TEXT NOT NULL DEFAULT 'EMPLOYEE'"
    "                 CHECK(role IN ('EMPLOYEE','SUBCONTRACTOR','SUPERVISOR','VISITOR')),"
    "    company_id   TEXT REFERENCES subcontractor_companies(company_id),"
    "    assigned_by  INTEGER REFERENCES users(id),"
    "    assigned_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),"
    "    removed_at   TEXT,"
    "    notes        TEXT"
    ");"
    "CREATE INDEX IF NOT EXISTS idx_access_log_plate     ON access_log(plate_number);"
    "CREATE INDEX IF NOT EXISTS idx_access_log_timestamp ON access_log(timestamp);"
    "CREATE INDEX IF NOT EXISTS idx_access_log_gate      ON access_log(gate_id);"
    "CREATE INDEX IF NOT EXISTS idx_va_plate             ON vehicle_assignments(plate_number);"
    "CREATE INDEX IF NOT EXISTS idx_va_user              ON vehicle_assignments(user_id);"
    "CREATE INDEX IF NOT EXISTS idx_va_active            ON vehicle_assignments(is_active);"
    "CREATE INDEX IF NOT EXISTS idx_aal_occurred         ON admin_audit_log(occurred_at);"
    "CREATE INDEX IF NOT EXISTS idx_pva_project          ON project_vehicle_assignments(project_code);"
    "CREATE INDEX IF NOT EXISTS idx_pva_plate            ON project_vehicle_assignments(plate_number);"
    "CREATE INDEX IF NOT EXISTS idx_proj_zone            ON projects(zone_id);"
    "CREATE INDEX IF NOT EXISTS idx_proj_status          ON projects(status);"
)

_MIGRATIONS = [
    "ALTER TABLE registered_vehicles ADD COLUMN vehicle_type TEXT NOT NULL DEFAULT 'CAR'",
    "ALTER TABLE registered_vehicles ADD COLUMN department TEXT",
    "ALTER TABLE registered_vehicles ADD COLUMN make_model TEXT",
    "ALTER TABLE users ADD COLUMN full_name TEXT",
    "ALTER TABLE registered_vehicles ADD COLUMN company_id TEXT",
    "ALTER TABLE access_log ADD COLUMN zone_id TEXT",
    "ALTER TABLE access_log ADD COLUMN project_code TEXT",
]


def connect(db_path=None):
    path = str(db_path) if db_path else str(DB_PATH)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    """Create all tables from scratch."""
    conn.executescript(SCHEMA)


def migrate_schema(conn):
    """Apply incremental migrations idempotently."""
    conn.executescript(SCHEMA)
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                pass
            else:
                raise


@contextmanager
def transaction(conn):
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
