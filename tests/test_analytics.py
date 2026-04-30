"""20 tests for analytics/reporting (FR-04, §6.5)."""
from __future__ import annotations

import csv
import io

import pytest

from src.analytics import (
    csv_string,
    daily_attendance_report,
    export_csv,
    export_pdf,
    gate_throughput_report,
    monthly_attendance_report,
    weekly_attendance_report,
)
from src.database import transaction


def _seed_log(conn, plate, ts, gate, direction, status, dwell=None):
    with transaction(conn) as cur:
        cur.execute(
            "INSERT INTO access_log "
            "(plate_number,timestamp,gate_id,direction,dwell_time_seconds,status,row_hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (plate, ts, gate, direction, dwell, status, "h"),
        )


def test_daily_report_empty(seeded_db):
    rows = daily_attendance_report(seeded_db, "2026-01-01", "2026-01-02")
    assert rows == []


def test_daily_report_basic(seeded_db):
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T08:05:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T17:00:00Z", "GATE_A", "EXIT", "ON_TIME_EXIT", 32100)
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    assert len(rows) == 1
    assert rows[0].plate_number == "CAB-1234"


def test_daily_report_total_hours(seeded_db):
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T17:00:00Z", "GATE_A", "EXIT", "ON_TIME_EXIT", 9 * 3600)
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    assert rows[0].total_hours == 9.0


def test_compliance_rate_100_percent(seeded_db):
    _seed_log(seeded_db, "X", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    assert rows[0].compliance_rate == 1.0


def test_compliance_rate_zero(seeded_db):
    _seed_log(seeded_db, "X", "2026-04-30T09:30:00Z", "GATE_A", "ENTRY", "LATE_ARRIVAL")
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    assert rows[0].compliance_rate == 0.0
    assert rows[0].late_count == 1


def test_exception_count(seeded_db):
    _seed_log(seeded_db, "Z", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "VISITOR")
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    assert rows[0].exception_count == 1


def test_weekly_aggregation(seeded_db):
    for d in range(1, 8):
        _seed_log(seeded_db, "CAB-1234", f"2026-04-{d+5:02d}T08:00:00Z",
                  "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = weekly_attendance_report(seeded_db, "2026-04-06")
    assert len(rows) == 1
    assert rows[0].entry_count == 7


def test_weekly_aggregation_compliance(seeded_db):
    _seed_log(seeded_db, "P", "2026-04-06T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "P", "2026-04-07T09:30:00Z", "GATE_A", "ENTRY", "LATE_ARRIVAL")
    rows = weekly_attendance_report(seeded_db, "2026-04-06")
    assert rows[0].compliance_rate == 0.5


def test_monthly_aggregation(seeded_db):
    for d in (1, 15, 28):
        _seed_log(seeded_db, "P", f"2026-04-{d:02d}T08:00:00Z",
                  "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = monthly_attendance_report(seeded_db, 2026, 4)
    assert rows[0].entry_count == 3


def test_monthly_period_label(seeded_db):
    _seed_log(seeded_db, "P", "2026-04-01T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = monthly_attendance_report(seeded_db, 2026, 4)
    assert rows[0].period == "2026-04"


def test_gate_throughput_basic(seeded_db):
    _seed_log(seeded_db, "P1", "2026-04-30T08:30:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "P2", "2026-04-30T08:45:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = gate_throughput_report(seeded_db, "2026-04-30", "2026-05-01")
    assert any(r.entries == 2 and r.hour == 8 for r in rows)


def test_gate_throughput_per_gate(seeded_db):
    _seed_log(seeded_db, "P1", "2026-04-30T08:30:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "P2", "2026-04-30T08:30:00Z", "GATE_B", "ENTRY", "ON_TIME_ENTRY")
    rows = gate_throughput_report(seeded_db, "2026-04-30", "2026-05-01")
    gates = {r.gate_id for r in rows}
    assert "GATE_A" in gates and "GATE_B" in gates


def test_csv_export_writes_header(seeded_db):
    _seed_log(seeded_db, "X", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    s = csv_string(rows)
    assert "plate_number" in s
    assert "X" in s


def test_csv_export_parseable(seeded_db):
    _seed_log(seeded_db, "X", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    parsed = list(csv.DictReader(io.StringIO(csv_string(rows))))
    assert parsed[0]["plate_number"] == "X"


def test_csv_empty_rows(tmp_path):
    p = tmp_path / "empty.csv"
    with open(p, "w", newline="") as fp:
        export_csv([], fp)
    assert p.exists()


def test_pdf_export_creates_file(seeded_db, tmp_path):
    _seed_log(seeded_db, "X", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    p = tmp_path / "r.pdf"
    with open(p, "wb") as fp:
        export_pdf(rows, fp, title="Daily Report")
    assert p.stat().st_size > 200


def test_pdf_export_empty(tmp_path):
    p = tmp_path / "e.pdf"
    with open(p, "wb") as fp:
        export_pdf([], fp, title="Empty")
    assert p.stat().st_size > 100


def test_daily_filters_date_range(seeded_db):
    _seed_log(seeded_db, "P", "2026-04-29T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "P", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    assert len(rows) == 1


def test_avg_dwell_in_throughput(seeded_db):
    _seed_log(seeded_db, "P", "2026-04-30T08:00:00Z", "GATE_A", "EXIT",
              "ON_TIME_EXIT", 3600)
    rows = gate_throughput_report(seeded_db, "2026-04-30", "2026-05-01")
    assert any(r.avg_dwell_seconds == 3600 for r in rows)


def test_late_count_in_daily(seeded_db):
    _seed_log(seeded_db, "P", "2026-04-30T09:30:00Z", "GATE_A", "ENTRY", "LATE_ARRIVAL")
    rows = daily_attendance_report(seeded_db, "2026-04-30", "2026-05-01")
    assert rows[0].late_count == 1
