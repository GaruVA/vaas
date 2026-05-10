from __future__ import annotations

"""Analytics -- 10 named report functions + 3 helpers.

Report functions (10)
---------------------
1.  personal_vehicle_allowance_report
2.  ohs_compliance_report           -- LEFT JOIN, non-compliant first
3.  gate_rejection_audit
4.  admin_audit_report
5.  daily_attendance_report
6.  weekly_attendance_report
7.  monthly_attendance_report
8.  gate_throughput_report
9.  zone_occupancy_snapshot
10. subcontractor_billing_audit

Helpers (3)
-----------
csv_string(rows)           -> str
export_csv(rows, fp)       -> None
export_pdf(rows, fp, title, date_range_str) -> None   (ReportLab)

References: section 6.8 of BUILD_SPEC.md
"""

import csv
import io
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import IO

from src.config import CDL_FUN_BLUE, CDL_YELLOW, CDL_SAFETY_GRN

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Personal vehicle allowance report
# ---------------------------------------------------------------------------

def personal_vehicle_allowance_report(
    conn,
    date_from: str,
    date_to: str,
    driver_user_id: int | None = None,
) -> list[dict]:
    """Daily allowance eligibility per driver based on on-time entry records.

    A driver is eligible for their personal vehicle allowance on a given day
    if they have at least one ON_TIME_ENTRY or EARLY_ARRIVAL record in the
    access_log for a vehicle assigned to them.

    Returns one row per (user_id, plate_number, date) triple.
    """
    sql = """
        SELECT
            u.id                                    AS user_id,
            u.username,
            u.full_name,
            va.plate_number,
            DATE(al.timestamp)                      AS event_date,
            COUNT(al.id)                            AS on_time_entries,
            CASE WHEN COUNT(al.id) > 0 THEN 1 ELSE 0 END AS eligible
        FROM users u
        JOIN vehicle_assignments va
            ON va.user_id = u.id AND va.is_active = 1
        LEFT JOIN access_log al
            ON al.plate_number = va.plate_number
            AND al.direction = 'ENTRY'
            AND al.status IN ('ON_TIME_ENTRY', 'EARLY_ARRIVAL')
            AND DATE(al.timestamp) BETWEEN ? AND ?
        WHERE 1=1
    """
    params: list = [date_from, date_to]
    if driver_user_id is not None:
        sql += " AND u.id = ?"
        params.append(driver_user_id)
    sql += " GROUP BY u.id, va.plate_number, DATE(al.timestamp) ORDER BY event_date, u.username"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 2. OHS compliance report
# ---------------------------------------------------------------------------

