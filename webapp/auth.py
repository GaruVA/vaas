"""Session auth, bcrypt password hashing, role decorators (§5.7)."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps

import bcrypt
from flask import (
    Blueprint, current_app, flash, redirect, render_template, request,
    session, url_for,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

ROLE_RANK = {"OPERATOR": 1, "MANAGER": 2, "ADMIN": 3}


def requires_role(*allowed: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login", next=request.path))
            user_role = session.get("role", "")
            user_rank = ROLE_RANK.get(user_role, 0)
            min_rank = min(ROLE_RANK[r] for r in allowed)
            if user_rank < min_rank:
                return ("Forbidden — role required: " + " or ".join(allowed)), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        conn = current_app.config["VAAS_DB"]
        row = conn.execute(
            "SELECT id, password_hash, role FROM users WHERE username=?",
            (username,),
        ).fetchone()
        if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            session.permanent = True
            session["user_id"] = row["id"]
            session["username"] = username
            session["role"] = row["role"]
            conn.execute("UPDATE users SET last_login=? WHERE id=?",
                         (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                          row["id"]))
            nxt = request.args.get("next") or url_for("index")
            return redirect(nxt)
        flash("Invalid credentials", "danger")
    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
