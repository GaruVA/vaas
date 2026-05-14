"""Comprehensive JSON API — covers FR-01 through FR-13.

Endpoint groups
---------------
Stats          GET  /api/stats
Events         GET  /api/events/recent
Exceptions     GET  /api/exceptions/pending
               POST /api/exceptions/<id>/dispose
Vehicles       GET/POST            /api/vehicles
               GET/PUT/DELETE      /api/vehicles/<plate>
Shifts         GET/POST            /api/shifts
               GET/PUT/DELETE      /api/shifts/<id>
Zones          GET/POST            /api/zones
               GET/PUT/DELETE      /api/zones/<zone_id>
Users          GET/POST            /api/users
               GET/PUT/DELETE      /api/users/<id>
Companies      GET/POST            /api/companies
Projects       GET/POST            /api/projects
               GET/PUT             /api/projects/<code>
               POST                /api/projects/<code>/close
               GET/POST            /api/projects/<code>/vehicles
               DELETE              /api/projects/<code>/vehicles/<plate>
Manager dash   GET  /api/manager/dashboard
Audit          GET  /api/audit/chain
               GET  /api/audit/log
               GET  /api/audit/rejections
"""
from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta, timezone

import bcrypt
from flask import Blueprint, Response, current_app, g, jsonify, make_response, request, session

from src.analytics import (
    admin_audit_report,
    csv_string,
    export_pdf,
    gate_rejection_audit,
    ohs_compliance_report,
    personal_vehicle_allowance_report,
    subcontractor_billing_audit,
    zone_occupancy_snapshot,
)
from src.audit import verify_chain
from src.database import VEHICLE_CATEGORIES, VEHICLE_TYPES, transaction
from src.projects import (
    assign_vehicle_to_project,
    close_project,
    create_company,
    create_project,
    create_zone,
    get_project,
    list_companies,
    list_project_vehicles,
    list_projects,
    list_zones,
    unassign_vehicle_from_project,
)
from webapp.auth import requires_role

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _audit(action: str, entity_type: str, entity_id: str,
           details: dict | None = None) -> None:
    """Write a row to admin_audit_log (never raises)."""
    try:
        g.db.execute(
            "INSERT INTO admin_audit_log "
            "(user_id, username, action, entity_type, entity_id, delta_json) "
            "VALUES (?,?,?,?,?,?)",
            (
                session.get("user_id"),
                session.get("username"),
                action,
                entity_type,
                str(entity_id),
                json.dumps(details) if details else None,
            ),
        )
    except Exception:
        pass


def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


# Display label mapping for access_log statuses → UI badge text
_STATUS_DISPLAY: dict[str, str] = {
    "AUTHORISED":                   "CLEARED",
    "VISITOR":                      "EXCEPTION",
    "DOUBLE_ENTRY":                 "FLAGGED",
    "UNMATCHED_EXIT":               "FLAGGED",
    "OVERSTAY":                     "OVERSTAY",
    "VISITOR_ADMITTED":             "ADMITTED",
    "VISITOR_REJECTED":             "REJECTED",
    "BLOCKED":                      "BLOCKED",
    "VISITOR_PENDING_REGISTRATION": "PENDING REG",
}


def _current_shift() -> dict:
    """Return the current operational shift name, label, and minutes remaining."""
    now = datetime.now(timezone.utc)
    h = now.hour
    if 7 <= h < 15:
        name, label = "MORNING", "07:00 – 15:00 UTC"
        end = now.replace(hour=15, minute=0, second=0, microsecond=0)
    elif 15 <= h < 23:
        name, label = "EVENING", "15:00 – 23:00 UTC"
        end = now.replace(hour=23, minute=0, second=0, microsecond=0)
    else:
        name, label = "NIGHT", "23:00 – 07:00 UTC"
        if h >= 23:
            end = (now + timedelta(days=1)).replace(
                hour=7, minute=0, second=0, microsecond=0)
        else:
            end = now.replace(hour=7, minute=0, second=0, microsecond=0)
    minutes_remaining = max(0, int((end - now).total_seconds() / 60))
    return {"name": name, "label": label, "minutes_remaining": minutes_remaining}


