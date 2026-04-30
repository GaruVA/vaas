"""Manager blueprint: reports, analytics, exports, audit verify."""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, current_app, render_template, request

from src.analytics import (
    csv_string,
    daily_attendance_report,
    export_pdf,
    gate_throughput_report,
    monthly_attendance_report,
    weekly_attendance_report,
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
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    rows = monthly_attendance_report(current_app.config["VAAS_DB"], year, month)
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


def _rows_for(report_type: str):
    today = date.today()
    db = current_app.config["VAAS_DB"]
    df = _parse_date(request.args.get("from"), today - timedelta(days=7))
    dt = _parse_date(request.args.get("to"), today + timedelta(days=1))
    if report_type == "daily":
        return daily_attendance_report(db, df.isoformat(), dt.isoformat()), "Daily Report"
    if report_type == "weekly":
        ws = _parse_date(request.args.get("week_start"),
                         today - timedelta(days=today.weekday()))
        return weekly_attendance_report(db, ws.isoformat()), "Weekly Report"
    if report_type == "monthly":
        y = int(request.args.get("year", today.year))
        m = int(request.args.get("month", today.month))
        return monthly_attendance_report(db, y, m), f"Monthly Report {y}-{m:02d}"
    if report_type == "gate-throughput":
        return gate_throughput_report(db, df.isoformat(), dt.isoformat()), "Gate Throughput"
    return [], "Report"


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
