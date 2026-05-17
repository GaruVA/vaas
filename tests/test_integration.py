from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pytest

from src.attendance import AttendanceEngine, GateStatus
from src.audit import verify_chain
from src.barrier import BarrierController
from src.pipeline import run_pipeline

import src.attendance as _att_mod

_GATE        = "MAIN_GATE"
_PLATE_GOOD  = "WP-CAB-1234"
_PLATE_CONF  = "WP-CA8-1234"
_PLATE_UNREG = "ZZ-ZZZ-9999"

_TS_ONTIME = datetime(2026, 1, 5, 7, 10, 0, tzinfo=timezone.utc)

@dataclass
class _Det:
    crop: np.ndarray
    confidence: float = 0.91

def _blank_frame() -> np.ndarray:
    return np.zeros((480, 640, 3), dtype=np.uint8)

def _make_camera(frames: list[np.ndarray]):
    it = iter(frames)

    class _Cam:
        released = False
        def read(self):   return next(it, None)
        def release(self): _Cam.released = True

    return _Cam()

def _make_detector(emit: bool = True):
    class _D:
        def detect(self, frame):
            return [_Det(crop=frame)] if emit else []
    return _D()

def _make_classifier(plate: str):
    class _C:
        def classify(self, crop): return plate
    return _C()

def _patch_now(monkeypatch, dt: datetime) -> None:
    monkeypatch.setattr(_att_mod, "_now", lambda: dt)

def _run(seeded_db, plate, gate=_GATE, direction="ENTRY", frames=1, emit=True,
         *, barrier=None):
    if barrier is None:
        barrier = BarrierController("MOCK")
    eng = AttendanceEngine(seeded_db, barrier)
    cam = _make_camera([_blank_frame()] * frames)
    run_pipeline(cam, _make_detector(emit), _make_classifier(plate),
                 eng, gate_id=gate, direction=direction)
    return eng, barrier

