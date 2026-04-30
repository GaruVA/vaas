"""SHA-256 hash chain for access_log tamper-evidence (FR-05.1, §5.6, §6.6)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.config import GENESIS_SALT


def compute_row_hash(plate_number: str, timestamp: str, gate_id: str,
                     direction: str, prev_hash: str) -> str:
    payload = json.dumps({
        "plate_number": plate_number,
        "timestamp": timestamp,
        "gate_id": gate_id,
        "direction": direction,
        "prev_hash": prev_hash,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_prev_hash(cur: sqlite3.Cursor) -> str:
    row = cur.execute(
        "SELECT row_hash FROM access_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return GENESIS_SALT
    return row["row_hash"] if isinstance(row, sqlite3.Row) else row[0]


@dataclass
class ChainVerificationResult:
    intact: bool
    first_bad_id: Optional[int]
    rows_checked: int
    verified_at: str
    message: str


def verify_chain(conn: sqlite3.Connection) -> ChainVerificationResult:
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, plate_number, timestamp, gate_id, direction, row_hash "
        "FROM access_log ORDER BY id ASC"
    ).fetchall()
    prev = GENESIS_SALT
    checked = 0
    for r in rows:
        checked += 1
        expected = compute_row_hash(
            r["plate_number"], r["timestamp"], r["gate_id"], r["direction"], prev
        )
        if expected != r["row_hash"]:
            return ChainVerificationResult(
                intact=False,
                first_bad_id=r["id"],
                rows_checked=checked,
                verified_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                message=f"Mismatch at row id={r['id']} (all subsequent rows are also broken)",
            )
        prev = r["row_hash"]
    return ChainVerificationResult(
        intact=True,
        first_bad_id=None,
        rows_checked=checked,
        verified_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        message=f"Chain intact across {checked} rows",
    )
