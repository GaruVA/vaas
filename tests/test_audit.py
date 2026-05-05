"""19 tests for SHA-256 hash chain (FR-05.1).

The hash payload now includes the row id (sec fix) to prevent
row-reordering attacks.  The _insert helper uses a two-step
INSERT/UPDATE pattern mirroring production code.
"""
from __future__ import annotations

import pytest

from src.audit import compute_row_hash, get_prev_hash, verify_chain
from src.config import GENESIS_SALT
from src.database import transaction

_TEST_ROW_ID = 1


def _insert(conn, plate, ts, gate, direction, status="ON_TIME_ENTRY"):
    with transaction(conn) as cur:
        prev = get_prev_hash(cur)
        cur.execute(
            "INSERT INTO access_log "
            "(plate_number,timestamp,gate_id,direction,status,row_hash) "
            "VALUES (?,?,?,?,?,?)",
            (plate, ts, gate, direction, status, "PENDING"),
        )
        row_id = cur.lastrowid
        h = compute_row_hash(row_id, plate, ts, gate, direction, prev)
        cur.execute("UPDATE access_log SET row_hash=? WHERE id=?", (h, row_id))
        return row_id


def test_genesis_hash_deterministic():
    a = compute_row_hash(_TEST_ROW_ID, "X", "2026-01-01T00:00:00Z", "G", "ENTRY", GENESIS_SALT)
    b = compute_row_hash(_TEST_ROW_ID, "X", "2026-01-01T00:00:00Z", "G", "ENTRY", GENESIS_SALT)
    assert a == b
    assert len(a) == 64


def test_hash_changes_with_plate():
    h1 = compute_row_hash(_TEST_ROW_ID, "A", "t", "g", "ENTRY", GENESIS_SALT)
    h2 = compute_row_hash(_TEST_ROW_ID, "B", "t", "g", "ENTRY", GENESIS_SALT)
    assert h1 != h2


def test_hash_changes_with_timestamp():
    h1 = compute_row_hash(_TEST_ROW_ID, "A", "t1", "g", "ENTRY", GENESIS_SALT)
    h2 = compute_row_hash(_TEST_ROW_ID, "A", "t2", "g", "ENTRY", GENESIS_SALT)
    assert h1 != h2


def test_hash_changes_with_gate():
    assert (compute_row_hash(_TEST_ROW_ID, "A", "t", "G1", "ENTRY", GENESIS_SALT)
            != compute_row_hash(_TEST_ROW_ID, "A", "t", "G2", "ENTRY", GENESIS_SALT))


def test_hash_changes_with_direction():
    assert (compute_row_hash(_TEST_ROW_ID, "A", "t", "g", "ENTRY", GENESIS_SALT)
            != compute_row_hash(_TEST_ROW_ID, "A", "t", "g", "EXIT", GENESIS_SALT))


def test_hash_changes_with_prev():
    assert (compute_row_hash(_TEST_ROW_ID, "A", "t", "g", "ENTRY", "p1")
            != compute_row_hash(_TEST_ROW_ID, "A", "t", "g", "ENTRY", "p2"))


def test_hash_changes_with_row_id():
    h1 = compute_row_hash(1, "A", "t", "g", "ENTRY", GENESIS_SALT)
    h2 = compute_row_hash(2, "A", "t", "g", "ENTRY", GENESIS_SALT)
    assert h1 != h2


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
    db.execute("UPDATE access_log SET plate_number=? WHERE id=?", ("HACK", rid))
    res = verify_chain(db)
    assert not res.intact
    assert res.first_bad_id == rid


def test_chain_detects_modified_timestamp(db):
    _insert(db, "A", "2026-01-01T00:00:00Z", "G", "ENTRY")
    db.execute("UPDATE access_log SET timestamp=? WHERE id=1", ("2099-01-01T00:00:00Z",))
    res = verify_chain(db)
    assert not res.intact and res.first_bad_id == 1


def test_chain_detects_modified_gate(db):
    _insert(db, "A", "2026-01-01T00:00:00Z", "GATE_A", "ENTRY")
    db.execute("UPDATE access_log SET gate_id=? WHERE id=1", ("GATE_X",))
    res = verify_chain(db)
    assert not res.intact


def test_chain_detects_modified_direction(db):
    _insert(db, "A", "t", "G", "ENTRY")
    db.execute("UPDATE access_log SET direction=? WHERE id=1", ("EXIT",))
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
    db.execute(
        "INSERT INTO access_log "
        "(plate_number,timestamp,gate_id,direction,status,row_hash) "
        "VALUES (?,?,?,?,?,?)",
        ("X", "tx", "G", "ENTRY", "UNKNOWN", "deadbeef"),
    )
    res = verify_chain(db)
    assert not res.intact


def test_chain_detects_row_reorder(db):
    _insert(db, "FIRST", "2026-01-01T00:00:00Z", "GATE_A", "ENTRY")
    _insert(db, "SECOND", "2026-01-01T00:01:00Z", "GATE_A", "ENTRY")
    db.execute("UPDATE access_log SET plate_number=? WHERE id=1", ("SECOND",))
    db.execute("UPDATE access_log SET plate_number=? WHERE id=2", ("FIRST",))
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
