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
        for plate in ("CAB-1234", "KL-5678", "WP-CAB-9012", "CAR-4521", "VAN-8801"):
            cur.execute(
                "INSERT INTO registered_vehicles "
                "(plate_number,vehicle_category,registration_status) VALUES (?,?,?)",
                (plate, "CONTRACTOR", "ACTIVE"),
            )
            cur.execute("INSERT INTO vehicle_shifts VALUES (?,?)",
                        (plate, "DAY_SHIFT"))
        cur.execute(
            "INSERT INTO registered_vehicles "
            "(plate_number,vehicle_category,registration_status) VALUES (?,?,?)",
            ("SUS-0001", "CONTRACTOR", "SUSPENDED"),
        )
        cur.execute(
            "INSERT INTO registered_vehicles "
            "(plate_number,vehicle_category,registration_status) VALUES (?,?,?)",
            ("EXP-0001", "CONTRACTOR", "EXPIRED"),
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
