from __future__ import annotations

"""15 tests for src/projects.py -- CDL Specialisation Layer.

Coverage
--------
1.  create_zone + get_zone round-trip
2.  create_zone rejects invalid zone_type (ValueError)
3.  create_project raises FK violation when zone_id missing
4.  list_projects filtered by status
5.  close_project sets status=CLOSED
6.  close_project soft-removes assignments (removed_at set)
7.  close_project does not hard-delete rows
8.  assign_vehicle_to_project: SUBCONTRACTOR without company_id -> ValueError
9.  assign_vehicle_to_project: SUBCONTRACTOR with non-existent company_id -> ValueError
10. assign_vehicle_to_project: EMPLOYEE without company_id accepted
11. get_project_attendance_summary distinct-day counting
12. list_companies filtered by approval_status (SUSPENDED)
13. get_zone_occupancy: counts unmatched ENTRY events
14. list_project_vehicles active_only=True filters removed assignments
15. resolve_event_attribution matches gate in zone's associated_gates
"""

import json
import sqlite3

import pytest

from src.projects import (
    create_zone, get_zone, list_zones, get_zone_occupancy,
    create_company, get_company, list_companies,
    create_project, get_project, list_projects,
    close_project, assign_vehicle_to_project,
    unassign_vehicle_from_project, list_project_vehicles,
    get_project_attendance_summary,
    get_subcontractor_hours, resolve_event_attribution,
)
from src.audit import log_gate_event

def test_01_create_and_get_zone(db):
    create_zone(db, "DD_TEST", "Test Dock", "DRYDOCK", ["GATE_A", "GATE_B"], 25)
    zone = get_zone(db, "DD_TEST")
    assert zone is not None
    assert zone["zone_id"] == "DD_TEST"
    assert zone["zone_name"] == "Test Dock"
    assert zone["zone_type"] == "DRYDOCK"
    assert zone["vehicle_capacity"] == 25

def test_02_invalid_zone_type_raises(db):
    with pytest.raises(ValueError, match="zone_type"):
        create_zone(db, "BAD", "Bad Zone", "HELIPAD", ["GATE_X"])

def test_03_create_project_fk_violation(db):
    db.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        create_project(db, "PRJ-X", "MV Ghost", "NONEXISTENT_ZONE", "2026-01-01")

def test_04_list_projects_by_status(seeded_db):
    projects_active = list_projects(seeded_db, status="ACTIVE")
    assert len(projects_active) == 2
    close_project(seeded_db, "PRJ-2026-001", "2026-06-01")
    projects_active_after = list_projects(seeded_db, status="ACTIVE")
    assert len(projects_active_after) == 1
    projects_closed = list_projects(seeded_db, status="CLOSED")
    assert len(projects_closed) == 1

def test_05_close_project_sets_status(seeded_db):
    close_project(seeded_db, "PRJ-2026-001", "2026-06-01")
    p = get_project(seeded_db, "PRJ-2026-001")
    assert p["status"] == "CLOSED"
    assert p["end_date"] == "2026-06-01"

def test_06_close_project_soft_removes_assignments(seeded_db):
    close_project(seeded_db, "PRJ-2026-001", "2026-06-01")
    active = list_project_vehicles(seeded_db, "PRJ-2026-001", active_only=True)
    assert len(active) == 0
    all_rows = list_project_vehicles(seeded_db, "PRJ-2026-001", active_only=False)
    assert len(all_rows) > 0
    for row in all_rows:
        assert row["removed_at"] is not None

def test_07_close_project_no_hard_delete(seeded_db):
    count_before = seeded_db.execute(
        "SELECT COUNT(*) FROM project_vehicle_assignments WHERE project_code='PRJ-2026-001'"
    ).fetchone()[0]
    close_project(seeded_db, "PRJ-2026-001", "2026-06-01")
    count_after = seeded_db.execute(
        "SELECT COUNT(*) FROM project_vehicle_assignments WHERE project_code='PRJ-2026-001'"
    ).fetchone()[0]
    assert count_before == count_after

