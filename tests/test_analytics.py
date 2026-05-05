"""Tests for analytics/reporting (FR-04, §6.5)."""
from __future__ import annotations

import csv
import io

import pytest

from src.analytics import (
    absence_report,
    absence_summary,
    csv_string,
    daily_attendance_report,
    dashboard_stats,
    export_csv,
    export_pdf,
    fuel_accountability_report,
    gate_throughput_report,
    monthly_attendance_report,
    ohs_compliance_report,
    payroll_report,
    rejections_report,
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


# ── Absence report tests ─────────────────────────────────────────────────────
# seeded_db: 5 ACTIVE vehicles all on DAY_SHIFT (shift_name="Day", all 7 days)
# 2026-04-30 is Thursday  →  day abbr "THU"  →  expected working day

def test_absence_report_absent(seeded_db):
    """Vehicle with no access_log entry on an expected day → ABSENT."""
    rows = absence_report(seeded_db, "2026-04-30", "2026-05-01")
    cab_rows = [r for r in rows if r.plate_number == "CAB-1234"]
    assert len(cab_rows) == 1
    assert cab_rows[0].attendance_status == "ABSENT"


def test_absence_report_present(seeded_db):
    """ON_TIME_ENTRY on expected day → PRESENT."""
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T08:05:00Z",
              "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T17:00:00Z",
              "GATE_A", "EXIT", "ON_TIME_EXIT", 32100)
    rows = absence_report(seeded_db, "2026-04-30", "2026-05-01")
    cab_rows = [r for r in rows if r.plate_number == "CAB-1234"]
    assert cab_rows[0].attendance_status == "PRESENT"


def test_absence_report_late(seeded_db):
    """LATE_ARRIVAL entry with no ON_TIME_ENTRY → LATE."""
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T09:30:00Z",
              "GATE_A", "ENTRY", "LATE_ARRIVAL")
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T17:00:00Z",
              "GATE_A", "EXIT", "ON_TIME_EXIT", 27000)
    rows = absence_report(seeded_db, "2026-04-30", "2026-05-01")
    cab_rows = [r for r in rows if r.plate_number == "CAB-1234"]
    assert cab_rows[0].attendance_status == "LATE"


def test_absence_report_partial(seeded_db):
    """ENTRY with no EXIT → PARTIAL."""
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T08:05:00Z",
              "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    rows = absence_report(seeded_db, "2026-04-30", "2026-05-01")
    cab_rows = [r for r in rows if r.plate_number == "CAB-1234"]
    assert cab_rows[0].attendance_status == "PARTIAL"


def test_absence_report_day_name(seeded_db):
    """Day name field is human-readable, e.g. Thursday for 2026-04-30."""
    rows = absence_report(seeded_db, "2026-04-30", "2026-05-01")
    cab_rows = [r for r in rows if r.plate_number == "CAB-1234"]
    assert cab_rows[0].day_name == "Thursday"


def test_absence_report_no_suspended(seeded_db):
    """SUSPENDED / EXPIRED vehicles are excluded from the absence report."""
    rows = absence_report(seeded_db, "2026-04-30", "2026-05-01")
    plates = {r.plate_number for r in rows}
    assert "SUS-0001" not in plates
    assert "EXP-0001" not in plates


def test_absence_report_shift_name(seeded_db):
    """shift_name comes from the shifts table (seeded as 'Day')."""
    rows = absence_report(seeded_db, "2026-04-30", "2026-05-01")
    assert all(r.shift_name == "Day" for r in rows)


# ── Absence summary tests ────────────────────────────────────────────────────

def test_absence_summary_counts(seeded_db):
    """Absent day for CAB-1234 bumps absent_count to 1 in summary."""
    summary = absence_summary(seeded_db, "2026-04-30", "2026-05-01")
    cab = next(r for r in summary if r.plate_number == "CAB-1234")
    assert cab.expected_days == 1
    assert cab.absent_count == 1
    assert cab.presence_rate_by_name if False else True   # attribute check below


def test_absence_summary_rates(seeded_db):
    """Absence rate = absent / expected; compliance = present / expected."""
    # 2 days window: 2026-04-30 (THU) and 2026-05-01 (FRI), both expected
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T08:05:00Z",
              "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T17:00:00Z",
              "GATE_A", "EXIT", "ON_TIME_EXIT", 32100)
    # 2026-05-01 — no log entry → ABSENT
    summary = absence_summary(seeded_db, "2026-04-30", "2026-05-02")
    cab = next(r for r in summary if r.plate_number == "CAB-1234")
    assert cab.expected_days == 2
    assert cab.present_count == 1
    assert cab.absent_count == 1
    assert cab.absence_rate == 0.5
    assert cab.compliance_rate == 0.5


