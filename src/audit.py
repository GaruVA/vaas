from __future__ import annotations

"""SHA-256 hash-chained audit log for VAAS access_log table.

Two-step INSERT / UPDATE pattern
---------------------------------
1. Insert the row with ``row_hash = 'PENDING'`` to obtain the auto-assigned PK.
2. Compute SHA-256 over the JSON payload ``{id, plate_number, timestamp,
   gate_id, direction, prev_hash}`` (sorted keys, compact separators).
3. UPDATE the row with the real hash.

Including the PK in the payload defeats row-reordering attacks: if two rows
are swapped, the hash chain will be broken at the first swapped row because
the recomputed hash will embed the *original* PK, not the swapped position.

References: section 6.6 of BUILD_SPEC.md
"""

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.config import GENESIS_PREV_HASH

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Two-step hash finalisation
# ---------------------------------------------------------------------------

def finalise_row_hash(conn: sqlite3.Connection, row_id: int) -> str:
    """Compute and commit the SHA-256 hash for an ``access_log`` row.

    Must be called after the INSERT that created the row.  The row must
    already have ``row_hash = 'PENDING'``.

    Parameters
    ----------
    conn:
        Open database connection (autocommit or inside a transaction).
    row_id:
        The ``access_log.id`` of the newly inserted row.

    Returns
    -------
    str
        The computed hex digest, also written to ``access_log.row_hash``.
    """
    cur = conn.cursor()

    # Fetch the fields that go into the payload
    cur.execute(
        "SELECT plate_number, timestamp, gate_id, direction "
        "FROM access_log WHERE id = ?",
        (row_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"access_log row {row_id} not found")
    plate, ts, gate, direction = row[0], row[1], row[2], row[3]

    # Previous row hash (genesis constant for the first row)
    cur.execute(
        "SELECT row_hash FROM access_log WHERE id < ? ORDER BY id DESC LIMIT 1",
        (row_id,),
    )
    prev_row = cur.fetchone()
    prev_hash: str = prev_row[0] if prev_row else GENESIS_PREV_HASH

    # Build deterministic JSON payload
    payload = json.dumps(
        {
            "id":           row_id,
            "plate_number": plate,
            "timestamp":    ts,
            "gate_id":      gate,
            "direction":    direction,
            "prev_hash":    prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    cur.execute(
        "UPDATE access_log SET row_hash = ? WHERE id = ?",
        (h, row_id),
    )
    logger.debug("Finalised hash for row %d: %s", row_id, h[:16] + "...")
    return h


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------

@dataclass
class ChainVerificationResult:
    """Result returned by :func:`verify_chain`."""

    ok: bool
    first_bad_id: int | None
    reason: str | None
    verified_at: str
    rows_checked: int


def verify_chain(conn: sqlite3.Connection) -> ChainVerificationResult:
    """Walk the entire ``access_log`` and verify SHA-256 chain integrity.

    Returns
    -------
    ChainVerificationResult
        ``.ok`` is ``True`` only when every row's stored hash matches the
        recomputed hash.  On failure, ``.first_bad_id`` identifies the
        first offending row.
    """
    verified_at = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, plate_number, timestamp, gate_id, direction, row_hash "
        "FROM access_log ORDER BY id"
    )
    rows = cur.fetchall()

    if not rows:
        return ChainVerificationResult(
            ok=True,
            first_bad_id=None,
            reason=None,
            verified_at=verified_at,
            rows_checked=0,
        )

    prev_hash = GENESIS_PREV_HASH

    for i, row in enumerate(rows):
        row_id, plate, ts, gate, direction, stored_hash = (
            row[0], row[1], row[2], row[3], row[4], row[5]
        )

        # Detect gaps (deleted rows) by checking id continuity against prev
        if i > 0:
            prev_id = rows[i - 1][0]
            # gap check is implicit: the prev_hash used in the payload
            # was computed from the *previous stored hash*, so a deleted row
            # will cause a mismatch at the next row automatically.

        payload = json.dumps(
            {
                "id":           row_id,
                "plate_number": plate,
                "timestamp":    ts,
                "gate_id":      gate,
                "direction":    direction,
                "prev_hash":    prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        if stored_hash != expected:
            return ChainVerificationResult(
                ok=False,
                first_bad_id=row_id,
                reason=(
                    f"Hash mismatch at id={row_id}: "
                    f"stored={stored_hash[:16]}... "
                    f"expected={expected[:16]}..."
                ),
                verified_at=verified_at,
                rows_checked=i + 1,
            )

        prev_hash = stored_hash

    return ChainVerificationResult(
        ok=True,
        first_bad_id=None,
        reason=None,
        verified_at=verified_at,
        rows_checked=len(rows),
    )


# ---------------------------------------------------------------------------
# Convenience: insert + finalise in one call
# ---------------------------------------------------------------------------

def log_gate_event(
    conn: sqlite3.Connection,
    plate_number: str,
    timestamp: str,
    gate_id: str,
    direction: str,
    *,
    status: str = "UNKNOWN",
    shift_id: str | None = None,
    confidence_score: float | None = None,
    dwell_time_seconds: float | None = None,
    zone_id: str | None = None,
    project_code: str | None = None,
    plate_crop_b64: str | None = None,
) -> int:
    """Insert an ``access_log`` row and finalise its hash chain link.

    Returns the new row id.
    """
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO access_log
           (plate_number, timestamp, gate_id, direction,
            status, shift_id, confidence_score, dwell_time_seconds,
            zone_id, project_code, plate_crop_b64,
            row_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,'PENDING')""",
        (
            plate_number, timestamp, gate_id, direction,
            status, shift_id, confidence_score, dwell_time_seconds,
            zone_id, project_code, plate_crop_b64,
        ),
    )
    row_id = cur.lastrowid
    finalise_row_hash(conn, row_id)
    return row_id
