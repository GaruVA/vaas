from __future__ import annotations

"""20 tests for src/audit.py -- SHA-256 two-step hash chain.

Test matrix
-----------
1.  empty log -> ok=True, rows_checked=0
2.  single row -> ok=True, rows_checked=1
3.  genesis prev_hash matches GENESIS_PREV_HASH constant
4.  PK is in payload (verify field)
5.  field-value tampering on interior row -> flagged
6.  field-value tampering on first row -> flagged
7.  field-value tampering on last row -> flagged
8.  row deletion (gap) -> flagged at next row
9.  row reordering (swap field values) -> flagged (PK-in-payload defence)
10. 1000-row chain -> ok=True, zero false positives
11. duplicate insert + finalise on same row -> idempotent (same hash)
12. multi-row chain: each stored hash != its predecessor
13. finalise_row_hash returns hex string of length 64
14. finalise_row_hash raises ValueError for missing row_id
15. verify_chain first_bad_id points to correct row
16. verify_chain reason string contains id of bad row
17. verify_chain rows_checked = total rows on intact chain
18. two separate chains (two DBs) produce same hash for same input
19. status field NOT in payload -- changing status does not break chain
20. log_gate_event convenience helper inserts row with non-PENDING hash
"""

import hashlib
import json
import sqlite3

import pytest

from src.config import GENESIS_PREV_HASH
from src.audit import finalise_row_hash, verify_chain, log_gate_event
from src.database import init_db


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _insert(conn, plate="AA-1234", ts="2026-01-01T07:00:00Z",
            gate="MAIN_GATE", direction="ENTRY"):
    """Insert a PENDING row and finalise its hash; return row_id."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO access_log
           (plate_number, timestamp, gate_id, direction, status, row_hash)
           VALUES (?,?,?,?,'ON_TIME_ENTRY','PENDING')""",
        (plate, ts, gate, direction),
    )
    row_id = cur.lastrowid
    finalise_row_hash(conn, row_id)
    return row_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_01_empty_log_ok(db):
    result = verify_chain(db)
    assert result.ok is True
    assert result.rows_checked == 0
    assert result.first_bad_id is None


def test_02_single_row_ok(db):
    _insert(db)
    result = verify_chain(db)
    assert result.ok is True
    assert result.rows_checked == 1


def test_03_genesis_prev_hash(db):
    """First row's hash payload must use GENESIS_PREV_HASH as prev_hash."""
    row_id = _insert(db)
    row = db.execute(
        "SELECT plate_number, timestamp, gate_id, direction, row_hash "
        "FROM access_log WHERE id = ?", (row_id,)
    ).fetchone()
    payload = json.dumps(
        {
            "id":           row_id,
            "plate_number": row[0],
            "timestamp":    row[1],
            "gate_id":      row[2],
            "direction":    row[3],
            "prev_hash":    GENESIS_PREV_HASH,
        },
        sort_keys=True, separators=(",", ":"),
    )
    expected = hashlib.sha256(payload.encode()).hexdigest()
    assert row[4] == expected


def test_04_pk_in_payload(db):
    """The hash payload explicitly contains the row's PK (id field)."""
    row_id = _insert(db)
    row = db.execute(
        "SELECT plate_number, timestamp, gate_id, direction, row_hash "
        "FROM access_log WHERE id = ?", (row_id,)
    ).fetchone()
    # Build payload WITH id and verify it matches stored hash
    payload_with_id = json.dumps(
        {
            "id":           row_id,
            "plate_number": row[0],
            "timestamp":    row[1],
            "gate_id":      row[2],
            "direction":    row[3],
            "prev_hash":    GENESIS_PREV_HASH,
        },
        sort_keys=True, separators=(",", ":"),
    )
    # Build payload WITHOUT id and verify it does NOT match
    payload_without_id = json.dumps(
        {
            "plate_number": row[0],
            "timestamp":    row[1],
            "gate_id":      row[2],
            "direction":    row[3],
            "prev_hash":    GENESIS_PREV_HASH,
        },
        sort_keys=True, separators=(",", ":"),
    )
    assert row[4] == hashlib.sha256(payload_with_id.encode()).hexdigest()
    assert row[4] != hashlib.sha256(payload_without_id.encode()).hexdigest()


def test_05_tamper_interior_row(db):
    """Tamper field value on an interior row -> chain broken at that row."""
    id1 = _insert(db, ts="2026-01-01T07:00:00Z")
    id2 = _insert(db, ts="2026-01-01T08:00:00Z")
    id3 = _insert(db, ts="2026-01-01T09:00:00Z")
    # Tamper plate_number on id2
    db.execute("UPDATE access_log SET plate_number = 'TAMPERED' WHERE id = ?", (id2,))
    result = verify_chain(db)
    assert result.ok is False
    assert result.first_bad_id == id2


def test_06_tamper_first_row(db):
    id1 = _insert(db, ts="2026-01-01T07:00:00Z")
    _insert(db, ts="2026-01-01T08:00:00Z")
    db.execute("UPDATE access_log SET gate_id = 'EVIL_GATE' WHERE id = ?", (id1,))
    result = verify_chain(db)
    assert result.ok is False
    assert result.first_bad_id == id1


def test_07_tamper_last_row(db):
    _insert(db, ts="2026-01-01T07:00:00Z")
    id2 = _insert(db, ts="2026-01-01T08:00:00Z")
    db.execute("UPDATE access_log SET direction = 'EXIT' WHERE id = ?", (id2,))
    result = verify_chain(db)
    assert result.ok is False
    assert result.first_bad_id == id2


