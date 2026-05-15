from __future__ import annotations

"""Shift-aware attendance engine for VAAS.

Classifies each gate event into one of 13 statuses based on:
- Vehicle registration status (ACTIVE / SUSPENDED / EXPIRED)
- Whether the vehicle has a shift assignment
- Current time vs shift start/end + grace period
- Direction (ENTRY vs EXIT)
- Previous entry for dwell-time / overstay calculation

All 13 status values
---------------------
ON_TIME_ENTRY, LATE_ARRIVAL, EARLY_ARRIVAL,
ON_TIME_EXIT, EARLY_DEPARTURE, OVERSTAY,
VISITOR, VISITOR_ADMITTED, VISITOR_REJECTED,
VISITOR_PENDING_REGISTRATION, VISITOR_TIMEOUT_REJECT,
SUSPENDED, EXPIRED.

Midnight boundary
-----------------
If ``shift.start_time >= shift.end_time`` the shift crosses midnight.
``end_dt`` is set to ``start_dt + timedelta(days=1) + (end_time - start_time)``.

Grace period
------------
Read at runtime from ``shifts.grace_period_minutes``.  No hardcoded value
anywhere in this module.

References: section 6.5 of BUILD_SPEC.md
"""

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Literal, Optional

from src.audit import finalise_row_hash
from src.barrier import BarrierController
from src.config import (
    EXCEPTION_TIMEOUT_SECONDS,
    LOW_CONF_GATE_THRESHOLD,
    OVERSTAY_THRESHOLD_MINUTES,
)
from src.database import transaction
from src.lpm_mled import lpm_mled_correct

logger = logging.getLogger(__name__)

_VALID_PLATE_RE = re.compile(
    r"^(?:[A-Z]{3}-\d{4}|[A-Z]{2}-\d{4}|[A-Z]{2}-[A-Z]{3}-\d{4}|[A-Z]{2}-[A-Z]{2}-\d{4})$"
)

def _now() -> datetime:
    return datetime.now(timezone.utc)

class GateStatus(str, Enum):
    ON_TIME_ENTRY                  = "ON_TIME_ENTRY"
    LATE_ARRIVAL                   = "LATE_ARRIVAL"
    EARLY_ARRIVAL                  = "EARLY_ARRIVAL"
    ON_TIME_EXIT                   = "ON_TIME_EXIT"
    EARLY_DEPARTURE                = "EARLY_DEPARTURE"
    OVERSTAY                       = "OVERSTAY"
    VISITOR                        = "VISITOR"
    VISITOR_ADMITTED               = "VISITOR_ADMITTED"
    VISITOR_REJECTED               = "VISITOR_REJECTED"
    VISITOR_PENDING_REGISTRATION   = "VISITOR_PENDING_REGISTRATION"
    VISITOR_TIMEOUT_REJECT         = "VISITOR_TIMEOUT_REJECT"
    SUSPENDED                      = "SUSPENDED"
    EXPIRED                        = "EXPIRED"
    DOUBLE_ENTRY                   = "DOUBLE_ENTRY"
    UNMATCHED_EXIT                 = "UNMATCHED_EXIT"

class GateOutcome(str, Enum):
    BARRIER_OPENED              = "BARRIER_OPENED"
    BARRIER_CLOSED_REJECTED     = "BARRIER_CLOSED_REJECTED"
    EXCEPTION_PENDING_DISPOSITION = "EXCEPTION_PENDING_DISPOSITION"

@dataclass
class GateEventResult:
    outcome:       GateOutcome
    status:        GateStatus
    plate_number:  str | None
    access_log_id: int | None
    message:       str = ""