def ohs_compliance_report(conn) -> list[dict]:
    """Driver assignment coverage, overstay flags, and vehicle status.

    Uses LEFT JOIN so every registered vehicle appears, even those with
    zero access_log events (the LEFT JOIN test is a required assertion).

    Returns vehicles ordered non-compliant first.
    """
    rows = conn.execute(
        """
        SELECT
            rv.plate_number,
            rv.vehicle_category,
            rv.registration_status,
            rv.contractor_name,
            rv.department,
            va.user_id,
            u.username                          AS assigned_driver,
            COUNT(al.id)                        AS total_events,
            SUM(CASE WHEN al.status = 'OVERSTAY' THEN 1 ELSE 0 END) AS overstay_count,
            CASE
                WHEN rv.registration_status != 'ACTIVE' THEN 0
                WHEN va.user_id IS NULL THEN 0
                ELSE 1
            END AS is_compliant
        FROM registered_vehicles rv
        LEFT JOIN vehicle_assignments va
            ON va.plate_number = rv.plate_number AND va.is_active = 1
        LEFT JOIN users u
            ON u.id = va.user_id
        LEFT JOIN access_log al
            ON al.plate_number = rv.plate_number
        GROUP BY rv.plate_number
        ORDER BY is_compliant ASC, overstay_count DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 3. Gate rejection audit
# ---------------------------------------------------------------------------

def gate_rejection_audit(
    conn,
    date_from: str,
    date_to: str,
    gate_id: str | None = None,
) -> list[dict]:
    """Post-incident audit trail of gate rejections."""
    sql = """
        SELECT
            gr.id,
            gr.plate_number,
            gr.timestamp,
            gr.gate_id,
            gr.reason,
            gr.confidence_score,
            rv.registration_status
        FROM gate_rejections gr
        LEFT JOIN registered_vehicles rv ON rv.plate_number = gr.plate_number
        WHERE DATE(gr.timestamp) BETWEEN ? AND ?
    """
    params: list = [date_from, date_to]
    if gate_id:
        sql += " AND gr.gate_id = ?"
        params.append(gate_id)
    sql += " ORDER BY gr.timestamp DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 4. Admin audit report
# ---------------------------------------------------------------------------

def admin_audit_report(
    conn,
    date_from: str,
    date_to: str,
    username: str | None = None,
    entity_type: str | None = None,
) -> list[dict]:
    """Administrative action trail from admin_audit_log."""
    sql = """
        SELECT *
        FROM admin_audit_log
        WHERE DATE(timestamp) BETWEEN ? AND ?
    """
    params: list = [date_from, date_to]
    if username:
        sql += " AND username = ?"
        params.append(username)
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    sql += " ORDER BY timestamp DESC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 5. Daily attendance report
# ---------------------------------------------------------------------------

def daily_attendance_report(conn, date: str) -> list[dict]:
    """Per-vehicle breakdown for a single calendar date."""
    rows = conn.execute(
        """
        SELECT
            rv.plate_number,
            rv.vehicle_category,
            rv.registration_status,
            rv.contractor_name,
            COUNT(al.id)                                        AS total_events,
            SUM(CASE WHEN al.status = 'ON_TIME_ENTRY'  THEN 1 ELSE 0 END) AS on_time,
            SUM(CASE WHEN al.status = 'LATE_ARRIVAL'   THEN 1 ELSE 0 END) AS late,
            SUM(CASE WHEN al.status = 'EARLY_ARRIVAL'  THEN 1 ELSE 0 END) AS early,
            COALESCE(MAX(al.dwell_time_seconds), 0)             AS max_dwell_seconds,
            CASE WHEN COUNT(al.id) > 0 THEN 1 ELSE 0 END       AS present
        FROM registered_vehicles rv
        LEFT JOIN access_log al
            ON al.plate_number = rv.plate_number
            AND DATE(al.timestamp) = ?
        GROUP BY rv.plate_number
        ORDER BY rv.plate_number
        """,
        (date,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 6. Weekly attendance report
# ---------------------------------------------------------------------------

def weekly_attendance_report(conn, week_start_date: str) -> list[dict]:
    """Weekly aggregation starting from week_start_date (7 days)."""
    start = datetime.strptime(week_start_date, "%Y-%m-%d").date()
    end   = start + timedelta(days=6)
    rows = conn.execute(
        """
        SELECT
            rv.plate_number,
            rv.vehicle_category,
            COUNT(DISTINCT DATE(al.timestamp))  AS days_present,
            SUM(CASE WHEN al.status IN ('ON_TIME_ENTRY','EARLY_ARRIVAL') THEN 1 ELSE 0 END) AS on_time_count,
            SUM(CASE WHEN al.status = 'LATE_ARRIVAL' THEN 1 ELSE 0 END) AS late_count,
            COALESCE(SUM(al.dwell_time_seconds)/3600.0, 0)               AS total_hours
        FROM registered_vehicles rv
        LEFT JOIN access_log al
            ON al.plate_number = rv.plate_number
            AND DATE(al.timestamp) BETWEEN ? AND ?
        GROUP BY rv.plate_number
        ORDER BY rv.plate_number
        """,
        (str(start), str(end)),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 7. Monthly attendance report
# ---------------------------------------------------------------------------

def monthly_attendance_report(conn, year: int, month: int) -> list[dict]:
    """Month-level summaries with average dwell times."""
    month_str = f"{year:04d}-{month:02d}"
    rows = conn.execute(
        """
        SELECT
            rv.plate_number,
            rv.vehicle_category,
            COUNT(DISTINCT DATE(al.timestamp))               AS days_present,
            COUNT(al.id)                                     AS total_events,
            COALESCE(AVG(al.dwell_time_seconds)/3600.0, 0)  AS avg_dwell_hours,
            COALESCE(SUM(al.dwell_time_seconds)/3600.0, 0)  AS total_hours
        FROM registered_vehicles rv
        LEFT JOIN access_log al
            ON al.plate_number = rv.plate_number
            AND strftime('%Y-%m', al.timestamp) = ?
        GROUP BY rv.plate_number
        ORDER BY rv.plate_number
        """,
        (month_str,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 8. Gate throughput report
# ---------------------------------------------------------------------------

def gate_throughput_report(conn, date_from: str, date_to: str) -> list[dict]:
    """Hourly and daily vehicle counts per gate."""
    rows = conn.execute(
        """
        SELECT
            gate_id,
            DATE(timestamp)                         AS event_date,
            strftime('%H', timestamp)               AS hour,
            direction,
            COUNT(id)                               AS vehicle_count,
            COALESCE(AVG(dwell_time_seconds), 0)    AS avg_dwell_seconds
        FROM access_log
        WHERE DATE(timestamp) BETWEEN ? AND ?
        GROUP BY gate_id, DATE(timestamp), strftime('%H', timestamp), direction
        ORDER BY gate_id, event_date, hour
        """,
        (date_from, date_to),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 9. Zone occupancy snapshot
# ---------------------------------------------------------------------------

def zone_occupancy_snapshot(conn) -> list[dict]:
    """Real-time vehicle headcount across all CDL zones."""
    zones = conn.execute("SELECT * FROM cdl_zones ORDER BY zone_id").fetchall()
    results: list[dict] = []
    for zone in zones:
        zone_id   = zone["zone_id"]
        zone_name = zone["zone_name"]
        zone_type = zone["zone_type"]
        capacity  = zone["vehicle_capacity"]
        try:
            gates: list[str] = json.loads(zone["associated_gates"])
        except (ValueError, TypeError):
            gates = []
        if gates:
            placeholders = ",".join("?" * len(gates))
            current = conn.execute(
                f"""SELECT COUNT(DISTINCT al.plate_number)
                    FROM access_log al
                    WHERE al.gate_id IN ({placeholders})
                      AND al.direction = 'ENTRY'
                      AND NOT EXISTS (
                        SELECT 1 FROM access_log ex
                        WHERE ex.plate_number = al.plate_number
                          AND ex.gate_id IN ({placeholders})
                          AND ex.direction = 'EXIT'
                          AND ex.id > al.id
                      )""",
                gates + gates,
            ).fetchone()[0] or 0
        else:
            current = 0
        utilisation_pct = (current / capacity * 100) if capacity > 0 else 0.0
        results.append({
            "zone_id":          zone_id,
            "zone_name":        zone_name,
            "zone_type":        zone_type,
            "current_occupancy": current,
            "capacity_vehicles": capacity,
            "utilisation_pct":  utilisation_pct,
        })
    return results


# ---------------------------------------------------------------------------
# 10. Subcontractor billing audit
# ---------------------------------------------------------------------------

def subcontractor_billing_audit(
    conn,
    company_id: str | None = None,
    date_from: str = "2000-01-01",
    date_to: str   = "2099-12-31",
) -> list[dict]:
    """Billed hours per subcontractor vehicle and project."""
    sql = """
        SELECT
            sc.company_id,
            sc.company_name,
            pva.plate_number,
            pva.project_code,
            p.vessel_name                                        AS project_name,
            MIN(DATE(al.timestamp))                             AS date_from,
            MAX(DATE(al.timestamp))                             AS date_to,
            COUNT(al.id)                                        AS trips,
            COALESCE(SUM(al.dwell_time_seconds)/3600.0, 0)     AS billed_hours
        FROM project_vehicle_assignments pva
        JOIN subcontractor_companies sc ON sc.company_id = pva.company_id
        JOIN projects p ON p.project_code = pva.project_code
        LEFT JOIN access_log al
            ON al.plate_number = pva.plate_number
            AND al.direction = 'EXIT'
            AND DATE(al.timestamp) BETWEEN ? AND ?
        WHERE pva.role = 'SUBCONTRACTOR'
          AND pva.removed_at IS NULL
    """
    params: list = [date_from, date_to]
    if company_id:
        sql += " AND pva.company_id = ?"
        params.append(company_id)
    sql += " GROUP BY sc.company_id, pva.plate_number, pva.project_code ORDER BY sc.company_id, pva.plate_number"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers: csv_string, export_csv, export_pdf
# ---------------------------------------------------------------------------

def csv_string(rows: list[dict]) -> str:
    """Serialise a list of row dicts to a CSV string."""
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def export_csv(rows: list[dict], fp: str | Path | IO) -> None:
    """Write rows as CSV to a file path or file-like object."""
    content = csv_string(rows)
    if hasattr(fp, "write"):
        fp.write(content)
    else:
        Path(fp).write_text(content, encoding="utf-8")


def export_pdf(
    rows: list[dict],
    fp: str | Path | IO,
    title: str = "VAAS Report",
    date_range_str: str = "",
) -> None:
    """Write rows as a styled PDF using ReportLab.

    Header bar: CDL Fun Blue (#1B3F95).
    Accent underline: CDL Yellow (#f4bd0f).
    Footer: page numbers.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    )
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import HRFlowable

    if hasattr(fp, "write"):
        target = fp
    else:
        target = str(fp)

    blue   = colors.HexColor(CDL_FUN_BLUE)
    yellow = colors.HexColor(CDL_YELLOW)
    white  = colors.white

    doc = SimpleDocTemplate(
        target,
        pagesize=landscape(A4),
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=title,
    )
    styles = getSampleStyleSheet()

    def _header_footer(canvas, doc):
        canvas.saveState()
        w, h = landscape(A4)
        # Blue header bar
        canvas.setFillColor(blue)
        canvas.rect(0, h - 1.5 * cm, w, 1.5 * cm, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(1.5 * cm, h - 1.1 * cm, f"VAAS | {title}")
        if date_range_str:
            canvas.setFont("Helvetica", 9)
            canvas.drawRightString(w - 1.5 * cm, h - 1.1 * cm, date_range_str)
        # Yellow accent line
        canvas.setFillColor(yellow)
        canvas.rect(0, h - 1.6 * cm, w, 0.1 * cm, fill=1, stroke=0)
        # Footer page number
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(w / 2, 0.75 * cm, f"Page {doc.page}")
        canvas.restoreState()

    story = [Spacer(1, 0.5 * cm)]

    if not rows:
        story.append(Paragraph("No data for selected period.", styles["Normal"]))
    else:
        headers = list(rows[0].keys())
        data = [headers] + [[str(r.get(h, "")) for h in headers] for r in rows]
        col_width = (landscape(A4)[0] - 3 * cm) / len(headers)
        tbl = Table(data, colWidths=[col_width] * len(headers), repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  blue),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("FONTSIZE",      (0, 1), (-1, -1), 7),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f9")]),
            ("GRID",          (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    logger.info("PDF exported: %s", title)
