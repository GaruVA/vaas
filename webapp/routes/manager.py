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
    db        = g.db
    today     = date.today()
    week_ago  = (today - timedelta(days=7)).isoformat()
    month_ago = today - timedelta(days=30)

    # ---- Core KPIs -------------------------------------------------------
    zones          = zone_occupancy_snapshot(db)
    active_in_yard = sum(z["current_occupancy"] for z in zones)

    events_today = db.execute(
        "SELECT COUNT(*) FROM access_log WHERE DATE(timestamp) = DATE('now')"
    ).fetchone()[0]

    anomaly_count_7d = db.execute(
        "SELECT COUNT(*) FROM access_log "
        "WHERE status IN ('DOUBLE_ENTRY', 'UNMATCHED_EXIT') "
        "AND timestamp >= ?",
        (week_ago,),
    ).fetchone()[0]

    chain = verify_chain(db)

    anomaly_rows = db.execute(
        "SELECT id, plate_number, timestamp, gate_id, direction, status, confidence_score "
        "FROM access_log "
        "WHERE status IN ('DOUBLE_ENTRY', 'UNMATCHED_EXIT') "
        "AND timestamp >= ? "
        "ORDER BY id DESC LIMIT 5",
        (week_ago,),
    ).fetchall()

    # ---- Fuel Allowance Intelligence (last 30 days) ----------------------
    DAILY_ALLOWANCE_LKR = 2678

    # Per driver+plate: eligible on-time entry days vs total access days
    allow_q = db.execute(
        "SELECT u.id, COALESCE(u.full_name, u.username) AS driver_name, "
        "       va.plate_number, "
        "       COUNT(DISTINCT DATE(al.timestamp)) AS eligible_days, "
        "       (SELECT COUNT(DISTINCT DATE(al2.timestamp)) "
        "        FROM access_log al2 "
        "        WHERE al2.plate_number = va.plate_number "
        "          AND al2.direction = 'ENTRY' "
        "          AND DATE(al2.timestamp) BETWEEN ? AND ?) AS access_days "
        "FROM users u "
        "JOIN vehicle_assignments va ON va.user_id = u.id AND va.is_active = 1 "
        "LEFT JOIN access_log al "
        "    ON al.plate_number = va.plate_number "
        "   AND al.direction = 'ENTRY' "
        "   AND al.status IN ('ON_TIME_ENTRY','EARLY_ARRIVAL') "
        "   AND DATE(al.timestamp) BETWEEN ? AND ? "
        "GROUP BY u.id, va.plate_number "
        "ORDER BY eligible_days ASC",
        (month_ago.isoformat(), today.isoformat(),
         month_ago.isoformat(), today.isoformat()),
    ).fetchall()

    drivers = []
    for r in allow_q:
        d = dict(r)
        d["access_days"]     = d["access_days"] or 0
        d["eligible_days"]   = d["eligible_days"] or 0
        d["ineligible_days"] = max(0, d["access_days"] - d["eligible_days"])
        d["compliance_pct"]  = (
            round(d["eligible_days"] / d["access_days"] * 100)
            if d["access_days"] > 0 else 0
        )
        drivers.append(d)

    total_ineligible  = sum(d["ineligible_days"] for d in drivers)
    prevented_leakage = total_ineligible * DAILY_ALLOWANCE_LKR
    total_drivers     = len(drivers)
    band_high = sum(1 for d in drivers if d["compliance_pct"] >= 85)
    band_mid  = sum(1 for d in drivers if 70 <= d["compliance_pct"] < 85)
    band_low  = sum(1 for d in drivers if d["compliance_pct"] < 70)
    watchlist = sorted(
        [d for d in drivers if d["compliance_pct"] < 85],
        key=lambda x: x["compliance_pct"],
    )[:5]

    # ---- OHS Compliance Intelligence ------------------------------------
    ohs_rows       = ohs_compliance_report(db)
    ohs_total      = len(ohs_rows)
    ohs_ok         = sum(1 for r in ohs_rows if r["risk_flag"] == "OK")
    ohs_unassigned = sum(1 for r in ohs_rows if r["risk_flag"] == "UNASSIGNED")
    ohs_medium     = sum(1 for r in ohs_rows if r["risk_flag"] == "MEDIUM_RISK")
    ohs_high       = sum(1 for r in ohs_rows if r["risk_flag"] == "HIGH_RISK")
    ohs_suspended  = sum(1 for r in ohs_rows if r["risk_flag"] == "SUSPENDED")
    ohs_compliance_pct = round(ohs_ok / ohs_total * 100) if ohs_total else 100
    ohs_risk_rows  = [r for r in ohs_rows if r["risk_flag"] != "OK"][:5]

    # ---- Subcontractor Billing Intelligence (last 30 days) --------------
    billing_rows          = subcontractor_billing_audit(
        db, None, month_ago.isoformat(), today.isoformat()
    )
    billing_total         = len(billing_rows)
    billing_flagged       = sum(1 for r in billing_rows if r["trips"] == 0)
    billing_verified      = billing_total - billing_flagged
    billing_integrity_pct = (
        round(billing_verified / billing_total * 100) if billing_total else 100
    )
    billing_total_hours   = round(sum(r["billed_hours"] for r in billing_rows), 1)
    billing_preview       = billing_rows[:6]

    return render_template(
        "manager/home.html",
        # Core KPIs
        active_in_yard        = active_in_yard,
        events_today          = events_today,
        anomaly_count_7d      = anomaly_count_7d,
        chain                 = chain,
        anomaly_rows          = anomaly_rows,
        # Fuel allowance intelligence
        prevented_leakage     = prevented_leakage,
        total_drivers         = total_drivers,
        band_high             = band_high,
        band_mid              = band_mid,
        band_low              = band_low,
        watchlist             = watchlist,
        # OHS intelligence
        ohs_total             = ohs_total,
        ohs_ok                = ohs_ok,
        ohs_unassigned        = ohs_unassigned,
        ohs_medium            = ohs_medium,
        ohs_high              = ohs_high,
        ohs_suspended         = ohs_suspended,
        ohs_compliance_pct    = ohs_compliance_pct,
        ohs_risk_rows         = ohs_risk_rows,
        # Billing intelligence
        billing_total         = billing_total,
        billing_flagged       = billing_flagged,
        billing_verified      = billing_verified,
        billing_integrity_pct = billing_integrity_pct,
        billing_total_hours   = billing_total_hours,
        billing_preview       = billing_preview,
    )


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
    rows = personal_vehicle_allowance_report(g.db, df.isoformat(), dt.isoformat())
    return render_template("manager/personal_allowance.html", rows=rows, df=df, dt=dt)


