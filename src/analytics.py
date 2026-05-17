from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import IO

from src.config import CDL_FUN_BLUE, CDL_YELLOW, CDL_SAFETY_GRN

logger = logging.getLogger(__name__)

def personal_vehicle_allowance_report(
    conn,
    date_from: str,
    date_to: str,
    driver_user_id: int | None = None,
) -> list[dict]:
    from src.config import ALLOWANCE_RATES, ALLOWANCE_DEFAULT_LKR

    sql = """
        SELECT
            u.id                                    AS user_id,
            u.username,
            COALESCE(u.full_name, u.username)      AS driver_name,
            va.plate_number,
            rv.vehicle_category,
            rv.vehicle_type,
            DATE(al.timestamp)                      AS event_date,
            COUNT(CASE WHEN al.status = 'ON_TIME_ENTRY'  THEN 1 END) AS on_time_entries,
            COALESCE(SUM(al.dwell_time_seconds) / 3600.0, 0) AS hours_on_site,
            CASE WHEN COUNT(CASE WHEN al.status IN ('ON_TIME_ENTRY','EARLY_ARRIVAL')
                                 THEN 1 END) > 0
                 THEN 1 ELSE 0 END AS eligible
        FROM users u
        JOIN vehicle_assignments va
            ON va.user_id = u.id AND va.is_active = 1
        JOIN registered_vehicles rv
            ON rv.plate_number = va.plate_number
        LEFT JOIN access_log al
            ON al.plate_number = va.plate_number
            AND al.direction = 'ENTRY'
            AND al.status IN ('ON_TIME_ENTRY', 'EARLY_ARRIVAL', 'LATE_ARRIVAL')
            AND DATE(al.timestamp) BETWEEN ? AND ?
        WHERE 1=1
    """
    params: list = [date_from, date_to]
    if driver_user_id is not None:
        sql += " AND u.id = ?"
        params.append(driver_user_id)
    sql += " GROUP BY u.id, va.plate_number, DATE(al.timestamp) ORDER BY event_date, u.username"
    rows = conn.execute(sql, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["daily_rate_lkr"] = ALLOWANCE_RATES.get(
            (d["vehicle_category"], d["vehicle_type"]),
            ALLOWANCE_DEFAULT_LKR,
        )
        result.append(d)
    return result

def ohs_compliance_report(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            rv.plate_number,
            rv.vehicle_type,
            rv.vehicle_category,
            rv.registration_status,
            rv.contractor_name,
            rv.department,
            va.user_id,
            COALESCE(u.full_name, u.username, 'UNASSIGNED')  AS driver_name,
            COUNT(al.id)                        AS total_events,
            SUM(CASE WHEN al.status = 'OVERSTAY' THEN 1 ELSE 0 END) AS overstay_count,
            SUM(CASE WHEN al.status IN ('DOUBLE_ENTRY','UNMATCHED_EXIT') THEN 1 ELSE 0 END) AS gate_anomaly_count,
            CASE
                WHEN rv.registration_status != 'ACTIVE' THEN 0
                WHEN va.user_id IS NULL THEN 0
                ELSE 1
            END AS is_compliant,
            CASE
                WHEN rv.registration_status != 'ACTIVE' THEN 'SUSPENDED'
                WHEN va.user_id IS NULL THEN 'UNASSIGNED'
                WHEN SUM(CASE WHEN al.status = 'OVERSTAY' THEN 1 ELSE 0 END) >= 3 THEN 'HIGH_RISK'
                WHEN SUM(CASE WHEN al.status = 'OVERSTAY' THEN 1 ELSE 0 END) > 0 THEN 'MEDIUM_RISK'
                ELSE 'OK'
            END AS risk_flag
        FROM registered_vehicles rv
        LEFT JOIN vehicle_assignments va
            ON va.plate_number = rv.plate_number AND va.is_active = 1
        LEFT JOIN users u
            ON u.id = va.user_id
        LEFT JOIN access_log al
            ON al.plate_number = rv.plate_number
            AND DATE(al.timestamp) >= DATE('now', '-30 days')
        GROUP BY rv.plate_number
        ORDER BY is_compliant ASC,
                 overstay_count DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]

def gate_rejection_audit(
    conn,
    date_from: str,
    date_to: str,
    gate_id: str | None = None,
) -> list[dict]:
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

def admin_audit_report(
    conn,
    date_from: str,
    date_to: str,
    username: str | None = None,
    entity_type: str | None = None,
) -> list[dict]:
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

def zone_occupancy_snapshot(conn) -> list[dict]:
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

def subcontractor_billing_audit(
    conn,
    company_id: str | None = None,
    date_from: str = "2000-01-01",
    date_to: str   = "2099-12-31",
) -> list[dict]:
    sql = """
        SELECT
            sc.company_id,
            sc.company_name,
            pva.plate_number,
            pva.project_code,
            p.vessel_name                                        AS project_name,
            COALESCE(MIN(DATE(al.timestamp)), ?)                AS date_from,
            COALESCE(MAX(DATE(al.timestamp)), ?)                AS date_to,
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
    params: list = [date_from, date_to, date_from, date_to]
    if company_id:
        sql += " AND pva.company_id = ?"
        params.append(company_id)
    sql += " GROUP BY sc.company_id, pva.plate_number, pva.project_code ORDER BY sc.company_id, pva.plate_number"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def daily_attendance_report(conn, report_date: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT rv.plate_number,
               rv.vehicle_category,
               COUNT(a.id)                        AS total_events,
               CASE WHEN COUNT(a.id) > 0 THEN 1 ELSE 0 END AS present
        FROM registered_vehicles rv
        LEFT JOIN access_log a
               ON a.plate_number = rv.plate_number
              AND date(a.timestamp) = ?
        GROUP BY rv.plate_number
        ORDER BY rv.plate_number
        """,
        (report_date,),
    ).fetchall()
    return [dict(r) for r in rows]

