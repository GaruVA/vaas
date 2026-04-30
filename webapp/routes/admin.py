"""Admin blueprint: vehicle / shift / user CRUD."""
from __future__ import annotations

import json

import bcrypt
from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, url_for,
)

from src.database import transaction
from webapp.auth import requires_role

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@requires_role("ADMIN")
def home():
    return render_template("admin/home.html")


# -------------------------- Vehicles --------------------------------------
@admin_bp.route("/vehicles")
@requires_role("ADMIN")
def vehicles():
    rows = current_app.config["VAAS_DB"].execute(
        "SELECT * FROM registered_vehicles ORDER BY plate_number"
    ).fetchall()
    return render_template("admin/vehicles.html", rows=rows)


@admin_bp.route("/vehicles/new", methods=["GET", "POST"])
@requires_role("ADMIN")
def new_vehicle():
    db = current_app.config["VAAS_DB"]
    shifts = db.execute("SELECT shift_id, shift_name FROM shifts").fetchall()
    if request.method == "POST":
        plate = (request.form.get("plate_number") or "").strip().upper()
        cat = request.form.get("vehicle_category", "CONTRACTOR")
        contractor = request.form.get("contractor_name") or None
        shift_id = request.form.get("shift_id") or None
        with transaction(db) as cur:
            cur.execute(
                "INSERT OR REPLACE INTO registered_vehicles "
                "(plate_number,vehicle_category,contractor_name,registration_status) "
                "VALUES (?,?,?,'ACTIVE')",
                (plate, cat, contractor),
            )
            if shift_id:
                cur.execute("DELETE FROM vehicle_shifts WHERE plate_number=?",
                            (plate,))
                cur.execute("INSERT INTO vehicle_shifts VALUES (?,?)",
                            (plate, shift_id))
        flash(f"Saved vehicle {plate}", "success")
        return redirect(url_for("admin.vehicles"))
    prefilled = request.args.get("plate", "")
    return render_template("admin/vehicle_form.html", shifts=shifts,
                           prefilled=prefilled)


@admin_bp.route("/vehicles/<plate>/status", methods=["POST"])
@requires_role("ADMIN")
def update_status(plate: str):
    new = request.form.get("status", "ACTIVE")
    if new not in ("ACTIVE", "SUSPENDED", "EXPIRED"):
        return "bad status", 400
    db = current_app.config["VAAS_DB"]
    with transaction(db) as cur:
        cur.execute(
            "UPDATE registered_vehicles SET registration_status=? WHERE plate_number=?",
            (new, plate),
        )
    flash(f"{plate} -> {new}", "info")
    return redirect(url_for("admin.vehicles"))


@admin_bp.route("/vehicles/<plate>/delete", methods=["POST"])
@requires_role("ADMIN")
def delete_vehicle(plate: str):
    db = current_app.config["VAAS_DB"]
    with transaction(db) as cur:
        cur.execute("DELETE FROM registered_vehicles WHERE plate_number=?", (plate,))
    flash(f"Deleted {plate}", "warning")
    return redirect(url_for("admin.vehicles"))


# -------------------------- Shifts ----------------------------------------
@admin_bp.route("/shifts")
@requires_role("ADMIN")
def shifts():
    rows = current_app.config["VAAS_DB"].execute(
        "SELECT * FROM shifts ORDER BY shift_id"
    ).fetchall()
    return render_template("admin/shifts.html", rows=rows)


@admin_bp.route("/shifts/new", methods=["GET", "POST"])
@requires_role("ADMIN")
def new_shift():
    if request.method == "POST":
        sid = request.form["shift_id"].strip().upper()
        name = request.form["shift_name"]
        start = request.form["start_time"]
        end = request.form["end_time"]
        days = request.form.getlist("days")
        gates = request.form.getlist("gates")
        grace = int(request.form.get("grace_period_minutes") or 10)
        db = current_app.config["VAAS_DB"]
        with transaction(db) as cur:
            cur.execute(
                "INSERT OR REPLACE INTO shifts VALUES (?,?,?,?,?,?,?)",
                (sid, name, start, end, json.dumps(days), json.dumps(gates), grace),
            )
        flash(f"Saved shift {sid}", "success")
        return redirect(url_for("admin.shifts"))
    return render_template("admin/shift_form.html")


@admin_bp.route("/shifts/<sid>/delete", methods=["POST"])
@requires_role("ADMIN")
def delete_shift(sid: str):
    db = current_app.config["VAAS_DB"]
    with transaction(db) as cur:
        cur.execute("DELETE FROM shifts WHERE shift_id=?", (sid,))
    flash(f"Deleted {sid}", "warning")
    return redirect(url_for("admin.shifts"))


# -------------------------- Users -----------------------------------------
@admin_bp.route("/users")
@requires_role("ADMIN")
def users():
    rows = current_app.config["VAAS_DB"].execute(
        "SELECT id, username, role, last_login FROM users ORDER BY username"
    ).fetchall()
    return render_template("admin/users.html", rows=rows)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@requires_role("ADMIN")
def new_user():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"]
        r = request.form.get("role", "OPERATOR")
        if r not in ("ADMIN", "MANAGER", "OPERATOR"):
            return "bad role", 400
        h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
        db = current_app.config["VAAS_DB"]
        with transaction(db) as cur:
            cur.execute(
                "INSERT INTO users (username,password_hash,role) VALUES (?,?,?)",
                (u, h, r),
            )
        flash(f"Created user {u}", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html")


@admin_bp.route("/users/<int:uid>/reset", methods=["POST"])
@requires_role("ADMIN")
def reset_password(uid: int):
    p = request.form["password"]
    h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
    db = current_app.config["VAAS_DB"]
    with transaction(db) as cur:
        cur.execute("UPDATE users SET password_hash=? WHERE id=?", (h, uid))
    flash("Password reset", "success")
    return redirect(url_for("admin.users"))