@pytest.mark.integration
def test_int_01_entry_creates_log_row(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    _run(seeded_db, _PLATE_GOOD)
    rows = seeded_db.execute(
        "SELECT * FROM access_log WHERE plate_number=?", (_PLATE_GOOD,)
    ).fetchall()
    assert len(rows) == 1

@pytest.mark.integration
def test_int_02_row_hash_not_pending(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    _run(seeded_db, _PLATE_GOOD)
    rows = seeded_db.execute("SELECT row_hash FROM access_log").fetchall()
    assert rows, "Expected at least one access_log row"
    for r in rows:
        assert r["row_hash"] != "PENDING", "row_hash must be finalised"

@pytest.mark.integration
def test_int_03_no_detection_no_log_row(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    before = seeded_db.execute("SELECT COUNT(*) FROM access_log").fetchone()[0]
    _run(seeded_db, "", emit=False, frames=2)
    after = seeded_db.execute("SELECT COUNT(*) FROM access_log").fetchone()[0]
    assert after == before

@pytest.mark.integration
def test_int_04_lpm_correction_applied(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    _run(seeded_db, _PLATE_CONF)
    rows = seeded_db.execute("SELECT plate_number FROM access_log").fetchall()
    plates = {r["plate_number"] for r in rows}

    assert _PLATE_GOOD in plates, f"Expected {_PLATE_GOOD!r} in {plates}"

@pytest.mark.integration
def test_int_05_unregistered_plate_visitor_flow(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    _run(seeded_db, _PLATE_UNREG)
    row = seeded_db.execute(
        "SELECT status FROM access_log WHERE plate_number=?", (_PLATE_UNREG,)
    ).fetchone()
    assert row is not None
    assert row["status"] == GateStatus.VISITOR.value

@pytest.mark.integration
def test_int_06_suspended_plate_writes_rejection(seeded_db, monkeypatch):
    seeded_db.execute(
        "UPDATE registered_vehicles SET registration_status='SUSPENDED'"
        " WHERE plate_number=?", (_PLATE_GOOD,)
    )
    _patch_now(monkeypatch, _TS_ONTIME)
    _run(seeded_db, _PLATE_GOOD)
    rej = seeded_db.execute(
        "SELECT reason FROM gate_rejections WHERE plate_number=?", (_PLATE_GOOD,)
    ).fetchone()
    assert rej is not None
    assert rej["reason"] == "SUSPENDED"

@pytest.mark.integration
def test_int_07_barrier_opens_for_valid_entry(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    barrier = BarrierController("MOCK")
    _run(seeded_db, _PLATE_GOOD, barrier=barrier)

    opens = [c for c in barrier.command_log() if c[1] == "OPEN"]
    assert len(opens) >= 1, f"Expected at least one OPEN; got {barrier.command_log()}"

@pytest.mark.integration
def test_int_08_barrier_stays_closed_on_rejection(seeded_db, monkeypatch):
    seeded_db.execute(
        "UPDATE registered_vehicles SET registration_status='SUSPENDED'"
        " WHERE plate_number=?", (_PLATE_GOOD,)
    )
    _patch_now(monkeypatch, _TS_ONTIME)
    barrier = BarrierController("MOCK")
    _run(seeded_db, _PLATE_GOOD, barrier=barrier)
    opens = [c for c in barrier.command_log() if c[1] == "OPEN"]
    assert len(opens) == 0, f"Barrier must not open for SUSPENDED; got {barrier.command_log()}"

@pytest.mark.integration
def test_int_09_stop_event_halts_pipeline(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    eng = AttendanceEngine(seeded_db, BarrierController("MOCK"))
    stop = threading.Event()
    call_count = [0]

    class _InfiniteCam:
        def read(self):   return _blank_frame()
        def release(self): pass

    class _CountingCls:
        def classify(self, crop):
            call_count[0] += 1
            if call_count[0] >= 3:
                stop.set()
            return _PLATE_UNREG

    run_pipeline(_InfiniteCam(), _make_detector(), _CountingCls(),
                 eng, gate_id=_GATE, direction="ENTRY", stop_event=stop)

    assert stop.is_set()
    assert call_count[0] >= 3

@pytest.mark.integration
def test_int_10_frame_callback_called_per_frame(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    received: list[np.ndarray] = []
    eng = AttendanceEngine(seeded_db, BarrierController("MOCK"))
    cam = _make_camera([_blank_frame(), _blank_frame(), _blank_frame()])
    run_pipeline(cam, _make_detector(emit=False), _make_classifier(""),
                 eng, gate_id=_GATE, direction="ENTRY",
                 frame_callback=lambda f: received.append(f))
    assert len(received) == 3
    assert all(isinstance(f, np.ndarray) for f in received)

@pytest.mark.integration
def test_int_11_camera_released_after_pipeline(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    eng = AttendanceEngine(seeded_db, BarrierController("MOCK"))
    cam = _make_camera([_blank_frame()])
    run_pipeline(cam, _make_detector(emit=False), _make_classifier(""),
                 eng, gate_id=_GATE, direction="ENTRY")
    assert cam.released is True

@pytest.mark.integration
def test_int_12_chain_integrity_after_multiple_events(seeded_db, monkeypatch):
    _patch_now(monkeypatch, _TS_ONTIME)
    barrier = BarrierController("MOCK")
    eng = AttendanceEngine(seeded_db, barrier)

    plates = ["WP-CAB-1234", "WP-KA-5678", "KL-9012"]
    frames = [_blank_frame() for _ in plates]
    cam = _make_camera(frames)
    idx = [0]

    class _SeqCls:
        def classify(self, crop):
            p = plates[idx[0] % len(plates)]
            idx[0] += 1
            return p

    run_pipeline(cam, _make_detector(), _SeqCls(),
                 eng, gate_id=_GATE, direction="ENTRY")

    result = verify_chain(seeded_db)
    assert result.ok is True, f"Chain broken: {result.reason}"
    assert result.rows_checked >= len(plates)