def weekly_attendance_report(conn, week_start: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT rv.plate_number,
               rv.vehicle_category,
               COUNT(DISTINCT date(a.timestamp)) AS days_present
        FROM registered_vehicles rv
        LEFT JOIN access_log a
               ON a.plate_number = rv.plate_number
              AND date(a.timestamp) >= ?
              AND date(a.timestamp) <  date(?, '+7 days')
        GROUP BY rv.plate_number
        ORDER BY rv.plate_number
        """,
        (week_start, week_start),
    ).fetchall()
    return [dict(r) for r in rows]

def monthly_attendance_report(conn, year: int, month: int) -> list[dict]:
    month_str = f"{year:04d}-{month:02d}"
    rows = conn.execute(
        """
        SELECT rv.plate_number,
               rv.vehicle_category,
               COUNT(DISTINCT date(a.timestamp)) AS days_present
        FROM registered_vehicles rv
        LEFT JOIN access_log a
               ON a.plate_number = rv.plate_number
              AND strftime('%Y-%m', a.timestamp) = ?
        GROUP BY rv.plate_number
        ORDER BY rv.plate_number
        """,
        (month_str,),
    ).fetchall()
    return [dict(r) for r in rows]

def gate_throughput_report(
    conn,
    date_from: str,
    date_to: str,
    gate_id: str | None = None,
) -> list[dict]:
    params: list = [date_from, date_to]
    gate_filter = ""
    if gate_id:
        gate_filter = "AND gate_id = ?"
        params.append(gate_id)

    rows = conn.execute(
        f"""
        SELECT gate_id,
               date(timestamp)              AS event_date,
               CAST(strftime('%H', timestamp) AS INTEGER) AS hour,
               direction,
               COUNT(*)                    AS count
        FROM access_log
        WHERE date(timestamp) BETWEEN ? AND ?
          {gate_filter}
        GROUP BY gate_id, event_date, hour, direction
        ORDER BY gate_id, event_date, hour, direction
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]

def personal_vehicle_allowance_report_pivot(
    conn,
    date_from: str,
    date_to: str,
) -> list[dict]:
    from datetime import date as _date, timedelta

    start = _date.fromisoformat(date_from)
    end   = _date.fromisoformat(date_to)
    dates: list[str] = []
    d = start
    while d <= end:
        dates.append(d.isoformat())
        d += timedelta(days=1)

    flat = personal_vehicle_allowance_report(conn, date_from, date_to)

    eligibility: dict[tuple, int] = {}
    driver_meta: dict[tuple, dict] = {}
    for row in flat:
        key = (row["driver_name"], row["plate_number"])
        if key not in driver_meta:
            driver_meta[key] = {
                "Driver":   row["driver_name"],
                "Plate":    row["plate_number"],
                "Category": row["vehicle_category"],
                "Type":     row["vehicle_type"],
                "Rate LKR/day": row["daily_rate_lkr"],
            }
        if row.get("event_date"):
            eligibility[(row["driver_name"], row["plate_number"], row["event_date"])] = row["eligible"]

    result: list[dict] = []
    for (driver_name, plate_number), meta in driver_meta.items():
        row: dict = {
            "Driver":   meta["Driver"],
            "Plate":    meta["Plate"],
            "Category": meta["Category"],
            "Type":     meta["Type"],
        }
        rate = meta["Rate LKR/day"]
        total_eligible = 0
        total_accessed = 0
        for dt in dates:
            val = eligibility.get((driver_name, plate_number, dt))
            short = dt[5:]
            if val is None:
                row[short] = ""
            elif val:
                row[short] = "Y"
                total_eligible += 1
                total_accessed += 1
            else:
                row[short] = "N"
                total_accessed += 1
        row["Rate LKR/day"] = rate
        row["Eligible"]     = total_eligible
        row["Days"]         = total_accessed
        row["Eligible LKR"] = total_eligible * rate
        row["Compliance"]   = (
            f"{round(total_eligible / total_accessed * 100)}%"
            if total_accessed else "—"
        )
        result.append(row)

    return result