# ─────────────────────────────────────────────────────────────────────────────
# Session User Info
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/user")
def get_current_user():
    """Return current logged-in user info from session."""
    user_id = session.get("user_id")
    if not user_id:
        return _err("Not authenticated", 401)

    row = g.db.execute(
        "SELECT id, username, full_name, role FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not row:
        return _err("User not found", 404)

    return jsonify({
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
    })


# ─────────────────────────────────────────────────────────────────────────────
# FR-01 / FR-02  Stats hub
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/stats")
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def stats():
    """Top-level KPI summary for the VAAS hub page."""
    db = g.db
    today_str = _today()
    events_today = db.execute(
        "SELECT COUNT(*) FROM access_log WHERE DATE(timestamp) = ?",
        (today_str,)
    ).fetchone()[0]

    active_vehicles = db.execute(
        "SELECT COUNT(*) FROM registered_vehicles WHERE registration_status = 'ACTIVE'"
    ).fetchone()[0]

    pending_exceptions = db.execute(
        "SELECT COUNT(*) FROM access_log WHERE status = 'VISITOR'"
    ).fetchone()[0]

    # Chain integrity — lightweight check (last 200 rows only for speed)
    try:
        result = verify_chain(db)
        chain_ok = result.ok
        chain_msg = "OK" if result.ok else (result.reason or "BROKEN")
    except Exception as exc:
        chain_ok = False
        chain_msg = str(exc)

    return jsonify({
        "events_today":       events_today,
        "active_vehicles":    active_vehicles,
        "pending_exceptions": pending_exceptions,
        "chain_integrity":    chain_ok,
        "chain_msg":          chain_msg,
    })


# ─────────────────────────────────────────────────────────────────────────────
# FR-01  Recent gate events
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/events/recent")
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def events_recent():
    limit = min(int(request.args.get("limit", 50)), 200)
    rows = g.db.execute(
        "SELECT id, plate_number, timestamp, gate_id, direction, "
        "       status, confidence_score "
        "FROM access_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    result = []
    for r in rows:
        row = dict(r)
        row["display_status"] = _STATUS_DISPLAY.get(row.get("status", ""), row.get("status", ""))

        is_anomaly = row.get("status") in ("DOUBLE_ENTRY", "UNMATCHED_EXIT", "VISITOR", "OVERSTAY")
        row["is_anomaly"] = is_anomaly

        result.append(row)
    return jsonify(result)


# Legacy alias kept for backwards compat
@api_bp.route("/recent")
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def recent():
    return events_recent()


# ─────────────────────────────────────────────────────────────────────────────
# Shift status
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/shift")
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def current_shift_route():
    """Return active shift name, label, and minutes remaining (UTC-based)."""
    return jsonify(_current_shift())


@api_bp.route("/gates/status")
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def gates_status():
    """Return real-time status of all gates — which have pending exceptions/ALPR activity."""
    gates = g.db.execute(
        """SELECT DISTINCT gate_id FROM access_log
           WHERE DATE(timestamp) = DATE('now')
           ORDER BY gate_id"""
    ).fetchall()

    result = {}
    for row in gates:
        gate_id = row["gate_id"]

        pending_exc = g.db.execute(
            "SELECT COUNT(*) FROM access_log WHERE gate_id=? AND status='VISITOR'",
            (gate_id,)
        ).fetchone()[0]

        recent_activity = g.db.execute(
            "SELECT MAX(timestamp) FROM access_log WHERE gate_id=? AND DATE(timestamp)=DATE('now')",
            (gate_id,)
        ).fetchone()[0]

        result[gate_id] = {
            "gate_id": gate_id,
            "has_exceptions": pending_exc > 0,
            "exception_count": pending_exc,
            "alpr_active": recent_activity is not None,
            "last_activity": recent_activity,
        }

    return jsonify(result)


# ─────────────────────────────────────────────────────────────────────────────
# FR-02  Exception queue + disposition
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/exceptions/pending")
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def exceptions_pending():
    seven_days_ago  = _days_ago(7)
    thirty_days_ago = _days_ago(30)

    rows = g.db.execute(
        """SELECT a.id, a.plate_number, a.timestamp, a.gate_id, a.direction,
                  a.confidence_score,
                  COALESCE(v.registration_status, 'UNKNOWN') AS reg_status,
                  COALESCE(v.vehicle_category,    'UNKNOWN') AS vehicle_category,
                  COALESCE(u.full_name, u.username)          AS driver_name,
                  va.user_id                                 AS driver_user_id,
                  (SELECT COUNT(*) FROM access_log x
                   WHERE x.plate_number = a.plate_number
                     AND x.status IN ('VISITOR','DOUBLE_ENTRY','UNMATCHED_EXIT','OVERSTAY')
                     AND DATE(x.timestamp) >= :d7)           AS anomaly_count,
                  (SELECT COUNT(*) FROM access_log x
                   WHERE x.plate_number = a.plate_number
                     AND DATE(x.timestamp) >= :d30)          AS total_events_30d,
                  (SELECT COUNT(*) FROM access_log x
                   WHERE x.plate_number = a.plate_number
                     AND DATE(x.timestamp) >= :d30
                     AND x.status = 'AUTHORISED')            AS auth_events_30d
           FROM access_log a
           LEFT JOIN registered_vehicles v  ON a.plate_number = v.plate_number
           LEFT JOIN vehicle_assignments va ON a.plate_number = va.plate_number
                                           AND va.is_active = 1
           LEFT JOIN users u                ON va.user_id = u.id
           WHERE a.status = 'VISITOR'
           ORDER BY a.id DESC""",
        {"d7": seven_days_ago, "d30": thirty_days_ago},
    ).fetchall()

    result = []
    for r in rows:
        row = dict(r)

        # OHS status derived from assignment + anomaly history
        if not row.get("driver_user_id"):
            row["ohs_status"] = "UNASSIGNED"
        elif row["anomaly_count"] >= 7:
            row["ohs_status"] = "HIGH_OVERSTAY"
        elif row["anomaly_count"] >= 3:
            row["ohs_status"] = "MEDIUM_RISK"
        else:
            row["ohs_status"] = "OK"

        # 30-day compliance percentage
        total = row.get("total_events_30d") or 0
        auth  = row.get("auth_events_30d")  or 0
        row["compliance_pct"] = round(auth / total * 100) if total else 100

        # Last 3 gate events for this plate (mini-timeline)
        recent = g.db.execute(
            "SELECT id, timestamp, gate_id, direction, status "
            "FROM access_log WHERE plate_number=? ORDER BY id DESC LIMIT 3",
            (row["plate_number"],),
        ).fetchall()
        row["recent_events"] = [
            {**dict(re), "display_status": _STATUS_DISPLAY.get(re["status"], re["status"])}
            for re in recent
        ]

        result.append(row)

    return jsonify(result)


# Legacy alias
@api_bp.route("/pending")
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def pending():
    return exceptions_pending()


@api_bp.route("/exceptions/<int:access_log_id>/dispose", methods=["POST"])
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def dispose_exception(access_log_id: int):
    body = request.get_json(silent=True) or {}
    disposition = (body.get("disposition") or "REJECT").upper()
    if disposition not in ("ADMIT", "REJECT", "REGISTER"):
        return _err("disposition must be ADMIT, REJECT, or REGISTER")

    engine = current_app.config.get("VAAS_ENGINE")
    if engine is None:
        return _err("Attendance engine not available", 503)

    engine.dispose_exception(
        access_log_id,
        disposition,
        operator_user_id=session.get("user_id"),
    )
    _audit("DISPOSE_EXCEPTION", "access_log", str(access_log_id),
           {"disposition": disposition})

    _DISPOSITION_STATUS = {
        "ADMIT":    "VISITOR_ADMITTED",
        "REJECT":   "VISITOR_REJECTED",
        "REGISTER": "VISITOR_PENDING_REGISTRATION",
    }
    broker = current_app.config.get("VAAS_BROKER")
    if broker:
        row_meta = current_app.config["VAAS_DB"].execute(
            "SELECT gate_id, plate_number FROM access_log WHERE id=?",
            (access_log_id,),
        ).fetchone()
        broker.publish({
            "type":       "exception_disposed",
            "id":         access_log_id,
            "gate_id":    row_meta["gate_id"] if row_meta else None,
            "new_status": _DISPOSITION_STATUS.get(disposition, ""),
        })

    return jsonify({"status": "ok", "disposition": disposition})


# ─────────────────────────────────────────────────────────────────────────────
# Fleet counts (lightweight — for home page card)
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/fleet/counts")
@requires_role("ADMIN", "MANAGER")
def fleet_counts():
    """Return total counts of active vehicles, shifts, zones, and users."""
    vehicles = g.db.execute(
        "SELECT COUNT(*) FROM registered_vehicles WHERE registration_status='ACTIVE'"
    ).fetchone()[0]
    shifts = g.db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0]
    zones  = g.db.execute("SELECT COUNT(*) FROM cdl_zones").fetchone()[0]
    users  = g.db.execute(
        "SELECT COUNT(*) FROM users WHERE is_active IS NULL OR is_active=1"
    ).fetchone()[0]
    return jsonify({"vehicles": vehicles, "shifts": shifts,
                    "zones": zones, "users": users})


# ─────────────────────────────────────────────────────────────────────────────
# FR-05  Vehicles
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/vehicles", methods=["GET"])
@requires_role("ADMIN", "MANAGER")
def list_vehicles():
    seven_days_ago = _days_ago(7)
    rows = g.db.execute(
        """SELECT rv.*,
                  va.user_id   AS assigned_user_id,
                  u.username   AS assigned_username,
                  COALESCE(u.full_name, u.username) AS assigned_driver_name,
                  (SELECT COUNT(*) FROM access_log x
                   WHERE x.plate_number = rv.plate_number
                     AND x.status IN ('DOUBLE_ENTRY','UNMATCHED_EXIT')
                     AND DATE(x.timestamp) >= :d7) AS anomaly_count,
                  (SELECT timestamp FROM access_log x
                   WHERE x.plate_number = rv.plate_number
                   ORDER BY x.id DESC LIMIT 1) AS last_event_ts,
                  (SELECT gate_id FROM access_log x
                   WHERE x.plate_number = rv.plate_number
                   ORDER BY x.id DESC LIMIT 1) AS last_event_gate,
                  (SELECT direction FROM access_log x
                   WHERE x.plate_number = rv.plate_number
                   ORDER BY x.id DESC LIMIT 1) AS last_event_dir
           FROM registered_vehicles rv
           LEFT JOIN vehicle_assignments va
                ON rv.plate_number = va.plate_number AND va.is_active = 1
           LEFT JOIN users u ON va.user_id = u.id
           ORDER BY rv.plate_number""",
        {"d7": seven_days_ago},
    ).fetchall()

    result = []
    for r in rows:
        row = dict(r)
        anom = row.get("anomaly_count", 0) or 0
        status = row.get("registration_status", "")
        if status == "SUSPENDED":
            row["ohs_status"] = "SUSPENDED"
        elif not row.get("assigned_user_id"):
            row["ohs_status"] = "UNASSIGNED"
        elif anom >= 5:
            row["ohs_status"] = "HIGH_OVERSTAY"
        elif anom >= 2:
            row["ohs_status"] = "MEDIUM_RISK"
        else:
            row["ohs_status"] = "OK"
        result.append(row)
    return jsonify(result)


@api_bp.route("/vehicles/<plate>/impact", methods=["GET"])
@requires_role("ADMIN", "MANAGER")
def vehicle_impact(plate: str):
    """Return downstream impact data for the Cascade Suspend modal."""
    plate = plate.upper()
    veh = g.db.execute(
        "SELECT 1 FROM registered_vehicles WHERE plate_number=?", (plate,)
    ).fetchone()
    if not veh:
        return _err("Vehicle not found", 404)

    # Active driver assignment
    driver = g.db.execute(
        "SELECT va.user_id, COALESCE(u.full_name, u.username) AS driver_name "
        "FROM vehicle_assignments va JOIN users u ON va.user_id = u.id "
        "WHERE va.plate_number=? AND va.is_active=1",
        (plate,),
    ).fetchone()

    # Active project assignments
    try:
        proj_rows = g.db.execute(
            "SELECT pva.project_code FROM project_vehicle_assignments pva "
            "JOIN projects p ON pva.project_code = p.project_code "
            "WHERE pva.plate_number=? AND p.status='ACTIVE' AND pva.removed_at IS NULL",
            (plate,),
        ).fetchall()
        proj_codes = [r["project_code"] for r in proj_rows]
    except Exception:
        proj_codes = []

    # 7-day anomaly count
    anomaly_count = g.db.execute(
        "SELECT COUNT(*) FROM access_log "
        "WHERE plate_number=? AND status IN ('DOUBLE_ENTRY','UNMATCHED_EXIT') "
        "AND DATE(timestamp) >= ?",
        (plate, _days_ago(7)),
    ).fetchone()[0]

    return jsonify({
        "plate_number":   plate,
        "driver_user_id": driver["user_id"] if driver else None,
        "driver_name":    driver["driver_name"] if driver else None,
        "project_count":  len(proj_codes),
        "project_codes":  proj_codes,
        "anomaly_count":  anomaly_count,
    })


@api_bp.route("/vehicles", methods=["POST"])
@requires_role("ADMIN")
def create_vehicle():
    data = request.get_json(silent=True) or {}
    plate = (data.get("plate_number") or "").strip().upper()
    if not plate:
        return _err("plate_number is required")
    cat   = data.get("vehicle_category", "CONTRACTOR")
    vtype = data.get("vehicle_type", "CAR")
    status = data.get("registration_status", "ACTIVE")
    if cat not in VEHICLE_CATEGORIES:
        cat = "CONTRACTOR"
    if vtype not in VEHICLE_TYPES:
        vtype = "CAR"

    try:
        with transaction(g.db) as cur:
            cur.execute(
                "INSERT OR REPLACE INTO registered_vehicles "
                "(plate_number, vehicle_category, vehicle_type, contractor_name, "
                " department, registration_status, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (plate, cat, vtype,
                 data.get("contractor_name"),
                 data.get("department"),
                 status,
                 data.get("notes")),
            )
            user_id = data.get("user_id")
            if user_id:
                cur.execute(
                    "UPDATE vehicle_assignments SET is_active=0 "
                    "WHERE plate_number=?", (plate,)
                )
                cur.execute(
                    "INSERT INTO vehicle_assignments "
                    "(plate_number, user_id, is_active) VALUES (?,?,1)",
                    (plate, user_id),
                )
    except Exception as exc:
        return _err(str(exc))

    _audit("CREATE", "vehicle", plate, data)
    return jsonify({"status": "created", "plate_number": plate}), 201


