from __future__ import annotations

"""45 tests for src/analytics.py -- 10 report functions + 3 helpers.

Distribution: 8+6+4+4+3+3+3+4+3+4+3 = 45
 8  personal_vehicle_allowance_report
 6  ohs_compliance_report  (incl. LEFT JOIN test)
 4  gate_rejection_audit
 4  admin_audit_report
 3  daily_attendance_report
 3  weekly_attendance_report
 3  monthly_attendance_report
 4  gate_throughput_report
 3  zone_occupancy_snapshot
 4  subcontractor_billing_audit
 3  export helpers (csv_string, export_csv, export_pdf)
"""

import csv
import io
import json
from datetime import date, timedelta

import pytest

from src.analytics import (
    personal_vehicle_allowance_report,
    ohs_compliance_report,
    gate_rejection_audit,
    admin_audit_report,
    daily_attendance_report,
    weekly_attendance_report,
    monthly_attendance_report,
    gate_throughput_report,
    zone_occupancy_snapshot,
    subcontractor_billing_audit,
    csv_string,
    export_csv,
    export_pdf,
)
from src.audit import log_gate_event

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_access(db, plate, ts, gate="MAIN_GATE", direction="ENTRY",
                 status="ON_TIME_ENTRY", dwell=None):
    cur = db.cursor()
    cur.execute(
        """INSERT INTO access_log
           (plate_number, timestamp, gate_id, direction, status,
            dwell_time_seconds, row_hash)
           VALUES (?,?,?,?,?,?,'PENDING')""",
        (plate, ts, gate, direction, status, dwell),
    )
    row_id = cur.lastrowid
    from src.audit import finalise_row_hash
    finalise_row_hash(db, row_id)
    return row_id


def _seed_rejection(db, plate, ts, gate="MAIN_GATE", reason="SUSPENDED"):
    db.execute(
        """INSERT INTO gate_rejections
           (plate_number, timestamp, gate_id, reason, confidence_score)
           VALUES (?,?,?,?,0.9)""",
        (plate, ts, gate, reason),
    )


def _seed_admin_audit(db, username, action, entity_type, entity_id, ts=None):
    db.execute(
        """INSERT INTO admin_audit_log
           (timestamp, username, action, entity_type, entity_id)
           VALUES (COALESCE(?,'2026-01-10T09:00:00Z'),?,?,?,?)""",
        (ts, username, action, entity_type, entity_id),
    )


# ============================================================
# 1-8: personal_vehicle_allowance_report
# ============================================================

def test_pva_01_returns_list(seeded_db):
    rows = personal_vehicle_allowance_report(seeded_db, "2026-01-01", "2026-12-31")
    assert isinstance(rows, list)


def test_pva_02_empty_period_no_events(seeded_db):
    rows = personal_vehicle_allowance_report(seeded_db, "2020-01-01", "2020-12-31")
    # No events in that period -> every row has on_time_entries = 0 or no rows
    for r in rows:
        assert r["on_time_entries"] is None or r["on_time_entries"] == 0


