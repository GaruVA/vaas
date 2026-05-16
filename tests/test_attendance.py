from __future__ import annotations

"""28 tests for src/attendance.py -- AttendanceEngine."""

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from src.attendance import AttendanceEngine, GateOutcome, GateStatus
from src.barrier import BarrierController

DAY_START  = datetime(2026, 1, 5, 7, 0, 0, tzinfo=timezone.utc)
SHIFT_END  = datetime(2026, 1, 5, 15, 0, 0, tzinfo=timezone.utc)
GRACE_MIN  = 15

def _engine(db, timeout=30, sse=None):
    return AttendanceEngine(db, BarrierController("MOCK"),
                            sse_callback=sse, exception_timeout=timeout)

def _evt(eng, direction="ENTRY", plate="WP-CAB-1234", ts=None, gate="MAIN_GATE", conf=0.95):
    return eng.process_gate_event(
        raw_plate=plate, confidence=conf, gate_id=gate,
        direction=direction, plate_crop_jpeg_bytes=b"", timestamp=ts or DAY_START,
    )

def test_01_on_time_entry_exact(seeded_db):
    result = _evt(_engine(seeded_db), ts=DAY_START)
    assert result.status == GateStatus.ON_TIME_ENTRY
    assert result.outcome == GateOutcome.BARRIER_OPENED

def test_02_on_time_entry_within_grace(seeded_db):
    result = _evt(_engine(seeded_db), ts=DAY_START + timedelta(minutes=GRACE_MIN - 1))
    assert result.status == GateStatus.ON_TIME_ENTRY

def test_03_late_arrival_after_grace(seeded_db):
    result = _evt(_engine(seeded_db), ts=DAY_START + timedelta(minutes=GRACE_MIN + 1))
    assert result.status == GateStatus.LATE_ARRIVAL

def test_04_early_arrival(seeded_db):
    result = _evt(_engine(seeded_db), ts=DAY_START - timedelta(minutes=30))
    assert result.status == GateStatus.EARLY_ARRIVAL

def test_05_on_time_exit_within_grace(seeded_db):
    eng = _engine(seeded_db)
    _evt(eng, direction="ENTRY", ts=DAY_START)
    result = _evt(eng, direction="EXIT", ts=SHIFT_END + timedelta(minutes=5))
    assert result.status == GateStatus.ON_TIME_EXIT

def test_06_early_departure(seeded_db):
    eng = _engine(seeded_db)
    _evt(eng, direction="ENTRY", ts=DAY_START)
    result = _evt(eng, direction="EXIT", ts=SHIFT_END - timedelta(hours=2))
    assert result.status == GateStatus.EARLY_DEPARTURE

def test_07_overstay(seeded_db):
    eng = _engine(seeded_db)
    _evt(eng, direction="ENTRY", ts=DAY_START)
    result = _evt(eng, direction="EXIT", ts=SHIFT_END + timedelta(minutes=GRACE_MIN + 1))
    assert result.status == GateStatus.OVERSTAY

def test_08_night_shift_entry_at_2359(seeded_db):
    seeded_db.execute(
        "INSERT OR IGNORE INTO vehicle_shifts (plate_number, shift_id) VALUES (?,?)",
        ("WP-CD-7788", "NIGHT"),
    )
    eng = _engine(seeded_db)
    ts = datetime(2026, 1, 5, 23, 5, 0, tzinfo=timezone.utc)
    result = eng.process_gate_event("WP-CD-7788", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=ts)
    assert result.outcome == GateOutcome.BARRIER_OPENED
    assert result.status == GateStatus.ON_TIME_ENTRY

