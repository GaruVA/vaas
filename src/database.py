"""SQLite WAL database layer (Appendix B schema)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.config import DB_PATH

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS registered_vehicles (
    plate_number        TEXT PRIMARY KEY,
    vehicle_category    TEXT NOT NULL DEFAULT 'CONTRACTOR',
    contractor_name     TEXT,
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
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'OPERATOR'
                  CHECK(role IN ('ADMIN','MANAGER','OPERATOR')),
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS gate_rejections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT,
    timestamp    TEXT NOT NULL,
    gate_id      TEXT NOT NULL,
    reason       TEXT NOT NULL,
    confidence_score REAL
);

CREATE INDEX IF NOT EXISTS idx_access_log_plate     ON access_log(plate_number);
CREATE INDEX IF NOT EXISTS idx_access_log_timestamp ON access_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_access_log_gate      ON access_log(gate_id);
"""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = str(db_path) if db_path else str(DB_PATH)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


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