def test_pva_03_on_time_entry_marks_eligible(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-10T07:05:00Z", status="ON_TIME_ENTRY")
    rows = personal_vehicle_allowance_report(seeded_db, "2026-01-10", "2026-01-10")
    cab = next((r for r in rows if r["plate_number"] == "WP-CAB-1234"), None)
    assert cab is not None
    assert cab["eligible"] == 1


def test_pva_04_late_arrival_not_eligible(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-11T07:30:00Z", status="LATE_ARRIVAL")
    rows = personal_vehicle_allowance_report(seeded_db, "2026-01-11", "2026-01-11")
    # LATE_ARRIVAL does NOT count for allowance
    for r in rows:
        if r["plate_number"] == "WP-CAB-1234" and r.get("event_date") == "2026-01-11":
            assert r["eligible"] == 0


def test_pva_05_filter_by_driver_user_id(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-12T07:05:00Z", status="ON_TIME_ENTRY")
    # operator user_id = 3 (from seeded_db conftest)
    op_id = seeded_db.execute("SELECT id FROM users WHERE username='operator'").fetchone()[0]
    rows = personal_vehicle_allowance_report(seeded_db, "2026-01-12", "2026-01-12", driver_user_id=op_id)
    assert all(r["user_id"] == op_id for r in rows if r.get("event_date"))


def test_pva_06_multiple_entries_same_day_single_row(seeded_db):
    for ts in ["2026-01-13T07:05:00Z", "2026-01-13T12:00:00Z"]:
        _seed_access(seeded_db, "WP-CAB-1234", ts, status="ON_TIME_ENTRY")
    rows = personal_vehicle_allowance_report(seeded_db, "2026-01-13", "2026-01-13")
    cab_rows = [r for r in rows if r["plate_number"] == "WP-CAB-1234" and r.get("event_date") == "2026-01-13"]
    assert len(cab_rows) == 1
    assert cab_rows[0]["on_time_entries"] == 2


def test_pva_07_early_arrival_also_eligible(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-14T06:50:00Z", status="EARLY_ARRIVAL")
    rows = personal_vehicle_allowance_report(seeded_db, "2026-01-14", "2026-01-14")
    cab = next((r for r in rows if r["plate_number"] == "WP-CAB-1234" and r.get("event_date") == "2026-01-14"), None)
    assert cab is not None
    assert cab["eligible"] == 1


def test_pva_08_date_range_filters_correctly(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-02-01T07:05:00Z", status="ON_TIME_ENTRY")
    _seed_access(seeded_db, "WP-CAB-1234", "2026-03-01T07:05:00Z", status="ON_TIME_ENTRY")
    rows = personal_vehicle_allowance_report(seeded_db, "2026-02-01", "2026-02-28")
    dates = {r["event_date"] for r in rows if r["plate_number"] == "WP-CAB-1234" and r.get("event_date")}
    assert "2026-03-01" not in dates


# ============================================================
# 9-14: ohs_compliance_report  (6 tests)
# ============================================================

def test_ohs_01_returns_all_vehicles(seeded_db):
    total_vehicles = seeded_db.execute("SELECT COUNT(*) FROM registered_vehicles").fetchone()[0]
    rows = ohs_compliance_report(seeded_db)
    assert len(rows) == total_vehicles


def test_ohs_02_left_join_zero_event_vehicle_present(seeded_db):
    """LEFT JOIN: vehicle with zero access_log events must still appear."""
    # Insert a new vehicle with no access_log rows
    seeded_db.execute(
        """INSERT INTO registered_vehicles (plate_number, vehicle_category, vehicle_type)
           VALUES ('TEST-0000', 'STAFF', 'CAR')""",
    )
    rows = ohs_compliance_report(seeded_db)
    plates = [r["plate_number"] for r in rows]
    assert "TEST-0000" in plates
    zero_row = next(r for r in rows if r["plate_number"] == "TEST-0000")
    assert zero_row["total_events"] == 0


def test_ohs_03_non_compliant_first(seeded_db):
    rows = ohs_compliance_report(seeded_db)
    # Non-compliant (is_compliant=0) should appear before compliant (is_compliant=1)
    compliant_flags = [r["is_compliant"] for r in rows]
    first_compliant_idx = next((i for i, v in enumerate(compliant_flags) if v == 1), None)
    first_non_idx = next((i for i, v in enumerate(compliant_flags) if v == 0), None)
    if first_compliant_idx is not None and first_non_idx is not None:
        assert first_non_idx <= first_compliant_idx


def test_ohs_04_suspended_vehicle_not_compliant(seeded_db):
    seeded_db.execute(
        "UPDATE registered_vehicles SET registration_status='SUSPENDED' WHERE plate_number='NW-9900'"
    )
    rows = ohs_compliance_report(seeded_db)
    nw = next(r for r in rows if r["plate_number"] == "NW-9900")
    assert nw["is_compliant"] == 0


def test_ohs_05_overstay_count_tracked(seeded_db):
    recent = (date.today() - timedelta(days=5)).isoformat()
    _seed_access(seeded_db, "WP-CAB-1234", f"{recent}T07:00:00Z", status="ON_TIME_ENTRY")
    _seed_access(seeded_db, "WP-CAB-1234", f"{recent}T18:00:00Z",
                 direction="EXIT", status="OVERSTAY", dwell=39600.0)
    rows = ohs_compliance_report(seeded_db)
    cab = next(r for r in rows if r["plate_number"] == "WP-CAB-1234")
    assert cab["overstay_count"] >= 1


def test_ohs_07_gate_anomaly_count_tracked(seeded_db):
    recent = (date.today() - timedelta(days=3)).isoformat()
    _seed_access(seeded_db, "WP-CAB-1234", f"{recent}T08:00:00Z", status="DOUBLE_ENTRY")
    _seed_access(seeded_db, "WP-CAB-1234", f"{recent}T09:00:00Z",
                 direction="EXIT", status="UNMATCHED_EXIT")
    rows = ohs_compliance_report(seeded_db)
    cab = next(r for r in rows if r["plate_number"] == "WP-CAB-1234")
    assert cab["gate_anomaly_count"] >= 2


def test_ohs_06_vehicle_with_assignment_is_compliant(seeded_db):
    # WP-CAB-1234 is assigned to operator user -> should be compliant
    rows = ohs_compliance_report(seeded_db)
    cab = next(r for r in rows if r["plate_number"] == "WP-CAB-1234")
    assert cab["is_compliant"] == 1


# ============================================================
# 15-18: gate_rejection_audit  (4 tests)
# ============================================================

def test_gr_01_returns_list(seeded_db):
    rows = gate_rejection_audit(seeded_db, "2020-01-01", "2030-12-31")
    assert isinstance(rows, list)


def test_gr_02_rejection_appears(seeded_db):
    _seed_rejection(seeded_db, "WP-AB-3344", "2026-01-10T08:00:00Z")
    rows = gate_rejection_audit(seeded_db, "2026-01-10", "2026-01-10")
    assert any(r["plate_number"] == "WP-AB-3344" for r in rows)


def test_gr_03_filter_by_gate(seeded_db):
    _seed_rejection(seeded_db, "XX-1111", "2026-01-10T09:00:00Z", gate="WORKSHOP_GATE")
    _seed_rejection(seeded_db, "XX-2222", "2026-01-10T09:01:00Z", gate="MAIN_GATE")
    rows = gate_rejection_audit(seeded_db, "2026-01-10", "2026-01-10", gate_id="WORKSHOP_GATE")
    assert all(r["gate_id"] == "WORKSHOP_GATE" for r in rows)


def test_gr_04_date_range_filter(seeded_db):
    _seed_rejection(seeded_db, "YY-0001", "2026-05-01T08:00:00Z")
    rows = gate_rejection_audit(seeded_db, "2026-01-01", "2026-04-30")
    plates = [r["plate_number"] for r in rows]
    assert "YY-0001" not in plates


# ============================================================
# 19-22: admin_audit_report  (4 tests)
# ============================================================

def test_aa_01_returns_list(seeded_db):
    rows = admin_audit_report(seeded_db, "2020-01-01", "2030-12-31")
    assert isinstance(rows, list)


def test_aa_02_row_appears(seeded_db):
    _seed_admin_audit(seeded_db, "admin", "CREATE", "VEHICLE", "WP-TEST-99")
    rows = admin_audit_report(seeded_db, "2026-01-01", "2026-12-31")
    assert any(r["entity_id"] == "WP-TEST-99" for r in rows)


def test_aa_03_filter_by_username(seeded_db):
    _seed_admin_audit(seeded_db, "admin",   "UPDATE", "SHIFT", "DAY")
    _seed_admin_audit(seeded_db, "manager", "UPDATE", "SHIFT", "EVE")
    rows = admin_audit_report(seeded_db, "2026-01-01", "2026-12-31", username="admin")
    assert all(r["username"] == "admin" for r in rows)


def test_aa_04_filter_by_entity_type(seeded_db):
    _seed_admin_audit(seeded_db, "admin", "DELETE", "USER", "5")
    rows = admin_audit_report(seeded_db, "2026-01-01", "2026-12-31", entity_type="USER")
    assert all(r["entity_type"] == "USER" for r in rows)


# ============================================================
# 23-25: daily_attendance_report  (3 tests)
# ============================================================

def test_da_01_returns_all_vehicles(seeded_db):
    total = seeded_db.execute("SELECT COUNT(*) FROM registered_vehicles").fetchone()[0]
    rows = daily_attendance_report(seeded_db, "2026-01-10")
    assert len(rows) == total


def test_da_02_event_on_date_counted(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-15T07:05:00Z", status="ON_TIME_ENTRY")
    rows = daily_attendance_report(seeded_db, "2026-01-15")
    cab = next(r for r in rows if r["plate_number"] == "WP-CAB-1234")
    assert cab["total_events"] >= 1
    assert cab["present"] == 1


def test_da_03_no_event_not_present(seeded_db):
    rows = daily_attendance_report(seeded_db, "2020-06-15")
    for r in rows:
        assert r["present"] == 0


# ============================================================
# 26-28: weekly_attendance_report  (3 tests)
# ============================================================

def test_wa_01_returns_list(seeded_db):
    rows = weekly_attendance_report(seeded_db, "2026-01-05")
    assert isinstance(rows, list)


def test_wa_02_days_present_counted(seeded_db):
    for day in ["2026-01-05", "2026-01-06", "2026-01-07"]:
        _seed_access(seeded_db, "WP-CAB-1234", f"{day}T07:05:00Z")
    rows = weekly_attendance_report(seeded_db, "2026-01-05")
    cab = next(r for r in rows if r["plate_number"] == "WP-CAB-1234")
    assert cab["days_present"] == 3


def test_wa_03_outside_week_not_counted(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-12T07:05:00Z")  # Next week
    rows = weekly_attendance_report(seeded_db, "2026-01-05")
    cab = next(r for r in rows if r["plate_number"] == "WP-CAB-1234")
    assert cab["days_present"] == 0


# ============================================================
# 29-31: monthly_attendance_report  (3 tests)
# ============================================================

def test_ma_01_returns_list(seeded_db):
    rows = monthly_attendance_report(seeded_db, 2026, 1)
    assert isinstance(rows, list)


def test_ma_02_events_in_month_counted(seeded_db):
    for day in ["2026-02-01", "2026-02-03", "2026-02-05"]:
        _seed_access(seeded_db, "WP-CAB-1234", f"{day}T07:05:00Z")
    rows = monthly_attendance_report(seeded_db, 2026, 2)
    cab = next(r for r in rows if r["plate_number"] == "WP-CAB-1234")
    assert cab["days_present"] == 3


def test_ma_03_different_month_excluded(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-03-01T07:05:00Z")
    rows = monthly_attendance_report(seeded_db, 2026, 2)
    cab = next(r for r in rows if r["plate_number"] == "WP-CAB-1234")
    assert cab["days_present"] == 0


# ============================================================
# 32-35: gate_throughput_report  (4 tests)
# ============================================================

def test_gt_01_returns_list(seeded_db):
    rows = gate_throughput_report(seeded_db, "2026-01-01", "2026-12-31")
    assert isinstance(rows, list)


def test_gt_02_event_appears(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-20T08:30:00Z", gate="MAIN_GATE")
    rows = gate_throughput_report(seeded_db, "2026-01-20", "2026-01-20")
    assert any(r["gate_id"] == "MAIN_GATE" for r in rows)


def test_gt_03_direction_separated(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-21T08:00:00Z", direction="ENTRY")
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-21T16:00:00Z", direction="EXIT")
    rows = gate_throughput_report(seeded_db, "2026-01-21", "2026-01-21")
    directions = {r["direction"] for r in rows}
    assert "ENTRY" in directions
    assert "EXIT" in directions


def test_gt_04_hour_granularity(seeded_db):
    for h in range(7, 10):
        _seed_access(seeded_db, "WP-CAB-1234", f"2026-01-22T{h:02d}:00:00Z")
    rows = gate_throughput_report(seeded_db, "2026-01-22", "2026-01-22")
    hours = {r["hour"] for r in rows}
    assert len(hours) >= 3


# ============================================================
# 36-38: zone_occupancy_snapshot  (3 tests)
# ============================================================

def test_zo_01_returns_all_zones(seeded_db):
    total_zones = seeded_db.execute("SELECT COUNT(*) FROM cdl_zones").fetchone()[0]
    rows = zone_occupancy_snapshot(seeded_db)
    assert len(rows) == total_zones


def test_zo_02_occupancy_increases_on_entry(seeded_db):
    _seed_access(seeded_db, "WP-CAB-1234", "2026-01-25T07:00:00Z", gate="MAIN_GATE", direction="ENTRY")
    rows = zone_occupancy_snapshot(seeded_db)
    dd1 = next((r for r in rows if r["zone_id"] == "DRYDOCK_1"), None)
    assert dd1 is not None
    assert dd1["current_occupancy"] >= 1


def test_zo_03_utilisation_pct_computed(seeded_db):
    rows = zone_occupancy_snapshot(seeded_db)
    for r in rows:
        assert "utilisation_pct" in r
        assert r["utilisation_pct"] >= 0.0


# ============================================================
# 39-42: subcontractor_billing_audit  (4 tests)
# ============================================================

def test_sb_01_returns_list(seeded_db):
    rows = subcontractor_billing_audit(seeded_db)
    assert isinstance(rows, list)


def test_sb_02_subcontractor_vehicle_appears(seeded_db):
    _seed_access(seeded_db, "WP-KA-5678", "2026-01-10T15:00:00Z",
                 direction="EXIT", status="ON_TIME_EXIT", dwell=28800.0)
    rows = subcontractor_billing_audit(seeded_db, date_from="2026-01-10", date_to="2026-01-10")
    plates = [r["plate_number"] for r in rows]
    assert "WP-KA-5678" in plates


def test_sb_03_filter_by_company(seeded_db):
    rows = subcontractor_billing_audit(seeded_db, company_id="SCO-001")
    assert all(r["company_id"] == "SCO-001" for r in rows)


def test_sb_04_billed_hours_from_dwell(seeded_db):
    _seed_access(seeded_db, "WP-KA-5678", "2026-01-11T15:00:00Z",
                 direction="EXIT", status="ON_TIME_EXIT", dwell=7200.0)  # 2 hours
    rows = subcontractor_billing_audit(seeded_db, company_id="SCO-001",
                                       date_from="2026-01-11", date_to="2026-01-11")
    sco = next((r for r in rows if r["plate_number"] == "WP-KA-5678"), None)
    assert sco is not None
    assert sco["billed_hours"] == pytest.approx(2.0, abs=0.01)


# ============================================================
# 43-45: Export helpers  (3 tests)
# ============================================================

def test_exp_01_csv_string_round_trip():
    rows = [{"a": 1, "b": "hello"}, {"a": 2, "b": "world"}]
    s = csv_string(rows)
    reader = csv.DictReader(io.StringIO(s))
    parsed = list(reader)
    assert parsed[0]["a"] == "1"
    assert parsed[1]["b"] == "world"


def test_exp_02_export_csv_to_file(seeded_db, tmp_path):
    rows = [{"plate": "WP-CAB-1234", "status": "OK"}]
    fp = tmp_path / "out.csv"
    export_csv(rows, fp)
    content = fp.read_text()
    assert "WP-CAB-1234" in content


def test_exp_03_export_pdf_produces_bytes(seeded_db, tmp_path):
    rows = [{"plate": "WP-CAB-1234", "status": "OK", "count": 5}]
    fp = tmp_path / "report.pdf"
    export_pdf(rows, fp, title="Test Report", date_range_str="2026-01-01 to 2026-01-31")
    assert fp.exists()
    assert fp.stat().st_size > 100
    # First 4 bytes of a PDF are %PDF
    assert fp.read_bytes()[:4] == b"%PDF"
