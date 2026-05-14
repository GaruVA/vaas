"""Admin blueprint: vehicle / shift / user CRUD + vehicle assignments."""
from __future__ import annotations

import json

import bcrypt
from flask import (
    Blueprint, g, flash, redirect, render_template,
    request, session, url_for,
)

from src.analytics import zone_occupancy_snapshot
from src.database import VEHICLE_CATEGORIES, VEHICLE_TYPES, transaction
from webapp.auth import requires_role

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ── Audit helper ─────────────────────────────────────────────────────────────

def _audit(conn, action: str, entity_type: str, entity_id: str,
           details: dict | None = None) -> None:
    """Write a row to admin_audit_log using the current session user."""
    try:
        conn.execute(
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
        pass   # audit must never block the main operation


# ── Home ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/")
@requires_role("ADMIN")
def home():
    return render_template("admin/home.html")


# ── Vehicles ──────────────────────────────────────────────────────────────────

@admin_bp.route("/vehicles")
@requires_role("ADMIN")
def vehicles():
    db   = g.db
    rows = db.execute("""
        SELECT rv.*,
               va.user_id            AS assigned_user_id,
               u.username            AS assigned_username,
               COALESCE(u.full_name, u.username) AS assigned_driver_name
        FROM registered_vehicles rv
        LEFT JOIN vehicle_assignments va
             ON rv.plate_number = va.plate_number AND va.is_active = 1
        LEFT JOIN users u ON va.user_id = u.id
        ORDER BY rv.plate_number
    """).fetchall()
    return render_template("admin/vehicles.html", rows=rows)


@admin_bp.route("/vehicles/new", methods=["GET", "POST"])
@requires_role("ADMIN")
def new_vehicle():
    db     = g.db
    shifts = db.execute("SELECT shift_id, shift_name FROM shifts").fetchall()
    users  = db.execute("SELECT id, username, COALESCE(full_name,username) AS display "
                        "FROM users ORDER BY username").fetchall()

    if request.method == "POST":
        plate      = (request.form.get("plate_number") or "").strip().upper()
        cat        = request.form.get("vehicle_category", "CONTRACTOR")
        vtype      = request.form.get("vehicle_type", "CAR")
        contractor = request.form.get("contractor_name") or None
        dept       = request.form.get("department") or None
        make_model = request.form.get("make_model") or None
        shift_id   = request.form.get("shift_id")   or None
        user_id    = request.form.get("user_id")    or None
        notes      = request.form.get("notes")      or None

        if cat not in VEHICLE_CATEGORIES:
            cat = "CONTRACTOR"
        if vtype not in VEHICLE_TYPES:
            vtype = "CAR"

        with transaction(db) as cur:
            cur.execute(
                "INSERT OR REPLACE INTO registered_vehicles "
                "(plate_number,vehicle_category,vehicle_type,contractor_name,"
                " department,make_model,registration_status,notes) "
                "VALUES (?,?,?,?,?,?,'ACTIVE',?)",
                (plate, cat, vtype, contractor, dept, make_model, notes),
            )
            if shift_id:
                cur.execute("DELETE FROM vehicle_shifts WHERE plate_number=?", (plate,))
                cur.execute("INSERT INTO vehicle_shifts VALUES (?,?)", (plate, shift_id))
            if user_id:
                cur.execute(
                    "UPDATE vehicle_assignments SET is_active=0 WHERE plate_number=?",
                    (plate,),
                )
                cur.execute(
                    "INSERT INTO vehicle_assignments (plate_number,user_id) VALUES (?,?)",
                    (plate, int(user_id)),
                )

        _audit(db, "CREATE", "VEHICLE", plate,
               {"category": cat, "type": vtype, "department": dept})
        flash(f"Saved vehicle {plate}", "success")
        return redirect(url_for("admin.vehicles"))

    prefilled = request.args.get("plate", "")
    return render_template("admin/vehicle_form.html",
                           shifts=shifts, users=users,
                           prefilled=prefilled,
                           categories=VEHICLE_CATEGORIES,
                           vtypes=VEHICLE_TYPES)


@admin_bp.route("/vehicles/<plate>/edit", methods=["GET", "POST"])
@requires_role("ADMIN")
def edit_vehicle(plate: str):
    db     = g.db
    shifts = db.execute("SELECT shift_id, shift_name FROM shifts").fetchall()
    users  = db.execute("SELECT id, username, COALESCE(full_name,username) AS display "
                        "FROM users ORDER BY username").fetchall()
    vehicle = db.execute(
        "SELECT * FROM registered_vehicles WHERE plate_number=?", (plate,)
    ).fetchone()
    if not vehicle:
        flash("Vehicle not found", "danger")
        return redirect(url_for("admin.vehicles"))

    current_shift = db.execute(
        "SELECT shift_id FROM vehicle_shifts WHERE plate_number=?", (plate,)
    ).fetchone()
    current_user = db.execute(
        "SELECT user_id FROM vehicle_assignments WHERE plate_number=? AND is_active=1",
        (plate,),
    ).fetchone()

    if request.method == "POST":
        cat        = request.form.get("vehicle_category", "CONTRACTOR")
        vtype      = request.form.get("vehicle_type", "CAR")
        contractor = request.form.get("contractor_name") or None
        dept       = request.form.get("department") or None
        make_model = request.form.get("make_model") or None
        shift_id   = request.form.get("shift_id")   or None
        user_id    = request.form.get("user_id")    or None
        notes      = request.form.get("notes")      or None

        if cat   not in VEHICLE_CATEGORIES: cat   = "CONTRACTOR"
        if vtype not in VEHICLE_TYPES:      vtype = "CAR"

        with transaction(db) as cur:
            cur.execute(
                "UPDATE registered_vehicles SET vehicle_category=?,vehicle_type=?,"
                "contractor_name=?,department=?,make_model=?,notes=? "
                "WHERE plate_number=?",
                (cat, vtype, contractor, dept, make_model, notes, plate),
            )
            cur.execute("DELETE FROM vehicle_shifts WHERE plate_number=?", (plate,))
            if shift_id:
                cur.execute("INSERT INTO vehicle_shifts VALUES (?,?)", (plate, shift_id))
            # Only update assignment if changed
            if user_id:
                old_uid = current_user["user_id"] if current_user else None
                if old_uid != int(user_id):
                    cur.execute(
                        "UPDATE vehicle_assignments SET is_active=0 WHERE plate_number=?",
                        (plate,),
                    )
                    cur.execute(
                        "INSERT INTO vehicle_assignments (plate_number,user_id) VALUES (?,?)",
                        (plate, int(user_id)),
                    )
            elif current_user:
                # Explicitly cleared
                cur.execute(
                    "UPDATE vehicle_assignments SET is_active=0 WHERE plate_number=?",
                    (plate,),
                )

        _audit(db, "UPDATE", "VEHICLE", plate,
               {"category": cat, "type": vtype, "department": dept})
        flash(f"Updated vehicle {plate}", "success")
        return redirect(url_for("admin.vehicles"))

    return render_template("admin/vehicle_form.html",
                           shifts=shifts, users=users,
                           prefilled=plate,
                           vehicle=vehicle,
                           current_shift=current_shift["shift_id"] if current_shift else None,
                           current_user_id=current_user["user_id"] if current_user else None,
                           categories=VEHICLE_CATEGORIES,
                           vtypes=VEHICLE_TYPES,
                           editing=True)


@admin_bp.route("/vehicles/<plate>/status", methods=["POST"])
@requires_role("ADMIN")
def update_status(plate: str):
    new_status = request.form.get("status", "ACTIVE")
    if new_status not in ("ACTIVE", "SUSPENDED", "EXPIRED"):
        return "bad status", 400
    db = g.db
    with transaction(db) as cur:
        cur.execute(
            "UPDATE registered_vehicles SET registration_status=? WHERE plate_number=?",
            (new_status, plate),
        )
    _audit(db, "UPDATE", "VEHICLE", plate, {"registration_status": new_status})
    flash(f"{plate} → {new_status}", "info")
    return redirect(url_for("admin.vehicles"))


@admin_bp.route("/vehicles/<plate>/delete", methods=["POST"])
@requires_role("ADMIN")
def delete_vehicle(plate: str):
    db = g.db
    with transaction(db) as cur:
        cur.execute("DELETE FROM registered_vehicles WHERE plate_number=?", (plate,))
    _audit(db, "DELETE", "VEHICLE", plate)
    flash(f"Deleted {plate}", "warning")
    return redirect(url_for("admin.vehicles"))


# ── Shifts ────────────────────────────────────────────────────────────────────

@admin_bp.route("/shifts")
@requires_role("ADMIN")
def shifts():
    rows = g.db.execute(
        "SELECT * FROM shifts ORDER BY shift_id"
    ).fetchall()
    return render_template("admin/shifts.html", rows=rows)


@admin_bp.route("/shifts/new", methods=["GET", "POST"])
@requires_role("ADMIN")
def new_shift():
    if request.method == "POST":
        sid   = request.form["shift_id"].strip().upper()
        name  = request.form["shift_name"]
        start = request.form["start_time"]
        end   = request.form["end_time"]
        days  = request.form.getlist("days")
        gates = request.form.getlist("gates")
        grace = int(request.form.get("grace_period_minutes") or 10)
        db = g.db
        with transaction(db) as cur:
            cur.execute(
                "INSERT OR REPLACE INTO shifts VALUES (?,?,?,?,?,?,?)",
                (sid, name, start, end, json.dumps(days), json.dumps(gates), grace),
            )
        _audit(db, "CREATE", "SHIFT", sid)
        flash(f"Saved shift {sid}", "success")
        return redirect(url_for("admin.shifts"))
    return render_template("admin/shift_form.html")


@admin_bp.route("/shifts/<sid>/delete", methods=["POST"])
@requires_role("ADMIN")
def delete_shift(sid: str):
    db = g.db
    with transaction(db) as cur:
        cur.execute("DELETE FROM shifts WHERE shift_id=?", (sid,))
    _audit(db, "DELETE", "SHIFT", sid)
    flash(f"Deleted {sid}", "warning")
    return redirect(url_for("admin.shifts"))


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/users")
@requires_role("ADMIN")
def users():
    rows = g.db.execute(
        "SELECT id, username, full_name, role, last_login FROM users ORDER BY username"
    ).fetchall()
    return render_template("admin/users.html", rows=rows)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@requires_role("ADMIN")
def new_user():
    if request.method == "POST":
        u    = request.form["username"].strip()
        fn   = request.form.get("full_name", "").strip() or None
        p    = request.form["password"]
        role = request.form.get("role", "OPERATOR")
        if role not in ("ADMIN", "MANAGER", "OPERATOR"):
            return "bad role", 400
        h  = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
        db = g.db
        with transaction(db) as cur:
            cur.execute(
                "INSERT INTO users (username,full_name,password_hash,role) VALUES (?,?,?,?)",
                (u, fn, h, role),
            )
        _audit(db, "CREATE", "USER", u, {"role": role})
        flash(f"Created user {u}", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html")


@admin_bp.route("/users/<int:uid>/reset", methods=["POST"])
@requires_role("ADMIN")
def reset_password(uid: int):
    p  = request.form["password"]
    h  = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
    db = g.db
    with transaction(db) as cur:
        cur.execute("UPDATE users SET password_hash=? WHERE id=?", (h, uid))
    _audit(db, "UPDATE", "USER", str(uid), {"action": "password_reset"})
    flash("Password reset", "success")
    return redirect(url_for("admin.users"))


# ── Zone Capacity Dashboard ───────────────────────────────────────────────────

@admin_bp.route("/zones")
@requires_role("ADMIN")
def zones():
    """Zone capacity grid: raw cdl_zones + live occupancy snapshot merged."""
    db         = g.db
    zones_raw  = db.execute("SELECT * FROM cdl_zones ORDER BY zone_id").fetchall()
    snap_by_id = {z["zone_id"]: z for z in zone_occupancy_snapshot(db)}
    rows = []
    for z in zones_raw:
        try:
            gates = json.loads(z["associated_gates"]) if z["associated_gates"] else []
        except (ValueError, TypeError):
            gates = []
        snap = snap_by_id.get(z["zone_id"], {})
        cap  = z["vehicle_capacity"] or 1
        cur  = snap.get("current_occupancy", 0)
        rows.append({
            "zone_id":           z["zone_id"],
            "zone_name":         z["zone_name"],
            "zone_type":         z["zone_type"],
            "associated_gates":  gates,
            "vehicle_capacity":  cap,
            "current_occupancy": cur,
            "utilisation_pct":   round(cur / cap * 100, 1),
        })
    return render_template("admin/zones.html", rows=rows)


# ── Admin audit log viewer ────────────────────────────────────────────────────

@admin_bp.route("/audit-log")
@requires_role("ADMIN")
def audit_log():
    rows = g.db.execute(
        "SELECT * FROM admin_audit_log ORDER BY timestamp DESC LIMIT 500"
    ).fetchall()
    return render_template("admin/audit_log.html", rows=rows)

