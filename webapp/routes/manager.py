"""Manager blueprint: reports, analytics, exports, audit verify."""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, current_app, render_template, request

from src.analytics import (
    absence_report,
    absence_summary,
    admin_audit_report,
    csv_string,
    daily_attendance_report,
    dashboard_stats,
    export_pdf,
    gate_rejection_audit,
    gate_throughput_report,
    monthly_attendance_report,
    ohs_compliance_report,
    payroll_report,
    personal_vehicle_allowance_report,
    rejections_report,
    subcontractor_billing_audit,
    weekly_attendance_report,
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
    stats = dashboard_stats(current_app.config["VAAS_DB"])
    return render_template("manager/home.html", stats=stats)


@manager_bp.route("/reports/daily")
@requires_role("MANAGER", "ADMIN")
def daily():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=7))
    dt = _parse_date(request.args.get("to"), today + timedelta(days=1))
    rows = daily_attendance_report(current_app.config["VAAS_DB"],
                                   df.isoformat(), dt.isoformat())
    return render_template("manager/daily.html", rows=rows, df=df, dt=dt)


@manager_bp.route("/reports/weekly")
@requires_role("MANAGER", "ADMIN")
def weekly():
    today = date.today()
    week_start = _parse_date(request.args.get("week_start"),
                             today - timedelta(days=today.weekday()))
    rows = weekly_attendance_report(current_app.config["VAAS_DB"],
                                    week_start.isoformat())
    return render_template("manager/weekly.html", rows=rows, week_start=week_start)


@manager_bp.route("/reports/monthly")
@requires_role("MANAGER", "ADMIN")
def monthly():
    today = date.today()
    year  = int(request.args.get("year",  today.year))
    month = int(request.args.get("month", today.month))
    rows  = monthly_attendance_report(current_app.config["VAAS_DB"], year, month)
    return render_template("manager/monthly.html", rows=rows, year=year, month=month)


@manager_bp.route("/reports/gate-throughput")
@requires_role("MANAGER", "ADMIN")
def gate_throughput():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=7))
    dt = _parse_date(request.args.get("to"), today + timedelta(days=1))
    rows = gate_throughput_report(current_app.config["VAAS_DB"],
                                  df.isoformat(), dt.isoformat())
    return render_template("manager/gate_throughput.html", rows=rows, df=df, dt=dt)


@manager_bp.route("/reports/absence")
@requires_role("MANAGER", "ADMIN")
def absence():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    db = current_app.config["VAAS_DB"]

    # Single DB round-trip; derive summary from detail rows in Python
    detail_rows  = absence_report(db, df.isoformat(), dt.isoformat())
    summary_rows = absence_summary(db, df.isoformat(), dt.isoformat(),
                                   _detail=detail_rows)

    return render_template("manager/absence.html",
                           summary_rows=summary_rows,
                           detail_rows=detail_rows,
                           df=df, dt=dt)


@manager_bp.route("/reports/payroll")
@requires_role("MANAGER", "ADMIN")
def payroll():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    rows = payroll_report(current_app.config["VAAS_DB"],
                          df.isoformat(), dt.isoformat())
    return render_template("manager/payroll.html", rows=rows, df=df, dt=dt)


@manager_bp.route("/reports/ohs")
@requires_role("MANAGER", "ADMIN")
def ohs():
    rows = ohs_compliance_report(current_app.config["VAAS_DB"])
    return render_template("manager/ohs.html", rows=rows)



@manager_bp.route("/reports/rejections")
@requires_role("MANAGER", "ADMIN")
def rejections():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    rows = rejections_report(current_app.config["VAAS_DB"],
                             df.isoformat(), dt.isoformat())
    return render_template("manager/rejections.html", rows=rows, df=df, dt=dt)


def _rows_for(report_type: str):
    today = date.today()
    db    = current_app.config["VAAS_DB"]
    df    = _parse_date(request.args.get("from"), today - timedelta(days=7))
    dt    = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    if report_type == "daily":
        return daily_attendance_report(db, df.isoformat(), dt.isoformat()), "Daily Report"
    if report_type == "weekly":
        ws = _parse_date(request.args.get("week_start"),
                         today - timedelta(days=today.weekday()))
        return weekly_attendance_report(db, ws.isoformat()), "Weekly Report"
    if report_type == "monthly":
        y = int(request.args.get("year",  today.year))
        m = int(request.args.get("month", today.month))
        return monthly_attendance_report(db, y, m), f"Monthly Report {y}-{m:02d}"
    if report_type == "gate-throughput":
        return gate_throughput_report(db, df.isoformat(), dt.isoformat()), "Gate Throughput"
    if report_type == "absence-summary":
        return absence_summary(db, df.isoformat(), dt.isoformat()), "Absence Summary"
    if report_type == "absence-detail":
        return absence_report(db, df.isoformat(), dt.isoformat()), "Absence Detail"
    if report_type == "payroll":
        return payroll_report(db, df.isoformat(), dt.isoformat()), "Payroll Summary"
    if report_type == "rejections":
        return rejections_report(db, df.isoformat(), dt.isoformat()), "Gate Rejections"
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
    rows = personal_vehicle_allowance_report(current_app.config["VAAS_DB"],
                                             df.isoformat(), dt.isoformat())
    return render_template("manager/personal_allowance.html", rows=rows, df=df, dt=dt)


@manager_bp.route("/reports/gate-rejection-audit")
@requires_role("MANAGER", "ADMIN")
def gate_rejection_audit_view():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    gate_id = request.args.get("gate_id") or None
    rows = gate_rejection_audit(current_app.config["VAAS_DB"],
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
    rows = admin_audit_report(current_app.config["VAAS_DB"],
                              df.isoformat(), dt.isoformat(),
                              username=username, entity_type=entity_type)
    return render_template("manager/admin_audit.html",
                           rows=rows, df=df, dt=dt,
                           username=username, entity_type=entity_type)


@manager_bp.route("/reports/zone-occupancy")
@requires_role("MANAGER", "ADMIN")
def zone_occupancy_view():
    rows = zone_occupancy_snapshot(current_app.config["VAAS_DB"])
    return render_template("manager/zone_occupancy.html", rows=rows)


@manager_bp.route("/reports/subcontractor")
@requires_role("MANAGER", "ADMIN")
def subcontractor_billing_view():
    today      = date.today()
    df         = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt         = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    company_id = request.args.get("company_id", "")
    rows = subcontractor_billing_audit(current_app.config["VAAS_DB"],
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
    res = verify_chain(current_app.config["VAAS_DB"])
    return render_template("manager/audit.html", res=res)
