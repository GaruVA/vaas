"""12 integration / system tests (§7.3, Table 7.2). Marked @pytest.mark.integration."""
from __future__ import annotations

import json

import pytest

from src.attendance import AttendanceEngine
from src.audit import verify_chain
from src.barrier import BarrierController
from src.database import transaction
from src.lpm_mled import lpm_mled_correct

pytestmark = pytest.mark.integration


def test_seed_and_verify_chain_intact(seeded_db, jpeg_bytes):
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"))
    for plate in ("CAB-1234", "KL-5678", "WP-CAB-9012"):
        e.process_gate_event(plate, 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    e.shutdown()
    assert verify_chain(seeded_db).intact


def test_full_visitor_admit_flow(seeded_db, jpeg_bytes):
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"),
                         exception_timeout_seconds=5)
    r = e.process_gate_event("VISIT-001", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    e.dispose_exception(r.access_log_id, "ADMIT")
    e.shutdown()
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?",
                            (r.access_log_id,)).fetchone()
    assert row["status"] == "VISITOR_ADMITTED"


def test_full_visitor_reject_flow(seeded_db, jpeg_bytes):
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"),
                         exception_timeout_seconds=5)
    r = e.process_gate_event("VISIT-002", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    e.dispose_exception(r.access_log_id, "REJECT")
    e.shutdown()
    n = seeded_db.execute(
        "SELECT COUNT(*) AS c FROM gate_rejections WHERE plate_number='VISIT-002'"
    ).fetchone()["c"]
    assert n >= 1


def test_lpm_correction_drives_match(seeded_db, jpeg_bytes):
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"))
    r = e.process_gate_event("CA8-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    e.shutdown()
    assert r.matched_plate == "CAB-1234"


def test_acceptance_criterion_typoed_z_returns_none():
    candidates = ["CAB-1234"]
    # Acceptance criterion: only one substitution that ISN'T a confusion pair
    assert lpm_mled_correct("CAZZ-1Z", candidates) is None


def test_suspended_logged_to_rejections(seeded_db, jpeg_bytes):
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"))
    e.process_gate_event("SUS-0001", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    e.shutdown()
    n = seeded_db.execute("SELECT COUNT(*) AS c FROM gate_rejections "
                          "WHERE plate_number='SUS-0001'").fetchone()["c"]
    assert n == 1


def test_dwell_across_multiple_gates(seeded_db, jpeg_bytes):
    from tests.conftest import utc
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"))
    e.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY",
                         jpeg_bytes, timestamp=utc(2026, 4, 30, 8, 0))
    r = e.process_gate_event("CAB-1234", 0.9, "GATE_B", "EXIT",
                             jpeg_bytes, timestamp=utc(2026, 4, 30, 17, 0))
    e.shutdown()
    assert r.dwell_time_seconds == 9 * 3600


def test_chain_breaks_on_modification(seeded_db, jpeg_bytes):
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"))
    e.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    e.process_gate_event("KL-5678", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    e.shutdown()
    seeded_db.execute("UPDATE access_log SET plate_number='HACK' WHERE id=1")
    res = verify_chain(seeded_db)
    assert not res.intact


def test_analytics_after_full_day(seeded_db, jpeg_bytes):
    from src.analytics import daily_attendance_report
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"))
    from tests.conftest import utc
    e.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY",
                         jpeg_bytes, timestamp=utc(2026, 4, 30, 8, 5))
    e.process_gate_event("CAB-1234", 0.9, "GATE_A", "EXIT",
                         jpeg_bytes, timestamp=utc(2026, 4, 30, 17, 0))
    e.shutdown()
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    assert any(r.plate_number == "CAB-1234" for r in rows)


def test_seed_db_creates_demo_vehicles(tmp_path):
    from scripts.seed_db import seed
    p = tmp_path / "seed.db"
    creds = seed(db_path=p, admin_password="testpw")
    assert "admin" in creds
    from src.database import connect
    c = connect(p)
    n = c.execute("SELECT COUNT(*) AS c FROM registered_vehicles").fetchone()["c"]
    assert n == 10
    c.close()


def test_seed_db_creates_two_shifts(tmp_path):
    from scripts.seed_db import seed
    from src.database import connect
    p = tmp_path / "seed.db"
    seed(db_path=p, admin_password="x")
    c = connect(p)
    n = c.execute("SELECT COUNT(*) AS c FROM shifts").fetchone()["c"]
    assert n == 2
    c.close()


def test_exception_timeout_path(seeded_db, jpeg_bytes):
    import time
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"),
                         exception_timeout_seconds=1)
    r = e.process_gate_event("UNKNOWN-T", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    time.sleep(1.5)
    e.shutdown()
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?",
                            (r.access_log_id,)).fetchone()
    assert row["status"] == "VISITOR_TIMEOUT_REJECT"