def test_08_row_deletion_flagged(db):
    """Delete an interior row -> chain broken at the next row."""
    _insert(db, ts="2026-01-01T07:00:00Z")
    id2 = _insert(db, ts="2026-01-01T08:00:00Z")
    id3 = _insert(db, ts="2026-01-01T09:00:00Z")
    # Remove id2 (simulates deletion attack)
    db.execute("DELETE FROM access_log WHERE id = ?", (id2,))
    result = verify_chain(db)
    assert result.ok is False
    # id3's prev_hash now points to id1's hash but id3's stored hash was
    # computed against id2's hash -> mismatch at id3
    assert result.first_bad_id == id3


def test_09_row_reordering_flagged(db):
    """Swap field values between two rows -> flagged (PK-in-payload defence).

    Even if an attacker swaps all non-PK fields between two rows, the hash
    payload contains the PK, so the recomputed hash won't match the stored
    one at whichever row now has mismatched PK/fields.
    """
    id1 = _insert(db, plate="AA-0001", ts="2026-01-01T07:00:00Z")
    id2 = _insert(db, plate="BB-0002", ts="2026-01-01T08:00:00Z")

    # Swap plate_number between the two rows
    db.execute("UPDATE access_log SET plate_number='BB-0002' WHERE id=?", (id1,))
    db.execute("UPDATE access_log SET plate_number='AA-0001' WHERE id=?", (id2,))

    result = verify_chain(db)
    assert result.ok is False  # PK-in-payload catches the reordering


def test_10_1000_row_chain_zero_false_positives(db):
    for i in range(1000):
        _insert(db, plate=f"TS-{i:04d}", ts=f"2026-01-01T{i % 24:02d}:00:00Z")
    result = verify_chain(db)
    assert result.ok is True
    assert result.rows_checked == 1000


def test_11_finalise_idempotent(db):
    """Calling finalise_row_hash twice on the same row gives the same hash."""
    row_id = _insert(db)
    h1 = db.execute(
        "SELECT row_hash FROM access_log WHERE id = ?", (row_id,)
    ).fetchone()[0]
    h2 = finalise_row_hash(db, row_id)
    # Note: calling finalise again re-reads prev_hash from prior row, so it
    # should produce the same hash because nothing changed.
    assert h1 == h2


def test_12_consecutive_hashes_differ(db):
    """Each row's hash is distinct from its predecessor."""
    ids = [_insert(db, ts=f"2026-01-0{i+1}T07:00:00Z") for i in range(5)]
    hashes = [
        db.execute("SELECT row_hash FROM access_log WHERE id=?", (i,)).fetchone()[0]
        for i in ids
    ]
    assert len(set(hashes)) == 5


def test_13_finalise_returns_hex64(db):
    row_id = _insert(db)
    # re-call to get return value
    h = finalise_row_hash(db, row_id)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_14_finalise_raises_for_missing_row(db):
    with pytest.raises(ValueError, match="not found"):
        finalise_row_hash(db, 99999)


def test_15_first_bad_id_correct(db):
    ids = [_insert(db, ts=f"2026-01-0{i+1}T07:00:00Z") for i in range(4)]
    # Tamper the third row
    db.execute("UPDATE access_log SET plate_number='X' WHERE id=?", (ids[2],))
    result = verify_chain(db)
    assert result.first_bad_id == ids[2]


def test_16_reason_contains_bad_id(db):
    row_id = _insert(db)
    db.execute("UPDATE access_log SET plate_number='X' WHERE id=?", (row_id,))
    result = verify_chain(db)
    assert str(row_id) in result.reason


def test_17_rows_checked_intact_chain(db):
    n = 7
    for i in range(n):
        _insert(db, ts=f"2026-01-0{i+1}T07:00:00Z")
    result = verify_chain(db)
    assert result.rows_checked == n


def test_18_same_input_same_hash_across_dbs(db):
    """Two fresh DBs with identical inserts produce identical hashes."""
    db2 = __import__("sqlite3").connect(":memory:")
    db2.row_factory = __import__("sqlite3").Row
    init_db(db2)

    id1a = _insert(db)
    id1b = _insert(db2)

    h_a = db.execute("SELECT row_hash FROM access_log WHERE id=?", (id1a,)).fetchone()[0]
    h_b = db2.execute("SELECT row_hash FROM access_log WHERE id=?", (id1b,)).fetchone()[0]
    assert h_a == h_b
    db2.close()


def test_19_status_not_in_payload(db):
    """Changing status field alone must NOT break the chain (status is not hashed)."""
    row_id = _insert(db)
    db.execute("UPDATE access_log SET status='LATE_ARRIVAL' WHERE id=?", (row_id,))
    result = verify_chain(db)
    assert result.ok is True


def test_20_log_gate_event_helper(db):
    """log_gate_event convenience function leaves a non-PENDING row_hash."""
    row_id = log_gate_event(
        db,
        plate_number="WP-CAB-1234",
        timestamp="2026-01-01T07:05:00Z",
        gate_id="MAIN_GATE",
        direction="ENTRY",
        status="ON_TIME_ENTRY",
    )
    row = db.execute(
        "SELECT row_hash FROM access_log WHERE id=?", (row_id,)
    ).fetchone()
    assert row is not None
    assert row[0] != "PENDING"
    assert len(row[0]) == 64
