"""18 tests for SHA-256 hash chain (FR-05.1)."""
from __future__ import annotations

import json

import pytest

from src.audit import compute_row_hash, get_prev_hash, verify_chain
from src.config import GENESIS_SALT
from src.database import transaction


def _insert(conn, plate, ts, gate, direction, status="ON_TIME_ENTRY"):
    with transaction(conn) as cur:
        prev = get_prev_hash(cur)
        h = compute_row_hash(plate, ts, gate, direction, prev)
        cur.execute(
            "INSERT INTO access_log "
            "(plate_number,timestamp,gate_id,direction,status,row_hash) "
            "VALUES (?,?,?,?,?,?)",
            (plate, ts, gate, direction, status, h),
        )
        return cur.lastrowid


def test_genesis_hash_deterministic():
    a = compute_row_hash("X", "2026-01-01T00:00:00Z", "G", "ENTRY", GENESIS_SALT)
    b = compute_row_hash("X", "2026-01-01T00:00:00Z", "G", "ENTRY", GENESIS_SALT)
    assert a == b
    assert len(a) == 64


def test_hash_changes_with_plate():
    h1 = compute_row_hash("A", "t", "g", "ENTRY", GENESIS_SALT)
    h2 = compute_row_hash("B", "t", "g", "ENTRY", GENESIS_SALT)
    assert h1 != h2


def test_hash_changes_with_timestamp():
    h1 = compute_row_hash("A", "t1", "g", "ENTRY", GENESIS_SALT)
    h2 = compute_row_hash("A", "t2", "g", "ENTRY", GENESIS_SALT)
    assert h1 != h2


def test_hash_changes_with_gate():
    assert (compute_row_hash("A", "t", "G1", "ENTRY", GENESIS_SALT)
            != compute_row_hash("A", "t", "G2", "ENTRY", GENESIS_SALT))


def test_hash_changes_with_direction():
    assert (compute_row_hash("A", "t", "g", "ENTRY", GENESIS_SALT)
            != compute_row_hash("A", "t", "g", "EXIT", GENESIS_SALT))


def test_hash_changes_with_prev():
    assert (compute_row_hash("A", "t", "g", "ENTRY", "p1")
            != compute_row_hash("A", "t", "g", "ENTRY", "p2"))


def test_get_prev_hash_empty(db):
    cur = db.cursor()
    assert get_prev_hash(cur) == GENESIS_SALT


def test_get_prev_hash_after_insert(db):
    _insert(db, "X", "2026-01-01T00:00:00Z", "G", "ENTRY")
    cur = db.cursor()
    assert get_prev_hash(cur) != GENESIS_SALT


def test_chain_intact_single(db):
    _insert(db, "X", "2026-01-01T00:00:00Z", "G", "ENTRY")
    res = verify_chain(db)
    assert res.intact and res.first_bad_id is None
    assert res.rows_checked == 1


def test_chain_intact_many(db):
    for i in range(20):
        _insert(db, f"P{i}", f"2026-01-01T00:{i:02d}:00Z", "G", "ENTRY")
    res = verify_chain(db)
    assert res.intact
    assert res.rows_checked == 20


def test_chain_intact_empty(db):
    res = verify_chain(db)
    assert res.intact
    assert res.rows_checked == 0


def test_chain_detects_modified_plate(db):
    _insert(db, "A", "2026-01-01T00:00:00Z", "G", "ENTRY")
    rid = _insert(db, "B", "2026-01-01T00:01:00Z", "G", "ENTRY")
    db.execute("UPDATE access_log SET plate_number='HACK' WHERE id=?", (rid,))
    db.execute("COMMIT") if db.in_transaction else None
    res = verify_chain(db)
    assert not res.intact
    assert res.first_bad_id == rid


def test_chain_detects_modified_timestamp(db):
    _insert(db, "A", "2026-01-01T00:00:00Z", "G", "ENTRY")
    db.execute("UPDATE access_log SET timestamp='2099-01-01T00:00:00Z' WHERE id=1")
    res = verify_chain(db)
    assert not res.intact and res.first_bad_id == 1


def test_chain_detects_modified_gate(db):
    _insert(db, "A", "2026-01-01T00:00:00Z", "GATE_A", "ENTRY")
    db.execute("UPDATE access_log SET gate_id='GATE_X' WHERE id=1")
    res = verify_chain(db)
    assert not res.intact


def test_chain_detects_modified_direction(db):
    _insert(db, "A", "t", "G", "ENTRY")
    db.execute("UPDATE access_log SET direction='EXIT' WHERE id=1")
    res = verify_chain(db)
    assert not res.intact


def test_chain_detects_row_deletion(db):
    _insert(db, "A", "t1", "G", "ENTRY")
    _insert(db, "B", "t2", "G", "ENTRY")
    _insert(db, "C", "t3", "G", "ENTRY")
    db.execute("DELETE FROM access_log WHERE id=2")
    res = verify_chain(db)
    assert not res.intact
    assert res.first_bad_id == 3


def test_chain_detects_row_insertion(db):
    _insert(db, "A", "t1", "G", "ENTRY")
    _insert(db, "B", "t2", "G", "ENTRY")
    # Inject a fake row with a wrong hash
    db.execute(
        "INSERT INTO access_log "
        "(plate_number,timestamp,gate_id,direction,status,row_hash) "
        "VALUES ('X','tx','G','ENTRY','UNKNOWN','deadbeef')")
    res = verify_chain(db)
    assert not res.intact


def test_zero_false_positives_under_load(db):
    for i in range(1000):
        _insert(db, f"P{i:04d}", f"2026-01-01T{i//60:02d}:{i%60:02d}:00Z",
                "GATE_A", "ENTRY" if i % 2 == 0 else "EXIT")
    res = verify_chain(db)
    assert res.intact
    assert res.rows_checked == 1000
    assert res.first_bad_id is None