def test_08_subcontractor_requires_company_id(seeded_db):
    with pytest.raises(ValueError, match="company_id is required"):
        assign_vehicle_to_project(
            seeded_db, "PRJ-2026-001", "WP-CD-7788", "SUBCONTRACTOR", company_id=None
        )

def test_09_subcontractor_nonexistent_company_raises(seeded_db):
    with pytest.raises(ValueError, match="does not exist"):
        assign_vehicle_to_project(
            seeded_db, "PRJ-2026-001", "WP-CD-7788", "SUBCONTRACTOR", company_id="SCO-GHOST"
        )

def test_10_employee_without_company_id_accepted(seeded_db):
    assign_vehicle_to_project(
        seeded_db, "PRJ-2026-001", "WP-EF-2233", "EMPLOYEE", company_id=None
    )
    vehicles = list_project_vehicles(seeded_db, "PRJ-2026-001")
    plates = [v["plate_number"] for v in vehicles]
    assert "WP-EF-2233" in plates

def test_11_attendance_summary_distinct_days(seeded_db):

    for ts in ["2026-01-10T07:05:00Z", "2026-01-10T15:10:00Z", "2026-01-11T07:03:00Z"]:
        log_gate_event(
            seeded_db, "WP-CAB-1234", ts, "MAIN_GATE", "ENTRY", status="ON_TIME_ENTRY"
        )
    summary = get_project_attendance_summary(seeded_db, "PRJ-2026-001", "2026-01-01", "2026-12-31")
    cab = next((r for r in summary if r["plate_number"] == "WP-CAB-1234"), None)
    assert cab is not None

    assert cab["days_present"] == 2

def test_12_list_companies_filter_suspended(seeded_db):
    seeded_db.execute(
        "UPDATE subcontractor_companies SET approval_status='SUSPENDED' WHERE company_id='SCO-002'"
    )
    suspended = list_companies(seeded_db, approval_status="SUSPENDED")
    assert len(suspended) == 1
    assert suspended[0]["company_id"] == "SCO-002"
    approved = list_companies(seeded_db, approval_status="APPROVED")
    assert all(c["approval_status"] == "APPROVED" for c in approved)

def test_13_zone_occupancy(seeded_db):

    log_gate_event(seeded_db, "WP-CAB-1234", "2026-01-10T07:00:00Z", "MAIN_GATE", "ENTRY")
    occ = get_zone_occupancy(seeded_db, "DRYDOCK_1")
    assert occ >= 1

    log_gate_event(seeded_db, "WP-CAB-1234", "2026-01-10T15:00:00Z", "MAIN_GATE", "EXIT")
    occ_after = get_zone_occupancy(seeded_db, "DRYDOCK_1")
    assert occ_after < occ or occ_after == 0

def test_14_list_project_vehicles_active_only(seeded_db):
    unassign_vehicle_from_project(seeded_db, "PRJ-2026-001", "WP-KA-5678", "2026-03-01")
    active = list_project_vehicles(seeded_db, "PRJ-2026-001", active_only=True)
    plates = [v["plate_number"] for v in active]
    assert "WP-KA-5678" not in plates
    all_rows = list_project_vehicles(seeded_db, "PRJ-2026-001", active_only=False)
    all_plates = [v["plate_number"] for v in all_rows]
    assert "WP-KA-5678" in all_plates

def test_15_resolve_event_attribution(seeded_db):

    zone_id, project_code = resolve_event_attribution(
        seeded_db, "WP-CAB-1234", "MAIN_GATE", "2026-01-10T07:00:00Z"
    )
    assert zone_id == "DRYDOCK_1"
    assert project_code == "PRJ-2026-001"

    z2, p2 = resolve_event_attribution(
        seeded_db, "NW-9900", "MAIN_GATE", "2026-01-10T07:00:00Z"
    )
    assert z2 is None
    assert p2 is None
