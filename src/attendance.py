"""Shift-aware attendance engine (FR-02, §5.4, §6.4)."""
from __future__ import annotations

import base64
import json
import logging
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Callable, Literal, Optional

from src.audit import compute_row_hash, get_prev_hash
from src.config import (
    EXCEPTION_TIMEOUT_SECONDS,
    OVERSTAY_CHECK_INTERVAL_S,
)
from src.database import transaction
from src.lpm_mled import lpm_mled_correct

logger = logging.getLogger(__name__)


Direction = Literal["ENTRY", "EXIT"]
Outcome = Literal[
    "BARRIER_OPENED",
    "BARRIER_CLOSED_REJECTED",
    "EXCEPTION_PENDING_DISPOSITION",
]
Disposition = Literal["ADMIT", "REJECT", "REGISTER"]
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

# Input validation constants (FR-01, §5.3)
_MAX_PLATE_LENGTH = 20                        # Sri Lankan plates: max 10 chars + separators
_VALID_PLATE_RE = re.compile(r'^[A-Z0-9\- ]{1,20}$', re.IGNORECASE)
_VALID_DIRECTIONS: frozenset[str] = frozenset({"ENTRY", "EXIT"})


@dataclass
class GateEventResult:
    outcome: Outcome
    matched_plate: Optional[str]
    status: str
    access_log_id: Optional[int]
    dwell_time_seconds: Optional[float]
    confidence: float = 0.0
    raw_plate: str = ""


@dataclass
class _PendingException:
    access_log_id: int
    timer: threading.Timer
    gate_id: str


def _utc_iso(ts: Optional[datetime] = None) -> str:
    if ts is None:
        ts = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


