"""Manager blueprint: reports, analytics, exports, audit verify."""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, g, render_template, request

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
from webapp.auth import requires_role

manager_bp = Blueprint("manager", __name__, url_prefix="/manager")


def _parse_date(s: str | None, default: date) -> date:
    if not s:
        return default
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return default


@manager_bp.route("/")
@requires_role("MANAGER", "ADMIN")
def home():
    return render_template("manager/home.html")


@manager_bp.route("/reports/ohs")
@requires_role("MANAGER", "ADMIN")
def ohs():
    rows = ohs_compliance_report(g.db)
    return render_template("manager/ohs.html", rows=rows)


def _rows_for(report_type: str):
    today = date.today()
    db    = g.db
    df    = _parse_date(request.args.get("from"), today - timedelta(days=7))
    dt    = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    if report_type == "ohs":
        return ohs_compliance_report(db), "OHS Compliance"
    if report_type == "personal-allowance":
        return personal_vehicle_allowance_report(db, df.isoformat(), dt.isoformat()), "Personal Vehicle Allowance"
    if report_type == "gate-rejection-audit":
        return gate_rejection_audit(db, df.isoformat(), dt.isoformat()), "Gate Rejection Audit"
    if report_type == "admin-audit":
        return admin_audit_report(db, df.isoformat(), dt.isoformat()), "Admin Audit Log"
    if report_type == "zone-occupancy":
        return zone_occupancy_snapshot(db), "Zone Occupancy Snapshot"
    if report_type == "subcontractor":
        company_id = request.args.get("company_id", "")
        return subcontractor_billing_audit(db, company_id, df.isoformat(), dt.isoformat()), "Subcontractor Billing Audit"
    return [], "Report"




@manager_bp.route("/reports/personal-allowance")
@requires_role("MANAGER", "ADMIN")
def personal_allowance():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    rows = personal_vehicle_allowance_report(g.db,
                                             df.isoformat(), dt.isoformat())
    return render_template("manager/personal_allowance.html", rows=rows, df=df, dt=dt)


@manager_bp.route("/reports/gate-rejection-audit")
@requires_role("MANAGER", "ADMIN")
def gate_rejection_audit_view():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    gate_id = request.args.get("gate_id") or None
    rows = gate_rejection_audit(g.db,
                                df.isoformat(), dt.isoformat(), gate_id=gate_id)
    return render_template("manager/gate_rejection_audit.html",
                           rows=rows, df=df, dt=dt, gate_id=gate_id)


@manager_bp.route("/reports/admin-audit")
@requires_role("ADMIN")
def admin_audit_view():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    username    = request.args.get("username")    or None
    entity_type = request.args.get("entity_type") or None
    rows = admin_audit_report(g.db,
                              df.isoformat(), dt.isoformat(),
                              username=username, entity_type=entity_type)
    return render_template("manager/admin_audit.html",
                           rows=rows, df=df, dt=dt,
                           username=username, entity_type=entity_type)


@manager_bp.route("/reports/zone-occupancy")
@requires_role("MANAGER", "ADMIN")
def zone_occupancy_view():
    rows = zone_occupancy_snapshot(g.db)
    return render_template("manager/zone_occupancy.html", rows=rows)


@manager_bp.route("/reports/subcontractor")
@requires_role("MANAGER", "ADMIN")
def subcontractor_billing_view():
    today      = date.today()
    df         = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt         = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    company_id = request.args.get("company_id", "")
    rows = subcontractor_billing_audit(g.db,
                                       company_id, df.isoformat(), dt.isoformat())
    return render_template("manager/subcontractor_billing.html",
                           rows=rows, df=df, dt=dt, company_id=company_id)

@manager_bp.route("/reports/<report_type>/export.csv")
@requires_role("MANAGER", "ADMIN")
def export_csv_route(report_type: str):
    rows, _ = _rows_for(report_type)
    return Response(csv_string(rows), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename={report_type}.csv"})


@manager_bp.route("/reports/<report_type>/export.pdf")
@requires_role("MANAGER", "ADMIN")
def export_pdf_route(report_type: str):
    rows, title = _rows_for(report_type)
    buf = io.BytesIO()
    export_pdf(rows, buf, title=title)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition":
                             f"attachment; filename={report_type}.pdf"})


@manager_bp.route("/audit/verify")
@requires_role("MANAGER", "ADMIN")
def audit():
    res = verify_chain(g.db)
    return render_template("manager/audit.html", res=res)