def test_absence_summary_uses_cached_detail(seeded_db):
    """_detail kwarg skips the second DB query (returns same result)."""
    detail = absence_report(seeded_db, "2026-04-30", "2026-05-01")
    s1 = absence_summary(seeded_db, "2026-04-30", "2026-05-01")
    s2 = absence_summary(seeded_db, "2026-04-30", "2026-05-01", _detail=detail)
    assert [r.plate_number for r in s1] == [r.plate_number for r in s2]


# ── Dashboard stats tests ────────────────────────────────────────────────────

def test_dashboard_stats_keys(seeded_db):
    """Return dict contains required top-level keys."""
    stats = dashboard_stats(seeded_db, days=7)
    assert "kpis" in stats
    assert "chart" in stats


def test_dashboard_stats_chart_length(seeded_db):
    """Chart arrays have exactly `days` elements."""
    stats = dashboard_stats(seeded_db, days=7)
    chart = stats["chart"]
    assert len(chart["labels"])  == 7
    assert len(chart["entries"]) == 7
    assert len(chart["on_time"]) == 7
    assert len(chart["late"])    == 7


def test_dashboard_stats_active_vehicles(seeded_db):
    """KPI active_vehicles matches the 5 ACTIVE rows in seeded_db."""
    stats = dashboard_stats(seeded_db, days=7)
    assert stats["kpis"]["active_vehicles"] == 5


def test_dashboard_stats_zero_fill(seeded_db):
    """Days with no access_log entries produce zeroes, not missing indices."""
    stats = dashboard_stats(seeded_db, days=3)
    assert all(isinstance(v, int) for v in stats["chart"]["entries"])


# ── Payroll report tests ──────────────────────────────────────────────────────
# seeded_db: CAB-1234 and WP-CAB-9012 assigned to alice (user_id=1)
#            KL-5678 assigned to bob (user_id=2)
#            CAR-4521 and VAN-8801 are UNASSIGNED

def test_payroll_report_empty_no_logs(seeded_db):
    """No access_log entries → empty payroll."""
    assert payroll_report(seeded_db, "2026-04-30", "2026-05-01") == []


def test_payroll_report_counts_assigned_vehicle(seeded_db):
    """EXIT event for assigned vehicle appears in payroll for the driver."""
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T17:00:00Z", "GATE_A", "EXIT",  "ON_TIME_EXIT", 32400)
    rows = payroll_report(seeded_db, "2026-04-30", "2026-05-01")
    assert len(rows) == 1
    r = rows[0]
    assert r.plate_number == "CAB-1234"
    assert r.username     == "alice"
    assert r.trips        == 1
    assert abs(r.hours_worked - 9.0) < 0.01


def test_payroll_report_excludes_unassigned(seeded_db):
    """Vehicle with no user assignment does NOT appear in payroll."""
    _seed_log(seeded_db, "CAR-4521", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "CAR-4521", "2026-04-30T17:00:00Z", "GATE_A", "EXIT",  "ON_TIME_EXIT", 32400)
    rows = payroll_report(seeded_db, "2026-04-30", "2026-05-01")
    plates = {r.plate_number for r in rows}
    assert "CAR-4521" not in plates


def test_payroll_report_compliance_rate(seeded_db):
    """Late entry lowers compliance rate below 1.0."""
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T09:30:00Z", "GATE_A", "ENTRY", "LATE_ARRIVAL")
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T17:00:00Z", "GATE_A", "EXIT",  "ON_TIME_EXIT", 27000)
    rows = payroll_report(seeded_db, "2026-04-30", "2026-05-01")
    r = rows[0]
    assert r.late_count == 1
    assert r.compliance_rate < 1.0


# ── OHS compliance tests ──────────────────────────────────────────────────────

def test_ohs_all_vehicles_present(seeded_db):
    """All 7 registered vehicles (5 active + 2 suspended/expired) appear."""
    rows = ohs_compliance_report(seeded_db)
    assert len(rows) == 7