class AttendanceEngine:
    def __init__(self, conn: sqlite3.Connection,
                 barrier=None,
                 sse_publish: Optional[Callable[[dict], None]] = None,
                 exception_timeout_seconds: int = EXCEPTION_TIMEOUT_SECONDS):
        self.conn = conn
        self.barrier = barrier
        self.sse_publish = sse_publish or (lambda evt: None)
        self.exception_timeout_seconds = exception_timeout_seconds
        self._pending: dict[int, _PendingException] = {}
        self._pending_lock = threading.Lock()
        self._overstay_thread: Optional[threading.Thread] = None
        self._overstay_stop = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process_gate_event(self,
                           raw_plate: str,
                           confidence: float,
                           gate_id: str,
                           direction: Direction,
                           plate_crop_jpeg_bytes: bytes,
                           timestamp: Optional[datetime] = None) -> GateEventResult:
        # ── Input validation (§5.3, FR-01) ──────────────────────────────────
        if not isinstance(raw_plate, str):
            raise TypeError(f"raw_plate must be str, got {type(raw_plate).__name__}")
        raw_plate = raw_plate.strip()
        if len(raw_plate) > _MAX_PLATE_LENGTH:
            raise ValueError(
                f"raw_plate exceeds maximum length of {_MAX_PLATE_LENGTH} "
                f"characters: {raw_plate!r}"
            )
        if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
            raise ValueError(
                f"confidence must be a float in [0.0, 1.0], got {confidence!r}"
            )
        confidence = float(confidence)
        if not gate_id or not isinstance(gate_id, str) or not gate_id.strip():
            raise ValueError(
                f"gate_id must be a non-empty string, got {gate_id!r}"
            )
        gate_id = gate_id.strip()
        if direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"direction must be 'ENTRY' or 'EXIT', got {direction!r}"
            )
        # ── End validation ───────────────────────────────────────────────────
        ts = timestamp or datetime.now(timezone.utc)
        ts_iso = _utc_iso(ts)
        crop_b64 = base64.b64encode(plate_crop_jpeg_bytes).decode("ascii") if plate_crop_jpeg_bytes else None

        candidates = self._registered_plates()
        matched = lpm_mled_correct(raw_plate, candidates) if candidates else None

        if matched is None:
            return self._handle_visitor(raw_plate, confidence, gate_id, direction,
                                        ts_iso, crop_b64)

        veh = self._get_vehicle(matched)
        status_reg = veh["registration_status"] if veh else "ACTIVE"
        if status_reg in ("SUSPENDED", "EXPIRED"):
            return self._handle_rejected(matched, confidence, gate_id, ts_iso, status_reg)

        # ACTIVE vehicle path
        shift_id, compliance = self._evaluate_shift(matched, gate_id, direction, ts)
        dwell: Optional[float] = None
        if direction == "EXIT":
            dwell = self._compute_dwell(matched, ts)

        log_id = self._insert_access_log(
            plate_number=matched,
            timestamp=ts_iso,
            gate_id=gate_id,
            direction=direction,
            dwell=dwell,
            shift_id=shift_id,
            confidence=confidence,
            status=compliance,
            crop_b64=crop_b64,
        )

        if self.barrier:
            try:
                self.barrier.open(gate_id)
            except Exception as exc:
                logger.error("Barrier open failed: %s", exc)

        result = GateEventResult(
            outcome="BARRIER_OPENED",
            matched_plate=matched,
            status=compliance,
            access_log_id=log_id,
            dwell_time_seconds=dwell,
            confidence=confidence,
            raw_plate=raw_plate,
        )
        self.sse_publish({
            "type": "gate_event",
            "id": log_id,
            "plate": matched,
            "gate": gate_id,
            "direction": direction,
            "status": compliance,
            "timestamp": ts_iso,
            "confidence": confidence,
            "dwell_time_seconds": dwell,
        })
        return result

    def dispose_exception(self, access_log_id: int,
                          disposition: Disposition,
                          operator_user_id: Optional[int] = None) -> str:
        with self._pending_lock:
            entry = self._pending.pop(access_log_id, None)
        if entry is not None:
            entry.timer.cancel()

        if disposition == "ADMIT":
            new_status = "VISITOR_ADMITTED"
        elif disposition == "REJECT":
            new_status = "VISITOR_REJECTED"
        elif disposition == "REGISTER":
            new_status = "VISITOR_PENDING_REGISTRATION"
        else:
            raise ValueError(f"Unknown disposition: {disposition}")

        with transaction(self.conn) as cur:
            cur.execute(
                "UPDATE access_log SET status = ? WHERE id = ?",
                (new_status, access_log_id),
            )

        gate_id = None
        if entry is not None:
            gate_id = entry.gate_id
        else:
            row = self.conn.execute(
                "SELECT gate_id FROM access_log WHERE id = ?", (access_log_id,)
            ).fetchone()
            if row:
                gate_id = row["gate_id"]

        if disposition == "ADMIT" and self.barrier and gate_id:
            try:
                self.barrier.open(gate_id)
            except Exception as exc:
                logger.error("Barrier open on admit failed: %s", exc)

        if disposition == "REJECT" and gate_id:
            with transaction(self.conn) as cur:
                row = cur.execute(
                    "SELECT plate_number, confidence_score FROM access_log WHERE id=?",
                    (access_log_id,),
                ).fetchone()
                cur.execute(
                    "INSERT INTO gate_rejections (plate_number,timestamp,gate_id,reason,confidence_score) "
                    "VALUES (?,?,?,?,?)",
                    (row["plate_number"], _utc_iso(), gate_id, "VISITOR_REJECTED",
                     row["confidence_score"] if row else None),
                )

        self.sse_publish({
            "type": "exception_disposed",
            "id": access_log_id,
            "disposition": disposition,
            "status": new_status,
        })
        return new_status

    def start_overstay_monitor(self) -> None:
        if self._overstay_thread is not None:
            return
        self._overstay_stop.clear()
        self._overstay_thread = threading.Thread(target=self._overstay_loop, daemon=True)
        self._overstay_thread.start()

    def stop_overstay_monitor(self) -> None:
        self._overstay_stop.set()
        if self._overstay_thread:
            self._overstay_thread.join(timeout=2)
            self._overstay_thread = None

    def shutdown(self) -> None:
        self.stop_overstay_monitor()
        with self._pending_lock:
            for p in self._pending.values():
                p.timer.cancel()
            self._pending.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _registered_plates(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT plate_number FROM registered_vehicles"
        ).fetchall()
        return [r["plate_number"] for r in rows]

    def _get_vehicle(self, plate: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM registered_vehicles WHERE plate_number = ?", (plate,)
        ).fetchone()

    def _vehicle_shifts(self, plate: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT s.* FROM shifts s "
            "JOIN vehicle_shifts vs ON vs.shift_id = s.shift_id "
            "WHERE vs.plate_number = ?",
            (plate,),
        ).fetchall()

    def _evaluate_shift(self, plate: str, gate_id: str,
                        direction: Direction,
                        ts: datetime) -> tuple[Optional[str], str]:
        shifts = self._vehicle_shifts(plate)
        if not shifts:
            return None, ("ON_TIME_ENTRY" if direction == "ENTRY" else "ON_TIME_EXIT")

        local = ts.astimezone(timezone.utc)
        weekday = DAYS[local.weekday()]
        now_t = local.time()

        # Pick the first shift whose day-of-week matches; otherwise first shift
        match = None
        for s in shifts:
            try:
                days = json.loads(s["days_of_week"])
                gates = json.loads(s["permitted_gates"])
            except Exception:
                days, gates = [], []
            if weekday in days and (not gates or gate_id in gates):
                match = s
                break
        if match is None:
            match = shifts[0]

        start = _parse_hhmm(match["start_time"])
        end = _parse_hhmm(match["end_time"])
        grace = timedelta(minutes=match["grace_period_minutes"])
        ts_dt = datetime.combine(local.date(), now_t, tzinfo=timezone.utc)
        start_dt = datetime.combine(local.date(), start, tzinfo=timezone.utc)
        end_dt = datetime.combine(local.date(), end, tzinfo=timezone.utc)
        # Handle overnight shift
        if end <= start:
            if now_t < start:
                start_dt -= timedelta(days=1)
            else:
                end_dt += timedelta(days=1)

        if direction == "ENTRY":
            if ts_dt < start_dt - timedelta(hours=1):
                status = "EARLY_ARRIVAL"
            elif ts_dt <= start_dt + grace:
                status = "ON_TIME_ENTRY"
            else:
                status = "LATE_ARRIVAL"
        else:
            if ts_dt < end_dt - grace:
                status = "EARLY_DEPARTURE"
            else:
                status = "ON_TIME_EXIT"
        return match["shift_id"], status

    def _compute_dwell(self, plate: str, exit_ts: datetime) -> Optional[float]:
        row = self.conn.execute(
            "SELECT timestamp FROM access_log "
            "WHERE plate_number = ? AND direction = 'ENTRY' "
            "AND id NOT IN ("
            "  SELECT a.id FROM access_log a "
            "  JOIN access_log b ON b.plate_number = a.plate_number "
            "  WHERE a.direction='ENTRY' AND b.direction='EXIT' "
            "  AND b.timestamp > a.timestamp"
            ") "
            "ORDER BY id DESC LIMIT 1",
            (plate,),
        ).fetchone()
        if row is None:
            return None
        entry_ts = _parse_iso(row["timestamp"])
        return max(0.0, (exit_ts - entry_ts).total_seconds())

    def _insert_access_log(self, *, plate_number: str, timestamp: str, gate_id: str,
                           direction: str, dwell: Optional[float], shift_id: Optional[str],
                           confidence: float, status: str, crop_b64: Optional[str]) -> int:
        with transaction(self.conn) as cur:
            prev = get_prev_hash(cur)
            # Step 1: Insert with a placeholder hash to obtain the auto-assigned row id.
            # The placeholder must never leave the transaction in a valid state if
            # Step 2 fails — the surrounding transaction ensures atomicity.
            cur.execute(
                "INSERT INTO access_log "
                "(plate_number,timestamp,gate_id,direction,dwell_time_seconds,shift_id,"
                " confidence_score,status,row_hash,plate_crop_b64) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (plate_number, timestamp, gate_id, direction, dwell, shift_id,
                 confidence, status, "PENDING", crop_b64),
            )
            log_id = int(cur.lastrowid)
            # Step 2: Recompute hash binding the actual row id to prevent row-reordering
            # attacks (§6.6).  Including the id means any swap of two rows will cause
            # verify_chain() to detect a mismatch at the earlier of the two row ids.
            row_hash = compute_row_hash(
                log_id, plate_number, timestamp, gate_id, direction, prev
            )
            cur.execute(
                "UPDATE access_log SET row_hash=? WHERE id=?",
                (row_hash, log_id),
            )
        return log_id

    def _handle_visitor(self, raw_plate: str, confidence: float, gate_id: str,
                        direction: str, ts_iso: str, crop_b64: Optional[str]) -> GateEventResult:
        log_id = self._insert_access_log(
            plate_number=raw_plate or "UNREADABLE",
            timestamp=ts_iso,
            gate_id=gate_id,
            direction=direction,
            dwell=None,
            shift_id=None,
            confidence=confidence,
            status="VISITOR",
            crop_b64=crop_b64,
        )

        def _timeout_reject():
            try:
                with transaction(self.conn) as cur:
                    cur.execute(
                        "UPDATE access_log SET status='VISITOR_TIMEOUT_REJECT' "
                        "WHERE id=? AND status='VISITOR'",
                        (log_id,),
                    )
                    cur.execute(
                        "INSERT INTO gate_rejections "
                        "(plate_number,timestamp,gate_id,reason,confidence_score) "
                        "VALUES (?,?,?,?,?)",
                        (raw_plate, _utc_iso(), gate_id, "VISITOR_TIMEOUT_REJECT", confidence),
                    )
                self.sse_publish({"type": "exception_timeout", "id": log_id})
            except Exception as exc:
                logger.error("Timeout reject failed: %s", exc)
            with self._pending_lock:
                self._pending.pop(log_id, None)

        timer = threading.Timer(self.exception_timeout_seconds, _timeout_reject)
        timer.daemon = True
        with self._pending_lock:
            self._pending[log_id] = _PendingException(log_id, timer, gate_id)
        timer.start()

        self.sse_publish({
            "type": "exception",
            "id": log_id,
            "raw_plate": raw_plate,
            "gate": gate_id,
            "direction": direction,
            "timestamp": ts_iso,
            "confidence": confidence,
        })

        return GateEventResult(
            outcome="EXCEPTION_PENDING_DISPOSITION",
            matched_plate=None,
            status="VISITOR",
            access_log_id=log_id,
            dwell_time_seconds=None,
            confidence=confidence,
            raw_plate=raw_plate,
        )

    def _handle_rejected(self, plate: str, confidence: float, gate_id: str,
                         ts_iso: str, reason: str) -> GateEventResult:
        with transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO gate_rejections "
                "(plate_number,timestamp,gate_id,reason,confidence_score) "
                "VALUES (?,?,?,?,?)",
                (plate, ts_iso, gate_id, reason, confidence),
            )
        if self.barrier:
            try:
                self.barrier.close(gate_id)
            except Exception:
                pass
        self.sse_publish({
            "type": "rejection",
            "plate": plate,
            "gate": gate_id,
            "reason": reason,
            "timestamp": ts_iso,
        })
        return GateEventResult(
            outcome="BARRIER_CLOSED_REJECTED",
            matched_plate=plate,
            status=reason,
            access_log_id=None,
            dwell_time_seconds=None,
            confidence=confidence,
        )

    def _overstay_loop(self) -> None:
        while not self._overstay_stop.is_set():
            try:
                self._check_overstay_once()
            except Exception as exc:
                logger.error("Overstay check failed: %s", exc)
            self._overstay_stop.wait(OVERSTAY_CHECK_INTERVAL_S)

    def _check_overstay_once(self) -> None:
        rows = self.conn.execute(
            "SELECT a.id, a.plate_number, a.timestamp, a.shift_id, a.status "
            "FROM access_log a "
            "WHERE a.direction='ENTRY' AND a.status NOT IN ('OVERSTAY','VISITOR_REJECTED','VISITOR_TIMEOUT_REJECT') "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM access_log b "
            "  WHERE b.plate_number=a.plate_number AND b.direction='EXIT' "
            "  AND b.timestamp > a.timestamp"
            ")"
        ).fetchall()
        now = datetime.now(timezone.utc)
        for r in rows:
            entry_ts = _parse_iso(r["timestamp"])
            if r["shift_id"]:
                s = self.conn.execute(
                    "SELECT end_time FROM shifts WHERE shift_id=?", (r["shift_id"],)
                ).fetchone()
                if s:
                    end_t = _parse_hhmm(s["end_time"])
                    end_dt = datetime.combine(entry_ts.date(), end_t, tzinfo=timezone.utc)
                    if end_dt < entry_ts:
                        end_dt += timedelta(days=1)
                    if now > end_dt + timedelta(minutes=30):
                        # Conditional UPDATE guards against the race condition where
                        # another thread inserts an EXIT record between the SELECT
                        # above and this write.  The subquery re-checks for an EXIT
                        # event at commit time; if one now exists, rowcount == 0 and
                        # the OVERSTAY flag is not applied (§6.4).
                        with transaction(self.conn) as cur:
                            cur.execute(
                                "UPDATE access_log SET status='OVERSTAY' "
                                "WHERE id=? "
                                "AND status NOT IN ('OVERSTAY','VISITOR_REJECTED',"
                                "                   'VISITOR_TIMEOUT_REJECT') "
                                "AND NOT EXISTS ("
                                "  SELECT 1 FROM access_log b "
                                "  WHERE b.plate_number=("
                                "    SELECT plate_number FROM access_log WHERE id=?) "
                                "  AND b.direction='EXIT' "
                                "  AND b.timestamp > ("
                                "    SELECT timestamp FROM access_log WHERE id=?))",
                                (r["id"], r["id"], r["id"]),
                            )
            elif (now - entry_ts) > timedelta(hours=12):
                with transaction(self.conn) as cur:
                    cur.execute(
                        "UPDATE access_log SET status='OVERSTAY' "
                        "WHERE id=? "
                        "AND status NOT IN ('OVERSTAY','VISITOR_REJECTED',"
                        "                   'VISITOR_TIMEOUT_REJECT') "
                        "AND NOT EXISTS ("
                        "  SELECT 1 FROM access_log b "
                        "  WHERE b.plate_number=("
                        "    SELECT plate_number FROM access_log WHERE id=?) "
                        "  AND b.direction='EXIT' "
                        "  AND b.timestamp > ("
                        "    SELECT timestamp FROM access_log WHERE id=?))",
                        (r["id"], r["id"], r["id"]),
                    )
