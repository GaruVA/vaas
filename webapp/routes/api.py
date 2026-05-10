"""JSON API endpoints used by SSE/AJAX."""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from webapp.auth import requires_role

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/recent")
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def recent():
    rows = g.db.execute(
        "SELECT id,plate_number,timestamp,gate_id,direction,status,confidence_score "
        "FROM access_log ORDER BY id DESC LIMIT 20"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@api_bp.route("/pending")
@requires_role("OPERATOR", "MANAGER", "ADMIN")
def pending():
    rows = g.db.execute(
        "SELECT id,plate_number,timestamp,gate_id,confidence_score "
        "FROM access_log WHERE status='VISITOR' ORDER BY id DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])