@api_bp.route("/vehicles/<plate>", methods=["GET"])
@requires_role("ADMIN", "MANAGER")
def get_vehicle(plate: str):
    row = g.db.execute(
        """SELECT rv.*,
                  va.user_id   AS assigned_user_id,
                  u.username   AS assigned_username,
                  COALESCE(u.full_name, u.username) AS assigned_driver_name
           FROM registered_vehicles rv
           LEFT JOIN vehicle_assignments va
                ON rv.plate_number = va.plate_number AND va.is_active = 1
           LEFT JOIN users u ON va.user_id = u.id
           WHERE rv.plate_number = ?""",
        (plate.upper(),),
    ).fetchone()
    if not row:
        return _err("Vehicle not found", 404)
    return jsonify(dict(row))


@api_bp.route("/vehicles/<plate>", methods=["PUT"])
@requires_role("ADMIN")
def update_vehicle(plate: str):
    data = request.get_json(silent=True) or {}
    plate = plate.upper()
    exists = g.db.execute(
        "SELECT 1 FROM registered_vehicles WHERE plate_number=?", (plate,)
    ).fetchone()
    if not exists:
        return _err("Vehicle not found", 404)

    fields = ["vehicle_category", "vehicle_type", "contractor_name",
              "department", "registration_status", "notes"]
    updates = {f: data[f] for f in fields if f in data}
    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        g.db.execute(
            f"UPDATE registered_vehicles SET {set_clause} WHERE plate_number=?",
            list(updates.values()) + [plate],
        )

    user_id = data.get("user_id")
    if user_id is not None:
        g.db.execute(
            "UPDATE vehicle_assignments SET is_active=0 WHERE plate_number=?",
            (plate,),
        )
        if user_id:
            g.db.execute(
                "INSERT INTO vehicle_assignments "
                "(plate_number, user_id, is_active) VALUES (?,?,1)",
                (plate, user_id),
            )

    _audit("UPDATE", "vehicle", plate, data)
    return jsonify({"status": "updated", "plate_number": plate})


