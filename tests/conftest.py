from __future__ import annotations

"""Shared pytest fixtures for VAAS test suite."""

import io
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

from src.database import init_db, migrate_db, connect as db_connect

@pytest.fixture
def db():
    """Bare in-memory SQLite connection with VAAS schema applied."""
    conn = db_connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()

@pytest.fixture
def seeded_db(db):
    """In-memory DB seeded with 3 shifts, demo zones, companies, projects,
    registered vehicles, and users."""
    import json
    import bcrypt

    conn = db
    gates = json.dumps(["MAIN_GATE", "WORKSHOP_GATE"])

    pw = bcrypt.hashpw(b"testpass", bcrypt.gensalt(rounds=4)).decode()
    conn.execute(
        "INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
        ("admin", pw, "ADMIN", "Admin User"),
    )
    conn.execute(
        "INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
        ("manager", pw, "MANAGER", "Manager User"),
    )
    conn.execute(
        "INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
        ("operator", pw, "OPERATOR", "Operator User"),
    )

    for sid, name, start, end in [
        ("DAY",     "Day Shift",     "07:00", "15:00"),
        ("EVENING", "Evening Shift", "15:00", "23:00"),
        ("NIGHT",   "Night Shift",   "23:00", "07:00"),
    ]:
        conn.execute(
            """INSERT INTO shifts
               (shift_id, shift_name, start_time, end_time,
                days_of_week, permitted_gates, grace_period_minutes)
               VALUES (?,?,?,?,?,?,?)""",
            (sid, name, start, end,
             json.dumps(["MON","TUE","WED","THU","FRI"]),
             gates, 15),
        )

    import json as _j
    for zid, zname, ztype, cap in [
        ("DRYDOCK_1",    "Dry Dock 1",          "DRYDOCK",  30),
        ("DRYDOCK_2",    "Dry Dock 2",          "DRYDOCK",  30),
        ("BERTH_NORTH",  "Berth North",         "BERTH",    20),
        ("WORKSHOP_ENG", "Engineering Workshop","WORKSHOP", 40),
        ("ADMIN_BLOCK",  "Administration Block","ADMIN",    60),
    ]:
        conn.execute(
            """INSERT INTO cdl_zones
               (zone_id, zone_name, zone_type, associated_gates, vehicle_capacity)
               VALUES (?,?,?,?,?)""",
            (zid, zname, ztype, gates, cap),
        )

    for cid, cname in [
        ("SCO-001", "Ceylon Marine Services"),
        ("SCO-002", "Lanka Welding (Pvt) Ltd"),
        ("SCO-003", "Onomichi Tech Support"),
    ]:
        conn.execute(
            "INSERT INTO subcontractor_companies (company_id, company_name) VALUES (?,?)",
            (cid, cname),
        )

    conn.execute(
        """INSERT INTO projects
           (project_code, vessel_name, zone_id, start_date, status)
           VALUES (?,?,?,?,?)""",
        ("PRJ-2026-001", "MV Sayuri",     "DRYDOCK_1", "2026-01-01", "ACTIVE"),
    )
    conn.execute(
        """INSERT INTO projects
           (project_code, vessel_name, zone_id, start_date, status)
           VALUES (?,?,?,?,?)""",
        ("PRJ-2026-002", "MV Lanka Pride","DRYDOCK_2", "2026-02-01", "ACTIVE"),
    )

    vehicles = [
        ("WP-CAB-1234", "STAFF",       "CAR",        "John Silva",    None,    None),
        ("WP-KA-5678",  "CONTRACTOR",  "VAN",         "ABC Builders",  None,    "SCO-001"),
        ("KL-9012",     "CONTRACTOR",  "TRUCK",       "Lanka Welding", None,    "SCO-002"),
        ("CAB-3456",    "MANAGEMENT",  "CAR",         None,            "MGMT",  None),
        ("WP-GA-7890",  "STAFF",       "MOTORCYCLE",  "Jane Perera",   None,    None),
        ("CP-1122",     "FLEET",       "UTILITY",     None,            "OPS",   None),
        ("WP-AB-3344",  "STAFF",       "CAR",         "Kamal Dias",    None,    None),
        ("KL-5566",     "CONTRACTOR",  "VAN",         "SubCo X",       None,    "SCO-003"),
        ("WP-CD-7788",  "MAINTENANCE", "TRUCK",       None,            "MAINT", None),
        ("NW-9900",     "VISITOR",     "CAR",         "Visitor Corp",  None,    None),
        ("SG-1111",     "EMERGENCY",   "UTILITY",     "Fire Dept",     None,    None),
        ("WP-EF-2233",  "STAFF",       "CAR",         "Rita Raj",      None,    None),
    ]
    for row in vehicles:
        plate, cat, vtype, contractor, dept, company = row
        conn.execute(
            """INSERT INTO registered_vehicles
               (plate_number, vehicle_category, vehicle_type,
                contractor_name, department, company_id)
               VALUES (?,?,?,?,?,?)""",
            (plate, cat, vtype, contractor, dept, company),
        )

    for plate in [v[0] for v in vehicles[:6]]:
        conn.execute(
            "INSERT OR IGNORE INTO vehicle_shifts (plate_number, shift_id) VALUES (?,?)",
            (plate, "DAY"),
        )

    conn.execute(
        """INSERT INTO project_vehicle_assignments
           (project_code, plate_number, role)
           VALUES (?,?,?)""",
        ("PRJ-2026-001", "WP-CAB-1234", "EMPLOYEE"),
    )
    conn.execute(
        """INSERT INTO project_vehicle_assignments
           (project_code, plate_number, role, company_id)
           VALUES (?,?,?,?)""",
        ("PRJ-2026-001", "WP-KA-5678", "SUBCONTRACTOR", "SCO-001"),
    )

    conn.execute(
        """INSERT INTO vehicle_assignments (user_id, plate_number) VALUES (?,?)""",
        (3, "WP-CAB-1234"),
    )

    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    yield conn

@pytest.fixture
def engine(seeded_db):
    """AttendanceEngine wired to seeded_db with a mock barrier."""
    from src.attendance import AttendanceEngine
    from src.barrier import BarrierController

    barrier = BarrierController("MOCK")
    eng = AttendanceEngine(conn=seeded_db, barrier=barrier)
    return eng

@pytest.fixture
def frozen_time(monkeypatch):
    """Return a setter that fixes src.attendance.datetime.now to a given datetime."""
    import src.attendance as att_mod

    class _FrozenDatetime:
        def __init__(self):
            self._fixed: datetime | None = None

        def set(self, dt: datetime) -> None:
            self._fixed = dt
            monkeypatch.setattr(
                att_mod, "_now",
                lambda: self._fixed,
            )

    return _FrozenDatetime()

@pytest.fixture
def mock_barrier():
    """MOCK-mode BarrierController — records open/close calls."""
    from src.barrier import BarrierController
    return BarrierController("MOCK")

@pytest.fixture
def make_jpeg_bytes():
    """Return a factory that creates a tiny JPEG bytestring (numpy required)."""
    import numpy as np
    import cv2

    def _factory(width: int = 200, height: int = 80, text: str = "TEST") -> bytes:
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:] = (40, 40, 40)
        cv2.putText(
            img, text, (10, height // 2 + 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
        )
        _, buf = cv2.imencode(".jpg", img)
        return bytes(buf)

    return _factory
