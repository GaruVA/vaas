"""Reporting and analytics aggregations (FR-04, §5.5, §6.5)."""
from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


@dataclass
class VehicleAttendanceRow:
    plate_number: str
    period: str
    total_hours: float
    entry_count: int
    exit_count: int
    on_time_count: int
    late_count: int
    exception_count: int
    compliance_rate: float


@dataclass
class GateThroughputRow:
    gate_id: str
    period: str
    hour: int
    entries: int
    exits: int
    avg_dwell_seconds: float


def _date_range_clause(date_from: str, date_to: str) -> tuple[str, tuple]:
    return ("timestamp >= ? AND timestamp < ?", (date_from, date_to))


def daily_attendance_report(conn: sqlite3.Connection,
                            date_from: str, date_to: str) -> list[VehicleAttendanceRow]:
    where, params = _date_range_clause(date_from, date_to)
    sql = f"""
    SELECT plate_number,
           substr(timestamp,1,10) AS period,
           SUM(CASE WHEN direction='ENTRY' THEN 1 ELSE 0 END) AS entries,
           SUM(CASE WHEN direction='EXIT' THEN 1 ELSE 0 END) AS exits,
           SUM(CASE WHEN status='ON_TIME_ENTRY' THEN 1 ELSE 0 END) AS on_time,
           SUM(CASE WHEN status='LATE_ARRIVAL' THEN 1 ELSE 0 END) AS late_count,
           SUM(CASE WHEN status='VISITOR' OR status LIKE 'VISITOR_%' THEN 1 ELSE 0 END) AS exceptions,
           COALESCE(SUM(dwell_time_seconds),0) AS dwell_total
    FROM access_log
    WHERE {where}
    GROUP BY plate_number, period
    ORDER BY period, plate_number
    """
    rows = conn.execute(sql, params).fetchall()
    out: list[VehicleAttendanceRow] = []
    for r in rows:
        entries = r["entries"] or 0
        on_time = r["on_time"] or 0
        rate = (on_time / entries) if entries > 0 else 0.0
        out.append(VehicleAttendanceRow(
            plate_number=r["plate_number"],
            period=r["period"],
            total_hours=round((r["dwell_total"] or 0.0) / 3600.0, 3),
            entry_count=entries,
            exit_count=r["exits"] or 0,
            on_time_count=on_time,
            late_count=r["late_count"] or 0,
            exception_count=r["exceptions"] or 0,
            compliance_rate=round(rate, 3),
        ))
    return out


def weekly_attendance_report(conn: sqlite3.Connection,
                             week_start: str) -> list[VehicleAttendanceRow]:
    start = datetime.strptime(week_start, "%Y-%m-%d").date()
    end = start + timedelta(days=7)
    rows = daily_attendance_report(conn, start.isoformat(), end.isoformat())
    agg: dict[str, VehicleAttendanceRow] = {}
    for r in rows:
        key = r.plate_number
        if key not in agg:
            agg[key] = VehicleAttendanceRow(
                plate_number=r.plate_number,
                period=f"week-of-{start.isoformat()}",
                total_hours=0.0,
                entry_count=0, exit_count=0, on_time_count=0,
                late_count=0, exception_count=0, compliance_rate=0.0,
            )
        a = agg[key]
        a.total_hours = round(a.total_hours + r.total_hours, 3)
        a.entry_count += r.entry_count
        a.exit_count += r.exit_count
        a.on_time_count += r.on_time_count
        a.late_count += r.late_count
        a.exception_count += r.exception_count
    for a in agg.values():
        a.compliance_rate = round(a.on_time_count / a.entry_count, 3) if a.entry_count else 0.0
    return list(agg.values())


def monthly_attendance_report(conn: sqlite3.Connection,
                              year: int, month: int) -> list[VehicleAttendanceRow]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    rows = daily_attendance_report(conn, start.isoformat(), end.isoformat())
    agg: dict[str, VehicleAttendanceRow] = {}
    for r in rows:
        key = r.plate_number
        if key not in agg:
            agg[key] = VehicleAttendanceRow(
                plate_number=r.plate_number,
                period=f"{year:04d}-{month:02d}",
                total_hours=0.0,
                entry_count=0, exit_count=0, on_time_count=0,
                late_count=0, exception_count=0, compliance_rate=0.0,
            )
        a = agg[key]
        a.total_hours = round(a.total_hours + r.total_hours, 3)
        a.entry_count += r.entry_count
        a.exit_count += r.exit_count
        a.on_time_count += r.on_time_count
        a.late_count += r.late_count
        a.exception_count += r.exception_count
    for a in agg.values():
        a.compliance_rate = round(a.on_time_count / a.entry_count, 3) if a.entry_count else 0.0
    return list(agg.values())


def gate_throughput_report(conn: sqlite3.Connection,
                           date_from: str, date_to: str) -> list[GateThroughputRow]:
    where, params = _date_range_clause(date_from, date_to)
    sql = f"""
    SELECT gate_id,
           substr(timestamp,1,10) AS period,
           CAST(substr(timestamp,12,2) AS INTEGER) AS hour,
           SUM(CASE WHEN direction='ENTRY' THEN 1 ELSE 0 END) AS entries,
           SUM(CASE WHEN direction='EXIT' THEN 1 ELSE 0 END) AS exits,
           AVG(dwell_time_seconds) AS avg_dwell
    FROM access_log
    WHERE {where}
    GROUP BY gate_id, period, hour
    ORDER BY period, hour, gate_id
    """
    rows = conn.execute(sql, params).fetchall()
    out: list[GateThroughputRow] = []
    for r in rows:
        out.append(GateThroughputRow(
            gate_id=r["gate_id"],
            period=r["period"],
            hour=r["hour"],
            entries=r["entries"] or 0,
            exits=r["exits"] or 0,
            avg_dwell_seconds=round((r["avg_dwell"] or 0.0), 2),
        ))
    return out


def export_csv(rows: Iterable[Any], fp) -> None:
    rows = list(rows)
    if not rows:
        fp.write("")
        return
    fields = list(asdict(rows[0]).keys())
    writer = csv.DictWriter(fp, fieldnames=fields)
    writer.writeheader()
    for r in rows:
        writer.writerow(asdict(r))


def export_pdf(rows: Iterable[Any], fp, title: str = "VAAS Report") -> None:
    rows = list(rows)
    doc = SimpleDocTemplate(fp, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm,
                            title=title)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            styles["Normal"]),
        Spacer(1, 0.5*cm),
    ]
    if not rows:
        story.append(Paragraph("No data for this report.", styles["Normal"]))
    else:
        fields = list(asdict(rows[0]).keys())
        data = [fields] + [
            [str(asdict(r).get(f, "")) for f in fields] for r in rows
        ]
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.whitesmoke, colors.lightgrey]),
        ]))
        story.append(tbl)

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(1.5*cm, 1*cm, f"VAAS — {title}")
        canvas.drawRightString(20*cm, 1*cm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


def csv_string(rows: Iterable[Any]) -> str:
    buf = io.StringIO()
    export_csv(rows, buf)
    return buf.getvalue()