@api_bp.route("/vehicles/<plate>", methods=["DELETE"])
@requires_role("ADMIN")
def delete_vehicle(plate: str):
    plate = plate.upper()
    g.db.execute(
        "UPDATE registered_vehicles SET registration_status='SUSPENDED' "
        "WHERE plate_number=?", (plate,)
    )
    _audit("UPDATE", "vehicle", plate, {"registration_status": "SUSPENDED"})
    return jsonify({"status": "suspended", "plate_number": plate})


# ─────────────────────────────────────────────────────────────────────────────
# FR-03  Shifts
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/shifts", methods=["GET"])
@requires_role("ADMIN", "MANAGER")
def list_shifts():
    rows = g.db.execute("SELECT * FROM shifts ORDER BY shift_id").fetchall()
    return jsonify([dict(r) for r in rows])


@api_bp.route("/shifts", methods=["POST"])
@requires_role("ADMIN")
def create_shift():
    data = request.get_json(silent=True) or {}
    name  = (data.get("shift_name") or "").strip()
    start = data.get("start_time")
    end   = data.get("end_time")
    if not name or not start or not end:
        return _err("shift_name, start_time, end_time are required")
    try:
        cur = g.db.execute(
            "INSERT INTO shifts (shift_name, start_time, end_time, days_of_week, permitted_gates, grace_period_minutes) "
            "VALUES (?,?,?,?,?,?)",
            (name, start, end,
             data.get("days_of_week", ""),
             data.get("permitted_gates", ""),
             data.get("grace_minutes", 15)),
        )
        shift_id = cur.lastrowid
    except Exception as exc:
        return _err(str(exc))
    _audit("CREATE", "shift", str(shift_id), data)
    return jsonify({"status": "created", "shift_id": shift_id}), 201


@api_bp.route("/shifts/<int:shift_id>", methods=["GET"])
@requires_role("ADMIN", "MANAGER")
def get_shift(shift_id: int):
    row = g.db.execute(
        "SELECT * FROM shifts WHERE shift_id=?", (shift_id,)
    ).fetchone()
    if not row:
        return _err("Shift not found", 404)
    return jsonify(dict(row))


@api_bp.route("/shifts/<int:shift_id>", methods=["PUT"])
@requires_role("ADMIN")
def update_shift(shift_id: int):
    data = request.get_json(silent=True) or {}
    updates = {}

    if "shift_name" in data:
        updates["shift_name"] = data["shift_name"]
    if "start_time" in data:
        updates["start_time"] = data["start_time"]
    if "end_time" in data:
        updates["end_time"] = data["end_time"]
    if "days_of_week" in data:
        updates["days_of_week"] = data["days_of_week"]
    if "grace_minutes" in data:
        updates["grace_period_minutes"] = data["grace_minutes"]

    if not updates:
        return _err("No updatable fields provided")

    set_clause = ", ".join(f"{k}=?" for k in updates)
    g.db.execute(
        f"UPDATE shifts SET {set_clause} WHERE shift_id=?",
        list(updates.values()) + [shift_id],
    )
    _audit("UPDATE", "shift", str(shift_id), data)
    return jsonify({"status": "updated", "shift_id": shift_id})


@api_bp.route("/shifts/<int:shift_id>", methods=["DELETE"])
@requires_role("ADMIN")
def delete_shift(shift_id: int):
    g.db.execute("DELETE FROM shifts WHERE shift_id=?", (shift_id,))
    _audit("DELETE", "shift", str(shift_id))
    return jsonify({"status": "deleted", "shift_id": shift_id})


# ─────────────────────────────────────────────────────────────────────────────
# FR-04  Zones
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/zones", methods=["GET"])
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def get_zones():
    rows = zone_occupancy_snapshot(g.db)
    # Supplement snapshot with associated_gates (needed by fleet edit modal)
    gates_map = {
        r["zone_id"]: r["associated_gates"]
        for r in g.db.execute(
            "SELECT zone_id, associated_gates FROM cdl_zones"
        ).fetchall()
    }
    for row in rows:
        raw = gates_map.get(row["zone_id"], "[]")
        try:
            row["associated_gates"] = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            row["associated_gates"] = []
        # Alias for frontend compatibility
        row["vehicle_capacity"] = row.get("capacity_vehicles", 50)
    return jsonify(rows)