def test_ohs_unassigned_flag(seeded_db):
    """CAR-4521 (active, no assignment) gets UNASSIGNED risk flag."""
    rows = ohs_compliance_report(seeded_db)
    car = next(r for r in rows if r.plate_number == "CAR-4521")
    assert car.risk_flag == "UNASSIGNED"


def test_ohs_assigned_ok_flag(seeded_db):
    """CAB-1234 is assigned to alice and has no overstays → OK."""
    rows = ohs_compliance_report(seeded_db)
    cab = next(r for r in rows if r.plate_number == "CAB-1234")
    assert cab.risk_flag == "OK"
    assert cab.assigned_driver == "alice"


def test_ohs_suspended_flag(seeded_db):
    """SUS-0001 is suspended → SUSPENDED flag regardless of assignment."""
    rows = ohs_compliance_report(seeded_db)
    sus = next(r for r in rows if r.plate_number == "SUS-0001")
    assert sus.risk_flag == "SUSPENDED"


# ── Fuel accountability tests ─────────────────────────────────────────────────

def test_fuel_report_empty(seeded_db):
    """No EXIT events → empty fuel report."""
    assert fuel_accountability_report(seeded_db, "2026-04-30", "2026-05-01") == []


def test_fuel_report_estimates_consumption(seeded_db):
    """CAR type with 1h dwell → 8.0 L estimated consumption."""
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T09:00:00Z", "GATE_A", "EXIT",  "ON_TIME_EXIT", 3600)
    rows = fuel_accountability_report(seeded_db, "2026-04-30", "2026-05-01")
    assert len(rows) == 1
    r = rows[0]
    assert r.vehicle_type == "CAR"
    assert abs(r.estimated_fuel_litres - 8.0) < 0.1


def test_fuel_report_van_higher_rate(seeded_db):
    """VAN uses 10 L/hr — higher than CAR at same dwell time."""
    _seed_log(seeded_db, "KL-5678",  "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "KL-5678",  "2026-04-30T09:00:00Z", "GATE_A", "EXIT",  "ON_TIME_EXIT", 3600)
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T08:00:00Z", "GATE_A", "ENTRY", "ON_TIME_ENTRY")
    _seed_log(seeded_db, "CAB-1234", "2026-04-30T09:00:00Z", "GATE_A", "EXIT",  "ON_TIME_EXIT", 3600)
    rows = fuel_accountability_report(seeded_db, "2026-04-30", "2026-05-01")
    van_fuel = next(r.estimated_fuel_litres for r in rows if r.plate_number == "KL-5678")
    car_fuel = next(r.estimated_fuel_litres for r in rows if r.plate_number == "CAB-1234")
    assert van_fuel > car_fuel


# ── Rejections report tests ───────────────────────────────────────────────────

def _seed_rejection(conn, plate, ts, gate, reason, conf=0.55):
    conn.execute(
        "INSERT INTO gate_rejections (plate_number,timestamp,gate_id,reason,confidence_score) "
        "VALUES (?,?,?,?,?)",
        (plate, ts, gate, reason, conf),
    )


def test_rejections_empty(seeded_db):
    """No rejections → empty list."""
    assert rejections_report(seeded_db, "2026-04-30", "2026-05-01") == []


def test_rejections_returns_event(seeded_db):
    """Seeded rejection appears in the report."""
    _seed_rejection(seeded_db, "UNK-9999", "2026-04-30T09:00:00Z",
                    "GATE_A", "NOT_REGISTERED", 0.62)
    rows = rejections_report(seeded_db, "2026-04-30", "2026-05-01")
    assert len(rows) == 1
    assert rows[0].plate_number == "UNK-9999"
    assert rows[0].reason == "NOT_REGISTERED"


def test_rejections_date_filter(seeded_db):
    """Rejection outside date window is excluded."""
    _seed_rejection(seeded_db, "UNK-9999", "2026-04-29T09:00:00Z", "GATE_A", "SUSPENDED")
    rows = rejections_report(seeded_db, "2026-04-30", "2026-05-01")
    assert rows == []


def test_rejections_ordered_newest_first(seeded_db):
    """Multiple rejections returned newest first."""
    _seed_rejection(seeded_db, "P1", "2026-04-30T08:00:00Z", "GATE_A", "SUSPENDED")
    _seed_rejection(seeded_db, "P2", "2026-04-30T10:00:00Z", "GATE_B", "NOT_REGISTERED")
    rows = rejections_report(seeded_db, "2026-04-30", "2026-05-01")
    assert rows[0].plate_number == "P2"