def test_09_night_shift_entry_at_0001(seeded_db):

    seeded_db.execute(
        "INSERT OR IGNORE INTO vehicle_shifts (plate_number, shift_id) VALUES (?,?)",
        ("SG-1111", "NIGHT"),
    )
    eng = _engine(seeded_db)
    ts = datetime(2026, 1, 6, 0, 1, 0, tzinfo=timezone.utc)

    result = eng.process_gate_event("SG-1111", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=ts)
    assert result.outcome == GateOutcome.BARRIER_OPENED
    assert result.status == GateStatus.LATE_ARRIVAL

def test_10_unknown_plate_visitor_exception(seeded_db):
    eng = _engine(seeded_db, timeout=60)
    result = eng.process_gate_event("ZZ-0000", 0.5, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    assert result.outcome == GateOutcome.EXCEPTION_PENDING_DISPOSITION
    assert result.status == GateStatus.VISITOR
    assert result.access_log_id is not None
    if result.access_log_id in eng._pending_timers:
        eng._pending_timers[result.access_log_id].cancel()

def test_11_visitor_auto_reject_after_timeout(seeded_db):
    eng = _engine(seeded_db, timeout=1)
    result = eng.process_gate_event("ZZ-9999", 0.5, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    log_id = result.access_log_id
    time.sleep(1.5)
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?", (log_id,)).fetchone()
    assert row[0] == GateStatus.VISITOR_TIMEOUT_REJECT.value

def test_12_dispose_admit_opens_barrier(seeded_db):
    barrier = BarrierController("MOCK")
    eng = AttendanceEngine(seeded_db, barrier, exception_timeout=60)
    result = eng.process_gate_event("ZZ-8888", 0.5, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    log_id = result.access_log_id
    eng.dispose_exception(log_id, "ADMIT", operator_user_id=1)
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?", (log_id,)).fetchone()
    assert row[0] == GateStatus.VISITOR_ADMITTED.value
    assert any(cmd == "OPEN" for _, cmd in barrier.command_log())

def test_13_dispose_reject(seeded_db):
    eng = _engine(seeded_db, timeout=60)
    result = eng.process_gate_event("ZZ-7777", 0.5, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    log_id = result.access_log_id
    eng.dispose_exception(log_id, "REJECT", operator_user_id=1)
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?", (log_id,)).fetchone()
    assert row[0] == GateStatus.VISITOR_REJECTED.value

def test_14_dispose_register(seeded_db):
    eng = _engine(seeded_db, timeout=60)
    result = eng.process_gate_event("ZZ-6666", 0.5, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    log_id = result.access_log_id
    eng.dispose_exception(log_id, "REGISTER", operator_user_id=1)
    row = seeded_db.execute("SELECT status FROM access_log WHERE id=?", (log_id,)).fetchone()
    assert row[0] == GateStatus.VISITOR_PENDING_REGISTRATION.value

def test_15_suspended_vehicle_rejected(seeded_db):
    seeded_db.execute(
        "UPDATE registered_vehicles SET registration_status='SUSPENDED' WHERE plate_number='WP-AB-3344'"
    )
    eng = _engine(seeded_db)
    result = eng.process_gate_event("WP-AB-3344", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    assert result.outcome == GateOutcome.BARRIER_CLOSED_REJECTED
    assert result.status == GateStatus.SUSPENDED
    row = seeded_db.execute(
        "SELECT reason FROM gate_rejections WHERE plate_number='WP-AB-3344'"
    ).fetchone()
    assert row is not None

def test_16_expired_vehicle_rejected(seeded_db):
    seeded_db.execute(
        "UPDATE registered_vehicles SET registration_status='EXPIRED' WHERE plate_number='WP-EF-2233'"
    )
    result = _evt(_engine(seeded_db), plate="WP-EF-2233")
    assert result.outcome == GateOutcome.BARRIER_CLOSED_REJECTED
    assert result.status == GateStatus.EXPIRED

def test_17_dwell_time_computed(seeded_db):
    eng = _engine(seeded_db)
    _evt(eng, direction="ENTRY", ts=DAY_START)
    result = _evt(eng, direction="EXIT", ts=DAY_START + timedelta(hours=2))
    row = seeded_db.execute(
        "SELECT dwell_time_seconds FROM access_log WHERE id=?", (result.access_log_id,)
    ).fetchone()
    assert row[0] == pytest.approx(7200.0, abs=1.0)

def test_18_no_shift_vehicle_admitted(seeded_db):
    eng = _engine(seeded_db)
    result = eng.process_gate_event("NW-9900", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    assert result.outcome == GateOutcome.BARRIER_OPENED
    assert result.status == GateStatus.VISITOR_ADMITTED

def test_19_access_log_row_hash_not_pending(seeded_db):
    result = _evt(_engine(seeded_db))
    row = seeded_db.execute(
        "SELECT row_hash FROM access_log WHERE id=?", (result.access_log_id,)
    ).fetchone()
    assert row[0] != "PENDING"
    assert len(row[0]) == 64

def test_20_active_entry_opens_barrier(seeded_db):
    barrier = BarrierController("MOCK")
    _evt(AttendanceEngine(seeded_db, barrier))
    assert barrier.command_log()[-1][1] == "OPEN"

def test_21_suspended_entry_does_not_open_barrier(seeded_db):
    seeded_db.execute(
        "UPDATE registered_vehicles SET registration_status='SUSPENDED' WHERE plate_number='WP-GA-7890'"
    )
    barrier = BarrierController("MOCK")
    eng = AttendanceEngine(seeded_db, barrier)
    eng.process_gate_event("WP-GA-7890", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    assert all(cmd != "OPEN" for _, cmd in barrier.command_log())

def test_22_confidence_score_stored(seeded_db):
    eng = _engine(seeded_db)
    result = eng.process_gate_event("WP-CAB-1234", 0.87, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    row = seeded_db.execute(
        "SELECT confidence_score FROM access_log WHERE id=?", (result.access_log_id,)
    ).fetchone()
    assert row[0] == pytest.approx(0.87, abs=0.001)

def test_23_plate_crop_b64_stored(seeded_db):
    import base64
    fake_jpeg = b"\xff\xd8\xff\xe0test"
    eng = _engine(seeded_db)
    result = eng.process_gate_event("WP-CAB-1234", 0.9, "MAIN_GATE", "ENTRY", fake_jpeg, timestamp=DAY_START)
    row = seeded_db.execute(
        "SELECT plate_crop_b64 FROM access_log WHERE id=?", (result.access_log_id,)
    ).fetchone()
    assert row[0] == base64.b64encode(fake_jpeg).decode()

def test_24_overstay_flag_idempotent_concurrent(seeded_db):
    eng = _engine(seeded_db)
    result = _evt(eng)
    row_id = result.access_log_id
    plate = "WP-CAB-1234"
    w_start = "2026-01-05T07:00:00Z"
    w_end   = "2026-01-05T17:00:00Z"
    errors = []
    def flag():
        try:
            eng._flag_overstay(row_id, plate, w_start, w_end)
        except Exception as e:
            errors.append(e)
    t1 = threading.Thread(target=flag)
    t2 = threading.Thread(target=flag)
    t1.start(); t2.start(); t1.join(); t2.join()
    assert not errors
    count = seeded_db.execute(
        "SELECT COUNT(*) FROM access_log WHERE id=? AND status='OVERSTAY'", (row_id,)
    ).fetchone()[0]
    assert count == 1

def test_25_flag_overstay_second_call_no_op(seeded_db):
    eng = _engine(seeded_db)
    result = _evt(eng)
    row_id = result.access_log_id
    plate = "WP-CAB-1234"
    w_start = "2026-01-05T07:00:00Z"
    w_end   = "2026-01-05T17:00:00Z"
    eng._flag_overstay(row_id, plate, w_start, w_end)
    eng._flag_overstay(row_id, plate, w_start, w_end)
    count = seeded_db.execute(
        "SELECT COUNT(*) FROM access_log WHERE id=? AND status='OVERSTAY'", (row_id,)
    ).fetchone()[0]
    assert count == 1

def test_26_grace_period_not_hardcoded(seeded_db):
    import src.attendance as att_mod, inspect
    source = inspect.getsource(att_mod)
    assert "grace_period_minutes = 15" not in source

def test_27_changing_grace_period_changes_boundary(seeded_db):
    seeded_db.execute("UPDATE shifts SET grace_period_minutes = 5 WHERE shift_id = 'DAY'")
    eng = _engine(seeded_db)

    result = _evt(eng, ts=DAY_START + timedelta(minutes=10))
    assert result.status == GateStatus.LATE_ARRIVAL

def test_28_visitor_triggers_sse_callback(seeded_db):
    events = []
    def sse_cb(event_type, data):
        events.append((event_type, data))
    eng = AttendanceEngine(seeded_db, BarrierController("MOCK"), sse_callback=sse_cb, exception_timeout=60)
    result = eng.process_gate_event("ZZ-9999", 0.5, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    if result.access_log_id in eng._pending_timers:
        eng._pending_timers[result.access_log_id].cancel()
    assert len(events) == 1
    assert events[0][0] == "exception"
    assert "id" in events[0][1]

def test_29_invalid_format_no_dash_discarded(db):
    eng = AttendanceEngine(db, BarrierController("MOCK"))
    result = eng.process_gate_event("ABCDE1", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    assert result.access_log_id is None

def test_30_invalid_format_mixed_prefix_discarded(db):
    eng = AttendanceEngine(db, BarrierController("MOCK"))
    result = eng.process_gate_event("A1-1234", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    assert result.access_log_id is None

def test_31_invalid_format_wrong_digit_count_discarded(db):
    eng = AttendanceEngine(db, BarrierController("MOCK"))
    result = eng.process_gate_event("ABC-12", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    assert result.access_log_id is None

def test_32_valid_format_xx_0000_passes_filter(db):
    eng = AttendanceEngine(db, BarrierController("MOCK"))
    result = eng.process_gate_event("AB-1234", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=DAY_START)
    assert result.access_log_id is not None

def test_33_night_shift_early_arrival_not_misclassified_as_late(seeded_db):
    """Employee on NIGHT shift (23:00 start) arrives at 22:45 — 15 min early.

    Before the candidate-date fix, the engine rolled back one day and returned
    LATE_ARRIVAL (treating it as 23h45m past yesterday's shift start).
    Correct answer: EARLY_ARRIVAL for tonight's shift.
    """
    seeded_db.execute(
        "INSERT OR IGNORE INTO vehicle_shifts (plate_number, shift_id) VALUES (?,?)",
        ("WP-CD-7788", "NIGHT"),
    )
    eng = _engine(seeded_db)
    ts = datetime(2026, 1, 5, 22, 45, 0, tzinfo=timezone.utc)  # 15 min before 23:00 NIGHT start
    result = eng.process_gate_event("WP-CD-7788", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=ts)
    assert result.outcome == GateOutcome.BARRIER_OPENED
    assert result.status == GateStatus.EARLY_ARRIVAL

def test_34_day_shift_early_arrival_within_window(seeded_db):
    """Employee on DAY shift (07:00 start) arrives at 06:15 — 45 min early.

    Within the 60-minute early window so should be EARLY_ARRIVAL, not VISITOR.
    """
    eng = _engine(seeded_db)
    ts = datetime(2026, 1, 5, 6, 15, 0, tzinfo=timezone.utc)  # 45 min before 07:00 DAY start
    result = eng.process_gate_event("WP-CAB-1234", 0.9, "MAIN_GATE", "ENTRY", b"", timestamp=ts)
    assert result.outcome == GateOutcome.BARRIER_OPENED
    assert result.status == GateStatus.EARLY_ARRIVAL