@api_bp.route("/zones", methods=["POST"])
@requires_role("ADMIN")
def post_zone():
    data = request.get_json(silent=True) or {}
    zone_id   = (data.get("zone_id") or "").strip().upper()
    zone_name = (data.get("zone_name") or "").strip()
    zone_type = (data.get("zone_type") or "").strip().upper()
    gates     = data.get("associated_gates") or []
    if not zone_id or not zone_name or not zone_type:
        return _err("zone_id, zone_name, zone_type are required")
    try:
        create_zone(g.db, zone_id, zone_name, zone_type, gates,
                    data.get("vehicle_capacity", 50))
    except (ValueError, Exception) as exc:
        return _err(str(exc))
    _audit("CREATE", "zone", zone_id, data)
    return jsonify({"status": "created", "zone_id": zone_id}), 201


@api_bp.route("/zones/<zone_id>", methods=["PUT"])
@requires_role("ADMIN")
def update_zone(zone_id: str):
    data = request.get_json(silent=True) or {}
    fields = ["zone_name", "zone_type", "vehicle_capacity"]
    updates = {f: data[f] for f in fields if f in data}
    if "associated_gates" in data:
        updates["associated_gates"] = json.dumps(data["associated_gates"])
    if not updates:
        return _err("No updatable fields provided")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    g.db.execute(
        f"UPDATE cdl_zones SET {set_clause} WHERE zone_id=?",
        list(updates.values()) + [zone_id.upper()],
    )
    _audit("UPDATE", "zone", zone_id, data)
    return jsonify({"status": "updated", "zone_id": zone_id})


@api_bp.route("/zones/<zone_id>", methods=["DELETE"])
@requires_role("ADMIN")
def delete_zone(zone_id: str):
    g.db.execute("DELETE FROM cdl_zones WHERE zone_id=?", (zone_id.upper(),))
    _audit("DELETE", "zone", zone_id)
    return jsonify({"status": "deleted", "zone_id": zone_id})