@manager_bp.route("/reports/gate-rejection-audit")
@requires_role("MANAGER", "ADMIN")
def gate_rejection_audit_view():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    gate_id = request.args.get("gate_id") or None
    rows = gate_rejection_audit(g.db, df.isoformat(), dt.isoformat(), gate_id=gate_id)
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
    rows = admin_audit_report(g.db, df.isoformat(), dt.isoformat(),
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
    rows = subcontractor_billing_audit(g.db, company_id, df.isoformat(), dt.isoformat())
    return render_template("manager/subcontractor_billing.html",
                           rows=rows, df=df, dt=dt, company_id=company_id)


@manager_bp.route("/reports/anomalies")
@requires_role("MANAGER", "ADMIN")
def anomaly_report():
    today = date.today()
    df = _parse_date(request.args.get("from"), today - timedelta(days=30))
    dt = _parse_date(request.args.get("to"),   today + timedelta(days=1))
    gate_id       = request.args.get("gate_id") or None
    status_filter = request.args.get("status")  or None

    statuses = ("DOUBLE_ENTRY", "UNMATCHED_EXIT")
    if status_filter in statuses:
        placeholders = "?"
        params = [status_filter, df.isoformat(), dt.isoformat()]
    else:
        placeholders = "?,?"
        params = list(statuses) + [df.isoformat(), dt.isoformat()]

    sql = (
        "SELECT id, plate_number, timestamp, gate_id, direction, status, confidence_score "
        "FROM access_log "
        f"WHERE status IN ({placeholders}) "
        "AND DATE(timestamp) BETWEEN ? AND ? "
    )
    if gate_id:
        sql += "AND gate_id = ? "
        params.append(gate_id)
    sql += "ORDER BY id DESC"
    rows = g.db.execute(sql, params).fetchall()
    return render_template("manager/anomaly_report.html",
                           rows=rows, df=df, dt=dt,
                           gate_id=gate_id, status_filter=status_filter)


@manager_bp.route("/audit")
@requires_role("MANAGER", "ADMIN")
def audit():
    from src.audit import verify_chain
    db  = g.db
    res = verify_chain(db)
    chain_rows   = db.execute(
        "SELECT id, plate_number, timestamp, gate_id, row_hash "
        "FROM access_log ORDER BY id DESC LIMIT 20"
    ).fetchall()
    tampered_row = None
    cross_ref_log = None
    if not res.ok and res.first_bad_id is not None:
        tampered_row = db.execute(
            "SELECT id, plate_number, timestamp, gate_id, direction, status "
            "FROM access_log WHERE id = ?", (res.first_bad_id,)
        ).fetchone()
        cross_ref_log = db.execute(
            "SELECT id, username, action, entity_type, entity_id, timestamp, delta_json "
            "FROM admin_audit_log "
            "WHERE timestamp >= ? "
            "ORDER BY id DESC LIMIT 1",
            (res.verified_at,),
        ).fetchone()
    audit_log_rows = db.execute(
        "SELECT id, username, action, entity_type, entity_id, delta_json, timestamp "
        "FROM admin_audit_log ORDER BY id DESC LIMIT 50"
    ).fetchall()
    return render_template(
        "manager/audit.html",
        res            = res,
        chain_rows     = chain_rows,
        tampered_row   = tampered_row,
        cross_ref_log  = cross_ref_log,
        audit_log_rows = audit_log_rows,
    )