class AttendanceEngine:
    """Processes gate events and determines attendance status.

    Parameters
    ----------
    conn:
        Open SQLite connection.
    barrier:
        :class:`~src.barrier.BarrierController` instance.
    sse_callback:
        Optional callable(event_type: str, data: dict) for SSE push.
    exception_timeout:
        Seconds before an unresolved visitor exception auto-rejects.
    """

    def __init__(
        self,
        conn,
        barrier: BarrierController,
        sse_callback=None,
        exception_timeout: int = EXCEPTION_TIMEOUT_SECONDS,
        confidence_threshold: float = LOW_CONF_GATE_THRESHOLD,
    ) -> None:
        self._conn          = conn
        self._barrier       = barrier
        self._sse           = sse_callback
        self._timeout       = exception_timeout
        self._conf_threshold = confidence_threshold
        self._pending_timers: dict[int, threading.Timer] = {}

    def process_gate_event(
        self,
        raw_plate: str,
        confidence: float,
        gate_id: str,
        direction: Literal["ENTRY", "EXIT"],
        plate_crop_jpeg_bytes: bytes,
        timestamp: datetime | None = None,
    ) -> GateEventResult:
        """Process one gate event and return the outcome.

        Parameters
        ----------
        raw_plate:
            Raw OCR string from the classifier.
        confidence:
            Classifier confidence score (0–1).
        gate_id:
            Gate identifier (e.g. ``"MAIN_GATE"``).
        direction:
            ``"ENTRY"`` or ``"EXIT"``.
        plate_crop_jpeg_bytes:
            JPEG bytes of the plate crop (stored in DB, may be empty).
        timestamp:
            Event time; defaults to ``utcnow()``.
        """
        import base64
        now = timestamp or _now()
        ts_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        crop_b64 = base64.b64encode(plate_crop_jpeg_bytes).decode() if plate_crop_jpeg_bytes else None

        raw_plate = raw_plate.strip().upper()
        if len(raw_plate) < 4:
            logger.debug("[%s] Discarding sub-4-char read '%s' (conf=%.2f)", gate_id, raw_plate, confidence)
            return GateEventResult(
                outcome=GateOutcome.BARRIER_CLOSED_REJECTED,
                status=GateStatus.VISITOR,
                plate_number=None,
                access_log_id=None,
                message="Read too short — discarded",
            )

        candidates = [
            r[0] for r in self._conn.execute(
                "SELECT plate_number FROM registered_vehicles"
            ).fetchall()
        ]
        matched_plate = lpm_mled_correct(raw_plate, candidates)

        if matched_plate is None:

            if not _VALID_PLATE_RE.match(raw_plate):
                logger.debug("[%s] Discarding invalid-format plate '%s' (conf=%.2f)", gate_id, raw_plate, confidence)
                return GateEventResult(
                    outcome=GateOutcome.BARRIER_CLOSED_REJECTED,
                    status=GateStatus.VISITOR,
                    plate_number=None,
                    access_log_id=None,
                    message="Invalid plate format — discarded",
                )

            return self._handle_visitor(raw_plate, confidence, gate_id, direction, ts_str, crop_b64)

        if confidence < self._conf_threshold:
            return self._handle_visitor(matched_plate, confidence, gate_id, direction, ts_str, crop_b64)

        vehicle = self._conn.execute(
            "SELECT registration_status FROM registered_vehicles WHERE plate_number = ?",
            (matched_plate,),
        ).fetchone()

        reg_status = vehicle[0] if vehicle else "UNKNOWN"

        if reg_status == "SUSPENDED":
            self._write_rejection(matched_plate, ts_str, gate_id, "SUSPENDED", confidence, crop_b64)
            return GateEventResult(
                outcome=GateOutcome.BARRIER_CLOSED_REJECTED,
                status=GateStatus.SUSPENDED,
                plate_number=matched_plate,
                access_log_id=None,
                message="Vehicle suspended",
            )

        if reg_status == "EXPIRED":
            self._write_rejection(matched_plate, ts_str, gate_id, "EXPIRED", confidence, crop_b64)
            return GateEventResult(
                outcome=GateOutcome.BARRIER_CLOSED_REJECTED,
                status=GateStatus.EXPIRED,
                plate_number=matched_plate,
                access_log_id=None,
                message="Vehicle registration expired",
            )

        last_dir_row = self._conn.execute(
            "SELECT direction FROM access_log "
            "WHERE plate_number = ? ORDER BY id DESC LIMIT 1",
            (matched_plate,),
        ).fetchone()
        last_dir = last_dir_row[0] if last_dir_row else None

        anomaly_status: GateStatus | None = None
        if direction == "ENTRY" and last_dir == "ENTRY":
            anomaly_status = GateStatus.DOUBLE_ENTRY
            logger.warning("[%s] Double-entry anomaly: %s — last recorded event was also ENTRY",
                           gate_id, matched_plate)
        elif direction == "EXIT" and last_dir != "ENTRY":
            anomaly_status = GateStatus.UNMATCHED_EXIT
            logger.warning("[%s] Unmatched-exit anomaly: %s — no prior ENTRY found (last=%s)",
                           gate_id, matched_plate, last_dir)

        if anomaly_status is not None:

            try:
                _sr = self._conn.execute(
                    """SELECT s.shift_id FROM shifts s
                       JOIN vehicle_shifts vs ON vs.shift_id = s.shift_id
                       WHERE vs.plate_number = ? LIMIT 1""",
                    (matched_plate,),
                ).fetchone()
                _shift_id = _sr[0] if _sr else None
            except Exception:
                _shift_id = None

            zone_id, project_code = self._resolve_attribution(matched_plate, gate_id, now)
            row_id = self._insert_access_log(
                matched_plate, ts_str, gate_id, direction,
                anomaly_status.value, _shift_id, confidence,
                None, zone_id, project_code, crop_b64,
            )
            self._barrier.open(gate_id)
            return GateEventResult(
                outcome=GateOutcome.BARRIER_OPENED,
                status=anomaly_status,
                plate_number=matched_plate,
                access_log_id=row_id,
                message=anomaly_status.value,
            )

        shift_row = self._conn.execute(
            """SELECT s.shift_id, s.start_time, s.end_time, s.grace_period_minutes
               FROM shifts s
               JOIN vehicle_shifts vs ON vs.shift_id = s.shift_id
               WHERE vs.plate_number = ?
               LIMIT 1""",
            (matched_plate,),
        ).fetchone()

        attendance_status = self._classify_status(direction, now, shift_row)

        dwell = None
        if direction == "EXIT":
            entry_row = self._conn.execute(
                """SELECT timestamp FROM access_log
                   WHERE plate_number = ? AND direction = 'ENTRY'
                   ORDER BY id DESC LIMIT 1""",
                (matched_plate,),
            ).fetchone()
            if entry_row:
                try:
                    entry_dt = datetime.fromisoformat(entry_row[0].replace("Z", "+00:00"))
                    dwell = (now - entry_dt).total_seconds()
                except (ValueError, TypeError):
                    pass

        zone_id, project_code = self._resolve_attribution(matched_plate, gate_id, now)

        shift_id = shift_row[0] if shift_row else None
        row_id = self._insert_access_log(
            matched_plate, ts_str, gate_id, direction,
            attendance_status.value, shift_id, confidence,
            dwell, zone_id, project_code, crop_b64,
        )

        self._barrier.open(gate_id)

        return GateEventResult(
            outcome=GateOutcome.BARRIER_OPENED,
            status=attendance_status,
            plate_number=matched_plate,
            access_log_id=row_id,
        )

    def dispose_exception(
        self,
        access_log_id: int,
        disposition: Literal["ADMIT", "REJECT", "REGISTER"],
        operator_user_id: int,
    ) -> None:
        """Handle operator disposition of a visitor exception.

        ADMIT   -> status VISITOR_ADMITTED, open barrier.
        REJECT  -> status VISITOR_REJECTED, write gate_rejections row.
        REGISTER -> status VISITOR_PENDING_REGISTRATION.
        """

        timer = self._pending_timers.pop(access_log_id, None)
        if timer:
            timer.cancel()

        row = self._conn.execute(
            "SELECT plate_number, gate_id, timestamp FROM access_log WHERE id = ?",
            (access_log_id,),
        ).fetchone()
        if row is None:
            logger.warning("dispose_exception: row %d not found", access_log_id)
            return
        plate, gate_id, ts = row[0], row[1], row[2]

        if disposition == "ADMIT":
            self._conn.execute(
                "UPDATE access_log SET status = ? WHERE id = ?",
                (GateStatus.VISITOR_ADMITTED.value, access_log_id),
            )
            self._barrier.open(gate_id)

        elif disposition == "REJECT":
            self._conn.execute(
                "UPDATE access_log SET status = ? WHERE id = ?",
                (GateStatus.VISITOR_REJECTED.value, access_log_id),
            )
            self._write_rejection(plate, ts, gate_id, "VISITOR_REJECTED", None, None)

        elif disposition == "REGISTER":
            self._conn.execute(
                "UPDATE access_log SET status = ? WHERE id = ?",
                (GateStatus.VISITOR_PENDING_REGISTRATION.value, access_log_id),
            )

        logger.info(
            "Exception %d disposed: %s by operator %d",
            access_log_id, disposition, operator_user_id,
        )

    def _classify_visitor_anomaly(
        self, raw_plate: str, gate_id: str, direction: str, ts_str: str
    ) -> "GateStatus":
        """Return the appropriate status for an unregistered-plate event.

        Detects two patterns that the registered-plate path already handles
        but visitor plates previously bypassed:

        1. Direction inconsistency — ENTRY after ENTRY (double-entry) or
           EXIT without a prior ENTRY on record (unmatched exit).
        2. Rapid cross-gate retry — the same plate triggered an exception
           or was rejected at *any* gate within the last 5 minutes.
           A debouncer only covers a single gate; this closes the gap.
        """
        last_row = self._conn.execute(
            "SELECT direction FROM access_log "
            "WHERE plate_number = ? ORDER BY id DESC LIMIT 1",
            (raw_plate,),
        ).fetchone()
        last_dir = last_row[0] if last_row else None

        if direction == "ENTRY" and last_dir == "ENTRY":
            logger.warning("[%s] Visitor double-entry: %s", gate_id, raw_plate)
            return GateStatus.DOUBLE_ENTRY

        if direction == "EXIT" and last_dir is not None and last_dir != "ENTRY":
            logger.warning("[%s] Visitor unmatched-exit: %s (last=%s)",
                           gate_id, raw_plate, last_dir)
            return GateStatus.UNMATCHED_EXIT

        recent = self._conn.execute(
            "SELECT 1 FROM access_log "
            "WHERE plate_number = ? "
            "  AND status IN ('VISITOR','VISITOR_TIMEOUT_REJECT','VISITOR_REJECTED') "
            "  AND datetime(timestamp) >= datetime(?, '-5 minutes') "
            "LIMIT 1",
            (raw_plate, ts_str),
        ).fetchone()
        if not recent:
            recent = self._conn.execute(
                "SELECT 1 FROM gate_rejections "
                "WHERE plate_number = ? "
                "  AND datetime(timestamp) >= datetime(?, '-5 minutes') "
                "LIMIT 1",
                (raw_plate, ts_str),
            ).fetchone()
        if recent:
            logger.warning("[%s] Rapid cross-gate retry after recent exception: %s",
                           gate_id, raw_plate)
            return GateStatus.DOUBLE_ENTRY

        return GateStatus.VISITOR

    def _handle_visitor(
        self, raw_plate, confidence, gate_id, direction, ts_str, crop_b64
    ) -> GateEventResult:
        """Insert VISITOR row and schedule auto-reject timeout."""
        visitor_status = self._classify_visitor_anomaly(raw_plate, gate_id, direction, ts_str)
        row_id = self._insert_access_log(
            raw_plate, ts_str, gate_id, direction,
            visitor_status.value, None, confidence,
            None, None, None, crop_b64,
        )
        if self._sse:
            self._sse("exception", {
                "id":         row_id,
                "raw_plate":  raw_plate,
                "gate_id":    gate_id,
                "confidence": confidence,
                "timestamp":  ts_str,
            })

        timer = threading.Timer(
            self._timeout,
            self._auto_reject,
            args=(row_id,),
        )
        timer.daemon = True
        timer.start()
        self._pending_timers[row_id] = timer

        return GateEventResult(
            outcome=GateOutcome.EXCEPTION_PENDING_DISPOSITION,
            status=visitor_status,
            plate_number=raw_plate,
            access_log_id=row_id,
        )

    def _auto_reject(self, access_log_id: int) -> None:
        """Called by threading.Timer after timeout -- auto-reject visitor."""
        self._pending_timers.pop(access_log_id, None)
        row = self._conn.execute(
            "SELECT gate_id FROM access_log WHERE id = ?", (access_log_id,)
        ).fetchone()
        self._conn.execute(
            "UPDATE access_log SET status = ? WHERE id = ?",
            (GateStatus.VISITOR_TIMEOUT_REJECT.value, access_log_id),
        )
        logger.info("Visitor exception %d auto-rejected (timeout)", access_log_id)
        if self._sse and row:
            self._sse("exception_timeout", {
                "id":      access_log_id,
                "gate_id": row[0],
            })

    def _classify_status(
        self,
        direction: str,
        now: datetime,
        shift_row,
    ) -> GateStatus:
        """Return attendance status for an ACTIVE vehicle."""
        if shift_row is None:

            if direction == "ENTRY":
                return GateStatus.VISITOR_ADMITTED
            return GateStatus.ON_TIME_EXIT

        shift_id, start_str, end_str, grace_minutes = (
            shift_row[0], shift_row[1], shift_row[2], shift_row[3]
        )

        start_h, start_m = (int(x) for x in start_str.split(":"))
        end_h,   end_m   = (int(x) for x in end_str.split(":"))
        grace = timedelta(minutes=grace_minutes)

        event_date = now.date()
        start_dt = datetime(
            event_date.year, event_date.month, event_date.day,
            start_h, start_m, tzinfo=timezone.utc,
        )
        end_dt = datetime(
            event_date.year, event_date.month, event_date.day,
            end_h, end_m, tzinfo=timezone.utc,
        )

        crosses_midnight = (start_h * 60 + start_m) >= (end_h * 60 + end_m)
        if crosses_midnight:
            end_dt += timedelta(days=1)

            if now < start_dt:
                start_dt -= timedelta(days=1)
                end_dt   -= timedelta(days=1)

        if direction == "ENTRY":
            if now < start_dt:
                return GateStatus.EARLY_ARRIVAL
            elif now <= start_dt + grace:
                return GateStatus.ON_TIME_ENTRY
            else:
                return GateStatus.LATE_ARRIVAL

        else:
            if now < end_dt:
                return GateStatus.EARLY_DEPARTURE
            elif now <= end_dt + grace:
                return GateStatus.ON_TIME_EXIT
            else:
                return GateStatus.OVERSTAY

    def _resolve_attribution(self, plate, gate_id, now):
        """Resolve zone_id and project_code for this event."""
        try:
            from src.projects import resolve_event_attribution
            return resolve_event_attribution(self._conn, plate, gate_id, now.isoformat())
        except Exception:
            return (None, None)

    def _insert_access_log(
        self, plate, ts, gate_id, direction, status,
        shift_id, confidence, dwell, zone_id, project_code, crop_b64
    ) -> int:
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO access_log
               (plate_number, timestamp, gate_id, direction, status,
                shift_id, confidence_score, dwell_time_seconds,
                zone_id, project_code, plate_crop_b64, row_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,'PENDING')""",
            (plate, ts, gate_id, direction, status,
             shift_id, confidence, dwell,
             zone_id, project_code, crop_b64),
        )
        row_id = cur.lastrowid
        finalise_row_hash(self._conn, row_id)
        return row_id

    def _write_rejection(self, plate, ts, gate_id, reason, confidence, crop_b64):
        self._conn.execute(
            """INSERT INTO gate_rejections
               (plate_number, timestamp, gate_id, reason, confidence_score, plate_crop_b64)
               VALUES (?,?,?,?,?,?)""",
            (plate, ts, gate_id, reason, confidence, crop_b64),
        )

    def _flag_overstay(self, row_id: int, plate: str, window_start: str, window_end: str) -> None:
        """Idempotent overstay flag using double NOT EXISTS subquery."""
        self._conn.execute(
            """UPDATE access_log SET status = 'OVERSTAY'
               WHERE id = ?
                 AND NOT EXISTS (
                   SELECT 1 FROM access_log
                   WHERE plate_number = ? AND status = 'OVERSTAY'
                     AND timestamp BETWEEN ? AND ?
                 )
                 AND NOT EXISTS (
                   SELECT 1 FROM access_log
                   WHERE id = ? AND status = 'OVERSTAY'
                 )""",
            (row_id, plate, window_start, window_end, row_id),
        )
