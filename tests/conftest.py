"""Pytest fixtures: temp DB, sample images, attendance engine."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.attendance import AttendanceEngine
from src.barrier import BarrierController
from src.database import connect, init_schema, transaction


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    p = tmp_path / "test.db"
    conn = connect(p)
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def seeded_db(db: sqlite3.Connection) -> sqlite3.Connection:
    with transaction(db) as cur:
        # CDL operates a continuous three-shift pattern (24/7 shipyard operations).
        # Shift 1: 07:00–15:00 (Day) | Shift 2: 15:00–23:00 (Evening) | Shift 3: 23:00–07:00 (Night)
        # A 15-minute grace period accounts for the Port of Colombo entry queue.
        for sid, sname, sstart, send in [
            ("CDL_SHIFT_1", "Day Shift",     "07:00", "15:00"),
            ("CDL_SHIFT_2", "Evening Shift", "15:00", "23:00"),
            ("CDL_SHIFT_3", "Night Shift",   "23:00", "07:00"),
        ]:
            cur.execute(
                "INSERT INTO shifts VALUES (?,?,?,?,?,?,?)",
                (sid, sname, sstart, send,
                 json.dumps(["MON","TUE","WED","THU","FRI","SAT","SUN"]),
                 json.dumps(["GATE_A","GATE_B","GATE_C","GATE_D"]), 15),
            )
        # Legacy aliases kept so existing tests using "DAY_SHIFT" / "NIGHT_SHIFT" continue to pass
        cur.execute(
            "INSERT INTO shifts VALUES (?,?,?,?,?,?,?)",
            ("DAY_SHIFT", "Day", "08:00", "17:00",
             json.dumps(["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]),
             json.dumps(["GATE_A", "GATE_B"]), 10),
        )
        cur.execute(
            "INSERT INTO shifts VALUES (?,?,?,?,?,?,?)",
            ("NIGHT_SHIFT", "Night", "20:00", "05:00",
             json.dumps(["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]),
             json.dumps(["GATE_A", "GATE_B"]), 10),
        )
        # CDL physical zones — 4 graving drydocks + support zones
        for zid, zname, ztype, gates, cap in [
            ("DRYDOCK_1",   "Graving Drydock No. 1", "DRYDOCK",  ["GATE_A"], 25),
            ("DRYDOCK_2",   "Graving Drydock No. 2", "DRYDOCK",  ["GATE_B"], 25),
            ("DRYDOCK_3",   "Graving Drydock No. 3", "DRYDOCK",  ["GATE_C"], 40),
            ("DRYDOCK_4",   "Graving Drydock No. 4", "DRYDOCK",  ["GATE_D"], 40),
            ("WORKSHOP_ENG","Engineering Workshop",   "WORKSHOP", ["GATE_A","GATE_B"], 20),
            ("ADMIN_BLOCK", "Administration Block",   "ADMIN",    ["GATE_MAIN"], 10),
        ]:
            cur.execute(
                "INSERT INTO cdl_zones (zone_id,zone_name,zone_type,gate_ids,capacity_vehicles) "
                "VALUES (?,?,?,?,?)",
                (zid, zname, ztype, json.dumps(gates), cap),
            )
        # Active vehicles — varied categories and types for enterprise reports
        for plate, cat, vtype, dept in [
            ("CAB-1234",    "STAFF",       "CAR",   "Engineering"),
            ("KL-5678",     "CONTRACTOR",  "VAN",   "Operations"),
            ("WP-CAB-9012", "STAFF",       "CAR",   "Engineering"),
            ("CAR-4521",    "MANAGEMENT",  "CAR",   "Management"),
            ("VAN-8801",    "FLEET",       "VAN",   "Operations"),
        ]:
            cur.execute(
                "INSERT INTO registered_vehicles "
                "(plate_number,vehicle_category,vehicle_type,department,registration_status) "
                "VALUES (?,?,?,?,'ACTIVE')",
                (plate, cat, vtype, dept),
            )
            cur.execute("INSERT INTO vehicle_shifts VALUES (?,?)", (plate, "DAY_SHIFT"))
        cur.execute(
            "INSERT INTO registered_vehicles "
            "(plate_number,vehicle_category,registration_status) VALUES (?,?,'SUSPENDED')",
            ("SUS-0001", "CONTRACTOR"),
        )
        cur.execute(
            "INSERT INTO registered_vehicles "
            "(plate_number,vehicle_category,registration_status) VALUES (?,?,'EXPIRED')",
            ("EXP-0001", "CONTRACTOR"),
        )
        # Users with full names (for payroll)
        import bcrypt as _bcrypt
        for uid, uname, fname, role in [
            (1, "alice", "Alice M. Silva", "OPERATOR"),
            (2, "bob",   "Bob R. Perera",  "OPERATOR"),
        ]:
            cur.execute(
                "INSERT INTO users (id,username,full_name,password_hash,role) VALUES (?,?,?,?,?)",
                (uid, uname, fname,
                 _bcrypt.hashpw(b"test1234", _bcrypt.gensalt()).decode(), role),
            )
        # Assign CAB-1234 and WP-CAB-9012 to alice; KL-5678 to bob
        cur.execute(
            "INSERT INTO vehicle_assignments (plate_number,user_id) VALUES (?,1)",
            ("CAB-1234",),
        )
        cur.execute(
            "INSERT INTO vehicle_assignments (plate_number,user_id) VALUES (?,1)",
            ("WP-CAB-9012",),
        )
        cur.execute(
            "INSERT INTO vehicle_assignments (plate_number,user_id) VALUES (?,2)",
            ("KL-5678",),
        )
    return db


@pytest.fixture
def engine(seeded_db: sqlite3.Connection) -> AttendanceEngine:
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"),
                         exception_timeout_seconds=2)
    yield e
    e.shutdown()


@pytest.fixture
def sample_plate_image() -> np.ndarray:
    img = np.full((60, 200, 3), 240, dtype=np.uint8)
    cv2.putText(img, "CAB-1234", (10, 42),
                cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 0, 0), 2)
    return img


@pytest.fixture
def jpeg_bytes(sample_plate_image) -> bytes:
    ok, buf = cv2.imencode(".jpg", sample_plate_image)
    assert ok
    return buf.tobytes()


def models_present() -> bool:
    from src.config import PLATE_DETECTOR, CHAR_CLASSIFIER
    return PLATE_DETECTOR.exists() and CHAR_CLASSIFIER.exists()


def utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