# ─────────────────────────────────────────────────────────────────────────────
# FR-05  Users (RBAC)
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/users", methods=["GET"])
@requires_role("ADMIN")
def list_users():
    rows = g.db.execute(
        "SELECT id, username, full_name, role, last_login "
        "FROM users ORDER BY username"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@api_bp.route("/users", methods=["POST"])
@requires_role("ADMIN")
def create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()
    role     = (data.get("role") or "OPERATOR").upper()
    if not username or not password:
        return _err("username and password are required")
    if role not in ("ADMIN", "MANAGER", "OPERATOR"):
        return _err("role must be ADMIN, MANAGER, or OPERATOR")
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        cur = g.db.execute(
            "INSERT INTO users (username, password_hash, role, full_name) "
            "VALUES (?,?,?,?)",
            (username, pw_hash, role, data.get("full_name")),
        )
        user_id = cur.lastrowid
    except Exception as exc:
        return _err(str(exc))
    _audit("CREATE", "user", str(user_id), {"username": username, "role": role})
    return jsonify({"status": "created", "user_id": user_id}), 201


@api_bp.route("/users/<int:user_id>", methods=["GET"])
@requires_role("ADMIN")
def get_user(user_id: int):
    row = g.db.execute(
        "SELECT id, username, full_name, role, last_login "
        "FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not row:
        return _err("User not found", 404)
    return jsonify(dict(row))


@api_bp.route("/users/<int:user_id>", methods=["PUT"])
@requires_role("ADMIN")
def update_user(user_id: int):
    data = request.get_json(silent=True) or {}
    updates = {}
    for f in ("full_name", "role"):
        if f in data:
            updates[f] = data[f]
    if "password" in data and data["password"]:
        updates["password_hash"] = bcrypt.hashpw(
            data["password"].encode(), bcrypt.gensalt()
        ).decode()
    if updates.get("role") and updates["role"] not in ("ADMIN", "MANAGER", "OPERATOR"):
        return _err("role must be ADMIN, MANAGER, or OPERATOR")
    if not updates:
        return _err("No updatable fields provided")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    g.db.execute(
        f"UPDATE users SET {set_clause} WHERE id=?",
        list(updates.values()) + [user_id],
    )
    _audit("UPDATE", "user", str(user_id), {k: v for k, v in data.items() if k != "password"})
    return jsonify({"status": "updated", "user_id": user_id})


@api_bp.route("/users/<int:user_id>", methods=["DELETE"])
@requires_role("ADMIN")
def delete_user(user_id: int):
    if user_id == session.get("user_id"):
        return _err("Cannot delete your own account")
    g.db.execute("DELETE FROM users WHERE id=?", (user_id,))
    _audit("DELETE", "user", str(user_id))
    return jsonify({"status": "deleted", "user_id": user_id})


# ─────────────────────────────────────────────────────────────────────────────
# FR-12  Subcontractor companies
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/companies", methods=["GET"])
@requires_role("ADMIN", "MANAGER")
def get_companies():
    return jsonify(list_companies(g.db))


@api_bp.route("/companies", methods=["POST"])
@requires_role("ADMIN")
def post_company():
    data = request.get_json(silent=True) or {}
    company_id   = (data.get("company_id") or "").strip().upper()
    company_name = (data.get("company_name") or "").strip()
    if not company_id or not company_name:
        return _err("company_id and company_name are required")
    try:
        create_company(
            g.db, company_id, company_name,
            data.get("contact_name"),
            data.get("contact_phone"),
            data.get("contact_email"),
        )
    except Exception as exc:
        return _err(str(exc))
    _audit("CREATE", "company", company_id, data)
    return jsonify({"status": "created", "company_id": company_id}), 201


# ─────────────────────────────────────────────────────────────────────────────
# FR-11  Projects
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/projects", methods=["GET"])
@requires_role("ADMIN", "MANAGER")
def get_projects():
    status = request.args.get("status")
    return jsonify(list_projects(g.db, status=status))


@api_bp.route("/projects", methods=["POST"])
@requires_role("ADMIN")
def post_project():
    data = request.get_json(silent=True) or {}
    code   = (data.get("project_code") or "").strip().upper()
    vessel = (data.get("vessel_name") or "").strip()
    zone   = (data.get("zone_id") or "").strip().upper()
    start  = data.get("start_date")
    if not code or not vessel or not zone or not start:
        return _err("project_code, vessel_name, zone_id, start_date are required")
    try:
        create_project(
            g.db, code, vessel, zone, start,
            data.get("end_date"),
            data.get("project_manager"),
        )
    except Exception as exc:
        return _err(str(exc))
    _audit("CREATE", "project", code, data)
    return jsonify({"status": "created", "project_code": code}), 201


@api_bp.route("/projects/<code>", methods=["GET"])
@requires_role("ADMIN", "MANAGER")
def get_project_detail(code: str):
    proj = get_project(g.db, code.upper())
    if not proj:
        return _err("Project not found", 404)
    return jsonify(proj)


@api_bp.route("/projects/<code>", methods=["PUT"])
@requires_role("ADMIN")
def update_project(code: str):
    data = request.get_json(silent=True) or {}
    fields = ["vessel_name", "zone_id", "start_date", "end_date",
              "status", "project_manager"]
    updates = {f: data[f] for f in fields if f in data}
    if not updates:
        return _err("No updatable fields provided")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    g.db.execute(
        f"UPDATE projects SET {set_clause} WHERE project_code=?",
        list(updates.values()) + [code.upper()],
    )
    _audit("UPDATE", "project", code, data)
    return jsonify({"status": "updated", "project_code": code})


@api_bp.route("/projects/<code>/close", methods=["POST"])
@requires_role("ADMIN")
def close_project_route(code: str):
    data = request.get_json(silent=True) or {}
    closure_date = data.get("closure_date") or _today()
    try:
        close_project(g.db, code.upper(), closure_date)
    except Exception as exc:
        return _err(str(exc))
    _audit("CLOSE", "project", code, {"closure_date": closure_date})
    return jsonify({"status": "closed", "project_code": code})


@api_bp.route("/projects/<code>/vehicles", methods=["GET"])
@requires_role("ADMIN", "MANAGER")
def project_vehicles_list(code: str):
    rows = list_project_vehicles(g.db, code.upper())
    return jsonify(rows)


@api_bp.route("/projects/<code>/vehicles", methods=["POST"])
@requires_role("ADMIN")
def project_vehicles_assign(code: str):
    data = request.get_json(silent=True) or {}
    plate = (data.get("plate_number") or "").strip().upper()
    role  = (data.get("role") or "").strip().upper()
    if not plate or not role:
        return _err("plate_number and role are required")
    try:
        assign_vehicle_to_project(
            g.db, code.upper(), plate, role,
            data.get("company_id"),
            data.get("assigned_at"),
        )
    except (ValueError, Exception) as exc:
        return _err(str(exc))
    _audit("ASSIGN_VEHICLE", "project", code,
           {"plate_number": plate, "role": role})
    return jsonify({"status": "assigned"}), 201


@api_bp.route("/projects/<code>/vehicles/<plate>", methods=["DELETE"])
@requires_role("ADMIN")
def project_vehicles_unassign(code: str, plate: str):
    unassign_vehicle_from_project(g.db, code.upper(), plate.upper())
    _audit("UNASSIGN_VEHICLE", "project", code, {"plate_number": plate})
    return jsonify({"status": "unassigned"})


# ─────────────────────────────────────────────────────────────────────────────
# FR-06 / FR-07 / FR-08 / FR-12 / FR-13  Manager dashboard
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/manager/dashboard")
@requires_role("MANAGER", "ADMIN")
def manager_dashboard():
    """Single endpoint delivering all BI data for vaas-manager.html."""
    db = g.db

    # Date window — default last 30 days
    date_to   = request.args.get("date_to",   _today())
    date_from = request.args.get("date_from",  _days_ago(30))

    # ── Attendance / leakage hero card ────────────────────────────────────────
    total_events = db.execute(
        "SELECT COUNT(*) FROM access_log "
        "WHERE DATE(timestamp) BETWEEN ? AND ?",
        (date_from, date_to),
    ).fetchone()[0]

    authorised_events = db.execute(
        "SELECT COUNT(*) FROM access_log "
        "WHERE DATE(timestamp) BETWEEN ? AND ? "
        "  AND status NOT IN ('VISITOR','VISITOR_REJECTED')",
        (date_from, date_to),
    ).fetchone()[0]

    exceptions_total = db.execute(
        "SELECT COUNT(*) FROM access_log "
        "WHERE DATE(timestamp) BETWEEN ? AND ? "
        "  AND status IN ('VISITOR','VISITOR_REJECTED','VISITOR_ADMITTED')",
        (date_from, date_to),
    ).fetchone()[0]

    prevented_pct = round(
        (authorised_events / total_events * 100) if total_events else 0, 1
    )

    # ── OHS compliance (FR-07) ────────────────────────────────────────────────
    ohs_rows = ohs_compliance_report(db)
    ohs_summary = {
        "ok":          sum(1 for r in ohs_rows if r["risk_flag"] == "OK"),
        "medium_risk": sum(1 for r in ohs_rows if r["risk_flag"] == "MEDIUM_RISK"),
        "high_risk":   sum(1 for r in ohs_rows if r["risk_flag"] == "HIGH_RISK"),
        "suspended":   sum(1 for r in ohs_rows if r["risk_flag"] == "SUSPENDED"),
        "unassigned":  sum(1 for r in ohs_rows if r["risk_flag"] == "UNASSIGNED"),
        "watchlist":   [r for r in ohs_rows if r["risk_flag"] not in ("OK",)][:10],
    }

    # ── Zone occupancy (FR-04 / FR-08) ───────────────────────────────────────
    zone_occupancy = zone_occupancy_snapshot(db)

    # ── Subcontractor billing aggregate (FR-12) ───────────────────────────────
    billing_rows = subcontractor_billing_audit(
        db, date_from=date_from, date_to=date_to
    )
    # Aggregate per company
    company_billing: dict = {}
    for row in billing_rows:
        cid = row["company_id"]
        if cid not in company_billing:
            company_billing[cid] = {
                "company_id":   cid,
                "company_name": row["company_name"],
                "total_trips":  0,
                "total_hours":  0.0,
                "projects":     set(),
            }
        company_billing[cid]["total_trips"] += row["trips"]
        company_billing[cid]["total_hours"] += row["billed_hours"]
        company_billing[cid]["projects"].add(row["project_code"])
    billing_summary = []
    for v in company_billing.values():
        billing_summary.append({
            "company_id":    v["company_id"],
            "company_name":  v["company_name"],
            "total_trips":   v["total_trips"],
            "total_hours":   round(v["total_hours"], 2),
            "project_count": len(v["projects"]),
        })

    # ── Registered vehicles count ─────────────────────────────────────────────
    registered_vehicles_count = db.execute(
        "SELECT COUNT(*) FROM registered_vehicles WHERE registration_status = 'ACTIVE'"
    ).fetchone()[0]

    # ── Events today and yesterday ────────────────────────────────────────────
    today_str     = _today()
    yesterday_str = _days_ago(1)
    events_today_count = db.execute(
        "SELECT COUNT(*) FROM access_log WHERE DATE(timestamp) = ?", (today_str,)
    ).fetchone()[0]
    events_yesterday_count = db.execute(
        "SELECT COUNT(*) FROM access_log WHERE DATE(timestamp) = ?", (yesterday_str,)
    ).fetchone()[0]

    # ── Fuel compliance per driver (FR-13) ────────────────────────────────────
    fc_rows = db.execute(
        """SELECT
               u.id AS user_id,
               COALESCE(u.full_name, u.username) AS driver_name,
               va.plate_number,
               COUNT(DISTINCT DATE(al.timestamp)) AS total_days,
               COUNT(DISTINCT CASE WHEN al.status IN ('ON_TIME_ENTRY','EARLY_ARRIVAL')
                                   THEN DATE(al.timestamp) END) AS eligible_days
           FROM users u
           JOIN vehicle_assignments va ON va.user_id = u.id AND va.is_active = 1
           JOIN access_log al ON al.plate_number = va.plate_number
               AND al.direction = 'ENTRY'
               AND DATE(al.timestamp) BETWEEN ? AND ?
           GROUP BY u.id, va.plate_number
           HAVING total_days > 0
           ORDER BY (eligible_days * 1.0 / total_days) ASC""",
        (date_from, date_to),
    ).fetchall()

    fuel_compliance = []
    for row in fc_rows:
        total    = row["total_days"]    or 0
        eligible = row["eligible_days"] or 0
        fuel_compliance.append({
            "driver_name":     row["driver_name"],
            "plate_number":    row["plate_number"],
            "total_days":      total,
            "eligible_days":   eligible,
            "ineligible_days": total - eligible,
            "compliance_pct":  round(eligible / total * 100) if total else 0,
        })

    # ── Prev period leakage (vs last month) ───────────────────────────────────
    prev_leakage_lkr = 0
    try:
        prev_to   = (date.fromisoformat(date_from) - timedelta(days=1)).isoformat()
        prev_from = (date.fromisoformat(date_from) - timedelta(days=30)).isoformat()
        prev_fc = db.execute(
            """SELECT
                   COUNT(DISTINCT DATE(al.timestamp)) AS total_days,
                   COUNT(DISTINCT CASE WHEN al.status IN ('ON_TIME_ENTRY','EARLY_ARRIVAL')
                                       THEN DATE(al.timestamp) END) AS eligible_days
               FROM users u
               JOIN vehicle_assignments va ON va.user_id = u.id AND va.is_active = 1
               JOIN access_log al ON al.plate_number = va.plate_number
                   AND al.direction = 'ENTRY'
                   AND DATE(al.timestamp) BETWEEN ? AND ?
               GROUP BY u.id, va.plate_number
               HAVING total_days > 0""",
            (prev_from, prev_to),
        ).fetchall()
        prev_ineligible = sum((r["total_days"] - r["eligible_days"]) for r in prev_fc)
        prev_leakage_lkr = prev_ineligible * 2678
    except Exception:
        prev_leakage_lkr = 0

    return jsonify({
        "date_from":                 date_from,
        "date_to":                   date_to,
        "total_events":              total_events,
        "authorised_events":         authorised_events,
        "exceptions_total":          exceptions_total,
        "prevented_pct":             prevented_pct,
        "registered_vehicles_count": registered_vehicles_count,
        "events_today":              events_today_count,
        "events_yesterday":          events_yesterday_count,
        "ohs":                       ohs_summary,
        "zone_occupancy":            zone_occupancy,
        "billing":                   billing_summary,
        "fuel_compliance":           fuel_compliance,
        "prev_leakage_lkr":          prev_leakage_lkr,
    })


# ─────────────────────────────────────────────────────────────────────────────
# FR-10  Forensic audit — hash chain + admin log
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/audit/chain")
@requires_role("ADMIN")
def audit_chain():
    """Chain integrity + forensic detail: tamper attribution, byte-diff, taint count."""
    import hashlib as _hashlib
    import json as _json2
    from datetime import timedelta as _td
    from src.config import GENESIS_PREV_HASH

    try:
        result = verify_chain(g.db)
        integrity = {
            "ok":           result.ok,
            "rows_checked": result.rows_checked,
            "verified_at":  result.verified_at,
            "first_bad_id": result.first_bad_id,
            "reason":       result.reason,
        }
    except Exception as exc:
        integrity = {"ok": False, "reason": str(exc),
                     "rows_checked": 0, "verified_at": None, "first_bad_id": None}

    rows = g.db.execute(
        "SELECT id, plate_number, timestamp, gate_id, direction, "
        "       status, row_hash "
        "FROM access_log ORDER BY id DESC LIMIT 100"
    ).fetchall()
    entries = [dict(r) for r in rows]

    tamper_detail = None
    attribution   = None
    tainted_count = 0
    tamper_class  = None

    first_bad_id = integrity.get("first_bad_id")
    if first_bad_id:
        tc = g.db.execute(
            "SELECT COUNT(*) FROM access_log WHERE id > ?", (first_bad_id,)
        ).fetchone()
        tainted_count = tc[0] if tc else 0

        bad = g.db.execute(
            "SELECT id, plate_number, timestamp, gate_id, direction, row_hash "
            "FROM access_log WHERE id = ?", (first_bad_id,)
        ).fetchone()

        if bad:
            bad_id, plate, ts, gate, direction, stored_hash = (
                bad[0], bad[1], bad[2], bad[3], bad[4], bad[5]
            )
            prev_r = g.db.execute(
                "SELECT row_hash FROM access_log WHERE id < ? ORDER BY id DESC LIMIT 1",
                (bad_id,),
            ).fetchone()
            prev_hash = prev_r[0] if prev_r else GENESIS_PREV_HASH

            payload = _json2.dumps(
                {"id": bad_id, "plate_number": plate, "timestamp": ts,
                 "gate_id": gate, "direction": direction, "prev_hash": prev_hash},
                sort_keys=True, separators=(",", ":"),
            )
            expected_hash = _hashlib.sha256(payload.encode()).hexdigest()

            groups = []
            for i in range(8):
                ex = expected_hash[i * 8:(i + 1) * 8]
                st = (stored_hash or "")[i * 8:(i + 1) * 8]
                groups.append({"expected": ex, "stored": st, "differs": ex != st})

            diff_positions = [i for i, g2 in enumerate(groups) if g2["differs"]]
            tamper_detail = {
                "record_id":       f"{gate}-{bad_id}",
                "plate_number":    plate,
                "timestamp":       ts,
                "gate_id":         gate,
                "direction":       direction,
                "prev_hash_prefix": (prev_hash[:8] + "…") if prev_hash else "—",
                "expected_hash":   expected_hash,
                "stored_hash":     stored_hash or "",
                "groups":          groups,
                "diff_count":      len(diff_positions),
                "diff_positions":  diff_positions,
            }

            # Find closest admin_audit_log entry within ±30 min of bad row timestamp
            try:
                bad_dt  = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                win_lo  = (bad_dt - _td(minutes=30)).isoformat()
                win_hi  = (bad_dt + _td(minutes=30)).isoformat()
            except Exception:
                win_lo = win_hi = ts

            attr = g.db.execute(
                "SELECT id, username, action, entity_type, entity_id, delta_json, timestamp "
                "FROM admin_audit_log "
                "WHERE timestamp BETWEEN ? AND ? "
                "ORDER BY ABS(julianday(timestamp) - julianday(?)) LIMIT 1",
                (win_lo, win_hi, ts),
            ).fetchone()

            if attr:
                tamper_class = "APP-LEVEL"
                try:
                    delta_data = _json2.loads(attr[5]) if attr[5] else {}
                except Exception:
                    delta_data = {}
                attribution = {
                    "id":          attr[0],
                    "username":    attr[1],
                    "action":      attr[2],
                    "entity_type": attr[3],
                    "entity_id":   attr[4],
                    "delta_json":  attr[5],
                    "delta_data":  delta_data,
                    "timestamp":   attr[6],
                }
            else:
                tamper_class = "DB-DIRECT"

    return jsonify({
        "integrity":     integrity,
        "entries":       entries,
        "tainted_count": tainted_count,
        "attribution":   attribution,
        "tamper_detail": tamper_detail,
        "tamper_class":  tamper_class,
    })


@api_bp.route("/audit/log")
@requires_role("ADMIN")
def audit_log():
    """Admin audit log with optional filters."""
    date_from   = request.args.get("date_from",   _days_ago(30))
    date_to     = request.args.get("date_to",     _today())
    username    = request.args.get("username")    or None
    entity_type = request.args.get("entity_type") or None

    rows = admin_audit_report(
        g.db, date_from, date_to,
        username=username, entity_type=entity_type,
    )
    return jsonify(rows)


# ─────────────────────────────────────────────────────────────────────────────
# FR-09  Gate rejection audit
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/audit/rejections")
@requires_role("MANAGER", "ADMIN")
def audit_rejections():
    date_from = request.args.get("date_from", _days_ago(30))
    date_to   = request.args.get("date_to",   _today())
    gate_id   = request.args.get("gate_id")  or None
    rows = gate_rejection_audit(g.db, date_from, date_to, gate_id=gate_id)
    return jsonify(rows)


# ─────────────────────────────────────────────────────────────────────────────
# FR-07  Allowance report export (CSV / PDF)
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/reports/allowance")
@requires_role("MANAGER", "ADMIN")
def report_allowance():
    date_from = request.args.get("date_from", _days_ago(30))
    date_to   = request.args.get("date_to",   _today())
    fmt       = request.args.get("format", "csv").lower()
    rows = personal_vehicle_allowance_report(g.db, date_from, date_to)
    date_range_str = f"{date_from} – {date_to}"
    if fmt == "pdf":
        buf = io.BytesIO()
        export_pdf(rows, buf, title="Personal Vehicle Allowance Report",
                   date_range_str=date_range_str)
        buf.seek(0)
        resp = make_response(buf.read())
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = (
            f'attachment; filename="allowance_{date_from}_{date_to}.pdf"'
        )
        return resp
    # default: CSV
    content = csv_string(rows)
    resp = make_response(content)
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="allowance_{date_from}_{date_to}.csv"'
    )
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# FR-08  OHS compliance report export (CSV / PDF)
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/reports/ohs")
@requires_role("MANAGER", "ADMIN")
def report_ohs():
    fmt  = request.args.get("format", "csv").lower()
    rows = ohs_compliance_report(g.db)
    today = _today()
    if fmt == "pdf":
        buf = io.BytesIO()
        export_pdf(rows, buf, title="OHS Compliance Report",
                   date_range_str=f"Snapshot: {today}")
        buf.seek(0)
        resp = make_response(buf.read())
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = (
            f'attachment; filename="ohs_compliance_{today}.pdf"'
        )
        return resp
    content = csv_string(rows)
    resp = make_response(content)
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="ohs_compliance_{today}.csv"'
    )
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# FR-09  Gate rejection audit export (CSV)
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/reports/rejections")
@requires_role("MANAGER", "ADMIN")
def report_rejections():
    date_from = request.args.get("date_from", _days_ago(30))
    date_to   = request.args.get("date_to",   _today())
    gate_id   = request.args.get("gate_id")  or None
    rows = gate_rejection_audit(g.db, date_from, date_to, gate_id=gate_id)
    content = csv_string(rows)
    resp = make_response(content)
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="gate_rejections_{date_from}_{date_to}.csv"'
    )
    return resp
