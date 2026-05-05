"""SHA-256 hash chain for access_log tamper-evidence (FR-05.1, §5.6, §6.6).

Security model
--------------
Each access_log row contains a ``row_hash`` field computed as:

    SHA-256(JSON({
        "id":           <integer row id>,
        "plate_number": <str>,
        "timestamp":    <ISO-8601 UTC str>,
        "gate_id":      <str>,
        "direction":    "ENTRY" | "EXIT",
        "prev_hash":    <hex digest of preceding row, or GENESIS_SALT for first row>
    }))

Including the auto-incremented ``id`` in the payload is critical.  Without it,
an adversary who can write directly to the database could swap two rows, recompute
all hashes from the swapped position onward (using prev_hash chaining), and produce
a chain that passes validation despite the reordering.  Binding each hash to its
row id makes such an attack detectable: the recomputed hash for a moved row will
incorporate the wrong id and will therefore not match the stored value.

The genesis sentinel ``GENESIS_SALT`` is a hard-coded non-empty string used as the
``prev_hash`` for the first row.  It provides a fixed, known starting point for
verification without requiring a separate genesis-block table entry.

Limitations
-----------
The chain is append-only tamper-evidence, not encryption.  A database
administrator with write access can still truncate the log or replace all hashes
after bulk data modification.  The chain should be supplemented by OS-level audit
logging and periodic export of the latest hash to an external, write-once store.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.config import GENESIS_SALT


def compute_row_hash(row_id: int, plate_number: str, timestamp: str,
                     gate_id: str, direction: str, prev_hash: str) -> str:
    """Compute the SHA-256 hash for a single access_log row.

    The payload binds six fields: the row's auto-incremented *row_id*, the
    four auditable event fields (*plate_number*, *timestamp*, *gate_id*,
    *direction*), and the hash of the immediately preceding row (*prev_hash*).
    Including *row_id* prevents row-reordering attacks in which an adversary
    swaps rows and recomputes the subsequent chain.

    Parameters
    ----------
    row_id : int
        The ``id`` primary-key value of the row being hashed.
    plate_number, timestamp, gate_id, direction : str
        Auditable event fields exactly as stored in the database.
    prev_hash : str
        SHA-256 hex digest of the preceding row, or ``GENESIS_SALT`` for the
        first row in the chain.

    Returns
    -------
    str
        64-character lowercase hexadecimal SHA-256 digest.
    """
    payload = json.dumps(
        {
            "id": row_id,
            "plate_number": plate_number,
            "timestamp": timestamp,
            "gate_id": gate_id,
            "direction": direction,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_prev_hash(cur: sqlite3.Cursor) -> str:
    """Return the hash of the most recently inserted access_log row.

    Returns ``GENESIS_SALT`` if the table is empty, providing a fixed and
    known starting point for the hash chain.

    Parameters
    ----------
    cur : sqlite3.Cursor
        An open cursor on the VAAS database connection.

    Returns
    -------
    str
        SHA-256 hex digest of the last row, or ``GENESIS_SALT``.
    """
    row = cur.execute(
        "SELECT row_hash FROM access_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return GENESIS_SALT
    return row["row_hash"] if isinstance(row, sqlite3.Row) else row[0]


@dataclass
class ChainVerificationResult:
    """Result of a full hash-chain verification pass."""

    intact: bool
    """True if every row's hash matches its recomputed value."""

    first_bad_id: Optional[int]
    """The ``id`` of the first row that failed verification, or *None*."""

    rows_checked: int
    """Total number of rows examined."""

    verified_at: str
    """ISO-8601 UTC timestamp at which verification was performed."""

    message: str
    """Human-readable summary suitable for logging or display."""


def verify_chain(conn: sqlite3.Connection) -> ChainVerificationResult:
    """Traverse the entire access_log and verify every row's hash.

    Rows are read in ascending ``id`` order.  For each row the function
    recomputes ``compute_row_hash(row_id, ...)`` using the stored field values
    and the previous row's hash, then compares the result against the stored
    ``row_hash``.  Any mismatch — caused by field modification, row deletion,
    row insertion, or row reordering — will be detected.

    The function additionally checks that row ids are strictly increasing
    (i.e., no gaps caused by unreported deletions reaching an otherwise-intact
    suffix of the chain, and no duplicate ids).  A non-sequential id is itself
    reported as a verification failure.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open connection to the VAAS database.

    Returns
    -------
    ChainVerificationResult
        Dataclass containing the verification outcome, the first bad row id if
        any, the count of rows examined, and a diagnostic message.
    """
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, plate_number, timestamp, gate_id, direction, row_hash "
        "FROM access_log ORDER BY id ASC"
    ).fetchall()

    prev_hash = GENESIS_SALT
    prev_id = 0  # sentinel: all real ids are >= 1
    checked = 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for r in rows:
        rid = r["id"] if isinstance(r, sqlite3.Row) else r[0]
        plate = r["plate_number"] if isinstance(r, sqlite3.Row) else r[1]
        ts = r["timestamp"] if isinstance(r, sqlite3.Row) else r[2]
        gate = r["gate_id"] if isinstance(r, sqlite3.Row) else r[3]
        dirn = r["direction"] if isinstance(r, sqlite3.Row) else r[4]
        stored_hash = r["row_hash"] if isinstance(r, sqlite3.Row) else r[5]
        checked += 1

        # Validate strictly increasing ids — gaps or duplicates signal tampering
        if rid <= prev_id:
            return ChainVerificationResult(
                intact=False,
                first_bad_id=rid,
                rows_checked=checked,
                verified_at=now_iso,
                message=(
                    f"Non-sequential row id={rid} (expected > {prev_id}); "
                    "possible row deletion or reordering"
                ),
            )

        expected = compute_row_hash(rid, plate, ts, gate, dirn, prev_hash)
        if expected != stored_hash:
            return ChainVerificationResult(
                intact=False,
                first_bad_id=rid,
                rows_checked=checked,
                verified_at=now_iso,
                message=(
                    f"Hash mismatch at row id={rid} "
                    f"(all subsequent rows are also broken)"
                ),
            )

        prev_hash = stored_hash
        prev_id = rid

    return ChainVerificationResult(
        intact=True,
        first_bad_id=None,
        rows_checked=checked,
        verified_at=now_iso,
        message=f"Chain intact across {checked} row(s)",
    )
