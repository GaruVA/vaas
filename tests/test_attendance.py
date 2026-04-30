"""28 tests for the Attendance Engine (§5.4, §6.4)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from src.attendance import AttendanceEngine
from src.barrier import BarrierController
from tests.conftest import utc


def test_active_entry_opens_barrier(engine, jpeg_bytes):
    r = engine.process_gate_event("CAB-1234", 0.95, "GATE_A", "ENTRY", jpeg_bytes)
    assert r.outcome == "BARRIER_OPENED"
    assert r.matched_plate == "CAB-1234"


def test_visitor_creates_exception(engine, jpeg_bytes):
    r = engine.process_gate_event("ZZZ-9999", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    assert r.outcome == "EXCEPTION_PENDING_DISPOSITION"
    assert r.status == "VISITOR"
    assert r.access_log_id is not None


def test_suspended_vehicle_rejected(engine, jpeg_bytes):
    r = engine.process_gate_event("SUS-0001", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    assert r.outcome == "BARRIER_CLOSED_REJECTED"
    assert r.status == "SUSPENDED"


def test_expired_vehicle_rejected(engine, jpeg_bytes):
    r = engine.process_gate_event("EXP-0001", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    assert r.outcome == "BARRIER_CLOSED_REJECTED"
    assert r.status == "EXPIRED"


def test_lpm_correction_via_confusion_pair(engine, jpeg_bytes):
    r = engine.process_gate_event("CA8-1234", 0.92, "GATE_A", "ENTRY", jpeg_bytes)
    assert r.matched_plate == "CAB-1234"


def test_on_time_entry_status(engine, jpeg_bytes):
    ts = utc(2026, 4, 30, 8, 5)  # Thursday day shift starts 08:00 +10min grace
    r = engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes, timestamp=ts)
    assert r.status == "ON_TIME_ENTRY"


def test_late_arrival_status(engine, jpeg_bytes):
    ts = utc(2026, 4, 30, 9, 30)
    r = engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes, timestamp=ts)
    assert r.status == "LATE_ARRIVAL"


def test_early_arrival_status(engine, jpeg_bytes):
    ts = utc(2026, 4, 30, 5, 0)
    r = engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes, timestamp=ts)
    assert r.status == "EARLY_ARRIVAL"


def test_on_time_exit_status(engine, jpeg_bytes):
    ts_in = utc(2026, 4, 30, 8, 0)
    engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes, timestamp=ts_in)
    ts_out = utc(2026, 4, 30, 17, 30)
    r = engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "EXIT", jpeg_bytes, timestamp=ts_out)
    assert r.status == "ON_TIME_EXIT"


def test_early_departure_status(engine, jpeg_bytes):
    ts_in = utc(2026, 4, 30, 8, 0)
    engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes, timestamp=ts_in)
    ts_out = utc(2026, 4, 30, 12, 0)
    r = engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "EXIT", jpeg_bytes, timestamp=ts_out)
    assert r.status == "EARLY_DEPARTURE"


def test_dwell_time_computed_on_exit(engine, jpeg_bytes):
    ts_in = utc(2026, 4, 30, 8, 0)
    ts_out = utc(2026, 4, 30, 16, 0)
    engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes, timestamp=ts_in)
    r = engine.process_gate_event("CAB-1234", 0.9, "GATE_B", "EXIT", jpeg_bytes, timestamp=ts_out)
    assert r.dwell_time_seconds == 8 * 3600


def test_dwell_time_none_without_prior_entry(engine, jpeg_bytes):
    ts_out = utc(2026, 4, 30, 16, 0)
    r = engine.process_gate_event("KL-5678", 0.9, "GATE_A", "EXIT", jpeg_bytes, timestamp=ts_out)
    assert r.dwell_time_seconds is None


def test_access_log_row_inserted(engine, seeded_db, jpeg_bytes):
    engine.process_gate_event("CAB-1234", 0.91, "GATE_A", "ENTRY", jpeg_bytes)
    row = seeded_db.execute("SELECT * FROM access_log").fetchone()
    assert row["plate_number"] == "CAB-1234"
    assert row["row_hash"]
    assert row["plate_crop_b64"]


def test_access_log_hash_chained(engine, seeded_db, jpeg_bytes):
    engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    engine.process_gate_event("KL-5678", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    rows = seeded_db.execute("SELECT row_hash FROM access_log ORDER BY id").fetchall()
    assert rows[0]["row_hash"] != rows[1]["row_hash"]


def test_dispose_admit_updates_status(engine, seeded_db, jpeg_bytes):
    r = engine.process_gate_event("UNKNOWN-1", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    engine.dispose_exception(r.access_log_id, "ADMIT")
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?",
                            (r.access_log_id,)).fetchone()
    assert row["status"] == "VISITOR_ADMITTED"


def test_dispose_reject_updates_status(engine, seeded_db, jpeg_bytes):
    r = engine.process_gate_event("UNKNOWN-2", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    engine.dispose_exception(r.access_log_id, "REJECT")
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?",
                            (r.access_log_id,)).fetchone()
    assert row["status"] == "VISITOR_REJECTED"


def test_dispose_register_updates_status(engine, seeded_db, jpeg_bytes):
    r = engine.process_gate_event("NEW-PLATE", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    engine.dispose_exception(r.access_log_id, "REGISTER")
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?",
                            (r.access_log_id,)).fetchone()
    assert row["status"] == "VISITOR_PENDING_REGISTRATION"


def test_dispose_invalid_raises(engine, jpeg_bytes):
    r = engine.process_gate_event("XXX-X", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    with pytest.raises(ValueError):
        engine.dispose_exception(r.access_log_id, "BOGUS")  # type: ignore[arg-type]


def test_exception_timeout_auto_rejects(engine, seeded_db, jpeg_bytes):
    r = engine.process_gate_event("TIMEOUT-1", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    time.sleep(2.5)  # exception_timeout_seconds=2 in fixture
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?",
                            (r.access_log_id,)).fetchone()
    assert row["status"] == "VISITOR_TIMEOUT_REJECT"


def test_admit_cancels_timeout(engine, seeded_db, jpeg_bytes):
    r = engine.process_gate_event("TIMEOUT-2", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    engine.dispose_exception(r.access_log_id, "ADMIT")
    time.sleep(2.5)
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?",
                            (r.access_log_id,)).fetchone()
    assert row["status"] == "VISITOR_ADMITTED"


def test_multi_gate_dwell(engine, jpeg_bytes):
    ts1 = utc(2026, 4, 30, 8, 0)
    ts2 = utc(2026, 4, 30, 16, 0)
    engine.process_gate_event("KL-5678", 0.9, "GATE_A", "ENTRY", jpeg_bytes, timestamp=ts1)
    r = engine.process_gate_event("KL-5678", 0.9, "GATE_B", "EXIT", jpeg_bytes, timestamp=ts2)
    assert r.dwell_time_seconds == 8 * 3600


def test_duplicate_entry_without_exit(engine, seeded_db, jpeg_bytes):
    engine.process_gate_event("WP-CAB-9012", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    engine.process_gate_event("WP-CAB-9012", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    n = seeded_db.execute(
        "SELECT COUNT(*) AS c FROM access_log WHERE plate_number='WP-CAB-9012'"
    ).fetchone()["c"]
    assert n == 2  # both logged; analytics flag duplicates


def test_rejection_logged_to_gate_rejections(engine, seeded_db, jpeg_bytes):
    engine.process_gate_event("SUS-0001", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    n = seeded_db.execute(
        "SELECT COUNT(*) AS c FROM gate_rejections WHERE plate_number='SUS-0001'"
    ).fetchone()["c"]
    assert n >= 1


def test_unregistered_plate_status_visitor(engine, seeded_db, jpeg_bytes):
    engine.process_gate_event("RANDOM", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    row = seeded_db.execute("SELECT status FROM access_log").fetchone()
    assert row["status"] == "VISITOR"


def test_sse_publish_called_on_event(seeded_db, jpeg_bytes):
    events = []
    e = AttendanceEngine(seeded_db, barrier=BarrierController(mode="MOCK"),
                         sse_publish=events.append)
    e.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    e.shutdown()
    assert any(ev.get("type") == "gate_event" for ev in events)


def test_confidence_recorded(engine, seeded_db, jpeg_bytes):
    engine.process_gate_event("CAB-1234", 0.83, "GATE_A", "ENTRY", jpeg_bytes)
    row = seeded_db.execute("SELECT confidence_score FROM access_log").fetchone()
    assert abs(row["confidence_score"] - 0.83) < 1e-6


def test_shift_id_stored(engine, seeded_db, jpeg_bytes):
    engine.process_gate_event("CAB-1234", 0.9, "GATE_A", "ENTRY", jpeg_bytes)
    row = seeded_db.execute("SELECT shift_id FROM access_log").fetchone()
    assert row["shift_id"] == "DAY_SHIFT"


def test_visitor_no_match_keeps_raw_plate(engine, seeded_db, jpeg_bytes):
    engine.process_gate_event("WEIRDXYZ", 0.4, "GATE_A", "ENTRY", jpeg_bytes)
    row = seeded_db.execute("SELECT plate_number FROM access_log").fetchone()
    assert row["plate_number"] == "WEIRDXYZ"