def export_pdf_pivot(
    rows: list[dict],
    fp,
    title: str = "VAAS Report",
    date_range_str: str = "",
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    if hasattr(fp, "write"):
        target = fp
    else:
        target = str(fp)

    blue   = colors.HexColor(CDL_FUN_BLUE)
    yellow = colors.HexColor(CDL_YELLOW)
    white  = colors.white
    green  = colors.HexColor("#76bd33")
    red    = colors.HexColor("#ef4444")

    page_w, page_h = landscape(A4)
    margin = 1.5 * cm
    usable_w = page_w - 2 * margin

    doc = SimpleDocTemplate(
        target,
        pagesize=landscape(A4),
        rightMargin=margin, leftMargin=margin,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=title,
    )

    def _header_footer(canvas, doc):
        canvas.saveState()
        w, h = landscape(A4)
        canvas.setFillColor(blue)
        canvas.rect(0, h - 1.5 * cm, w, 1.5 * cm, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(1.5 * cm, h - 1.1 * cm, f"VAAS | {title}")
        if date_range_str:
            canvas.setFont("Helvetica", 9)
            canvas.drawRightString(w - 1.5 * cm, h - 1.1 * cm, date_range_str)
        canvas.setFillColor(yellow)
        canvas.rect(0, h - 1.6 * cm, w, 0.1 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(w / 2, 0.75 * cm, f"Page {doc.page}")
        canvas.restoreState()

    story = [Spacer(1, 0.5 * cm)]

    if not rows:
        from reportlab.platypus import Paragraph
        styles = getSampleStyleSheet()
        story.append(Paragraph("No data for selected period.", styles["Normal"]))
    else:
        headers = list(rows[0].keys())
        fixed = {"Driver", "Plate", "Category", "Type", "Rate LKR/day",
                 "Eligible", "Days", "Eligible LKR", "Compliance"}
        date_cols = [h for h in headers if h not in fixed]

        driver_w       = 3.5 * cm
        plate_w        = 2.2 * cm
        cat_w          = 1.6 * cm
        type_w         = 1.5 * cm
        rate_w         = 1.8 * cm
        summary_w      = 1.3 * cm
        eligible_lkr_w = 2.0 * cm
        fixed_total  = (driver_w + plate_w + cat_w + type_w + rate_w
                        + summary_w * 3 + eligible_lkr_w)
        date_total   = usable_w - fixed_total
        date_w       = max(0.45 * cm, date_total / len(date_cols)) if date_cols else 0.6 * cm

        col_widths: list[float] = []
        for h in headers:
            if h == "Driver":
                col_widths.append(driver_w)
            elif h == "Plate":
                col_widths.append(plate_w)
            elif h == "Category":
                col_widths.append(cat_w)
            elif h == "Type":
                col_widths.append(type_w)
            elif h == "Rate LKR/day":
                col_widths.append(rate_w)
            elif h in ("Eligible", "Days", "Compliance"):
                col_widths.append(summary_w)
            elif h == "Eligible LKR":
                col_widths.append(eligible_lkr_w)
            else:
                col_widths.append(date_w)

        data = [headers] + [[str(r.get(h, "")) for h in headers] for r in rows]
        tbl = Table(data, colWidths=col_widths, repeatRows=1)

        style_cmds = [
            ("BACKGROUND",    (0, 0), (-1, 0),  blue),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  6),
            ("FONTSIZE",      (0, 1), (-1, -1), 6),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, colors.HexColor("#f4f6f9")]),
            ("GRID",          (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
            ("ALIGN",         (1, 0), (1, -1),  "LEFT"),
        ]

        for col_idx, h in enumerate(headers):
            if h in ("Driver", "Plate", "Category", "Type", "Rate LKR/day",
                     "Compliance", "Eligible", "Days", "Eligible LKR"):
                continue
            for row_idx, row in enumerate(rows, start=1):
                val = row.get(h, "")
                if val == "Y":
                    style_cmds.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), green))
                    style_cmds.append(("FONTNAME",  (col_idx, row_idx), (col_idx, row_idx), "Helvetica-Bold"))
                elif val == "N":
                    style_cmds.append(("TEXTCOLOR", (col_idx, row_idx), (col_idx, row_idx), red))

        tbl.setStyle(TableStyle(style_cmds))
        story.append(tbl)

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    logger.info("Pivot PDF exported: %s", title)

def csv_string(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

def export_csv(rows: list[dict], fp: str | Path | IO) -> None:
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

        canvas.setFillColor(blue)
        canvas.rect(0, h - 1.5 * cm, w, 1.5 * cm, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(1.5 * cm, h - 1.1 * cm, f"VAAS | {title}")
        if date_range_str:
            canvas.setFont("Helvetica", 9)
            canvas.drawRightString(w - 1.5 * cm, h - 1.1 * cm, date_range_str)

        canvas.setFillColor(yellow)
        canvas.rect(0, h - 1.6 * cm, w, 0.1 * cm, fill=1, stroke=0)

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
