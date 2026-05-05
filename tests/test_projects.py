"""15 tests for CDL Project and Zone Management (src/projects.py).

Covers: zone CRUD, subcontractor CRUD, project lifecycle, vehicle assignment,
attendance summary analytics, zone occupancy, and subcontractor billing hours.
"""
from __future__ import annotations

import pytest

from src.database import transaction
from src.projects import (
    assign_vehicle_to_project,
    close_project,
    create_project,
    create_subcontractor,
    create_zone,
    get_project,
    get_project_attendance_summary,
    get_subcontractor_hours,
    get_zone,
    get_zone_occupancy,
    list_project_vehicles,
    list_projects,
    list_subcontractors,
    list_zones,
    remove_vehicle_from_project,
    suspend_subcontractor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_zone(db, zone_id="DRYDOCK_1"):
    create_zone(db, zone_id, f"Graving Drydock No. 1", "DRYDOCK",
                ["GATE_A", "GATE_B"], capacity_vehicles=30)


def _seed_vehicle(db, plate="CDL-001"):
    db.execute(
        "INSERT OR IGNORE INTO registered_vehicles "
        "(plate_number, vehicle_category, registration_status) VALUES (?,?,'ACTIVE')",
        (plate, "STAFF"),
    )


def _seed_project(db, code="CDL-2026-001"):
    _seed_zone(db)
    create_project(db, code, "MV Colombo Trader Overhaul",
                   "DRYDOCK_1", "2026-01-15", vessel_name="MV Colombo Trader")


def _log_entry(db, plate, ts, gate="GATE_A", dwell=3600.0):
    from src.audit import compute_row_hash, get_prev_hash
    from src.database import transaction as tx
    with tx(db) as cur:
        prev = get_prev_hash(cur)
        cur.execute(
            "INSERT INTO access_log "
            "(plate_number,timestamp,gate_id,direction,dwell_time_seconds,"
            "status,row_hash) VALUES (?,?,?,?,?,?,?)",
            (plate, ts, gate, "ENTRY", dwell, "ON_TIME_ENTRY", "PENDING"),
        )
        rid = cur.lastrowid
        h = compute_row_hash(rid, plate, ts, gate, "ENTRY", prev)
        cur.execute("UPDATE access_log SET row_hash=? WHERE id=?", (h, rid))


# ---------------------------------------------------------------------------
# Zone tests
# ---------------------------------------------------------------------------

def test_create_and_retrieve_zone(db):
    create_zone(db, "DRYDOCK_2", "Graving Drydock No. 2", "DRYDOCK",
                ["GATE_C", "GATE_D"], capacity_vehicles=40,
                description="Largest drydock, up to 125,000 DWT")
    zone = get_zone(db, "DRYDOCK_2")
    assert zone is not None
    assert zone["zone_name"] == "Graving Drydock No. 2"
    assert zone["zone_type"] == "DRYDOCK"
    assert zone["capacity_vehicles"] == 40


def test_list_zones_returns_all(db):
    create_zone(db, "DRYDOCK_1", "Drydock 1", "DRYDOCK", ["GATE_A"])
    create_zone(db, "ADMIN_BLOCK", "Admin Block", "ADMIN", ["GATE_MAIN"])
    zones = list_zones(db)
    assert len(zones) == 2


def test_create_zone_invalid_type_raises(db):
    with pytest.raises(ValueError, match="Invalid zone_type"):
        create_zone(db, "Z1", "Z1", "SUBMARINE_BASE", ["GATE_X"])


def test_create_zone_empty_gates_raises(db):
    with pytest.raises(ValueError, match="gate_ids"):
        create_zone(db, "Z2", "Z2", "WORKSHOP", [])


# ---------------------------------------------------------------------------
# Subcontractor tests
# ---------------------------------------------------------------------------

def test_create_and_list_subcontractor(db):
    create_subcontractor(db, "SC-001", "Lanka Marine Services Ltd.",
                         contact_name="Ruwan Perera", approved_until="2027-12-31")
    subs = list_subcontractors(db)
    assert len(subs) == 1
    assert subs[0]["company_name"] == "Lanka Marine Services Ltd."


def test_suspend_subcontractor(db):
    create_subcontractor(db, "SC-002", "Precision Welding Co.")
    suspend_subcontractor(db, "SC-002")
    active = list_subcontractors(db, status="APPROVED")
    suspended = list_subcontractors(db, status="SUSPENDED")
    assert len(active) == 0
    assert len(suspended) == 1


# ---------------------------------------------------------------------------
# Project lifecycle tests
# ---------------------------------------------------------------------------

def test_create_and_get_project(db):
    _seed_zone(db)
    create_project(db, "CDL-2026-042", "MV Sun Pearl — Routine Dry-Docking",
                   "DRYDOCK_1", "2026-04-01", vessel_name="MV Sun Pearl",
                   end_date="2026-04-21", project_manager="K. Bandara")
    proj = get_project(db, "CDL-2026-042")
    assert proj is not None
    assert proj["vessel_name"] == "MV Sun Pearl"
    assert proj["status"] == "ACTIVE"
    assert proj["zone_name"] == "Graving Drydock No. 1"


def test_list_active_projects(db):
    _seed_zone(db)
    create_project(db, "P-001", "Project Alpha", "DRYDOCK_1", "2026-01-01")
    create_project(db, "P-002", "Project Beta", "DRYDOCK_1", "2026-02-01")
    db.execute("UPDATE projects SET status='COMPLETED' WHERE project_code='P-002'")
    active = list_projects(db, status="ACTIVE")
    assert len(active) == 1
    assert active[0]["project_code"] == "P-001"


def test_close_project_marks_completed(db):
    _seed_project(db)
    _seed_vehicle(db)
    aid = assign_vehicle_to_project(db, "CDL-2026-001", "CDL-001")
    close_project(db, "CDL-2026-001", end_date="2026-03-15")
    proj = get_project(db, "CDL-2026-001")
    assert proj["status"] == "COMPLETED"
    assert proj["end_date"] == "2026-03-15"
    # assignment should be auto-closed
    vehicles = list_project_vehicles(db, "CDL-2026-001", active_only=True)
    assert len(vehicles) == 0


# ---------------------------------------------------------------------------
# Vehicle assignment tests
# ---------------------------------------------------------------------------

def test_assign_and_list_vehicle(db):
    _seed_project(db)
    _seed_vehicle(db, "CDL-002")
    aid = assign_vehicle_to_project(db, "CDL-2026-001", "CDL-002",
                                    role="EMPLOYEE")
    assert isinstance(aid, int) and aid > 0
    vehicles = list_project_vehicles(db, "CDL-2026-001")
    assert len(vehicles) == 1
    assert vehicles[0]["plate_number"] == "CDL-002"


def test_assign_subcontractor_requires_company_id(db):
    _seed_project(db)
    _seed_vehicle(db, "SC-VAN-01")
    with pytest.raises(ValueError, match="company_id"):
        assign_vehicle_to_project(db, "CDL-2026-001", "SC-VAN-01",
                                  role="SUBCONTRACTOR")


def test_remove_vehicle_from_project(db):
    _seed_project(db)
    _seed_vehicle(db, "CDL-003")
    aid = assign_vehicle_to_project(db, "CDL-2026-001", "CDL-003")
    remove_vehicle_from_project(db, aid, removed_at="2026-02-28T17:00:00Z")
    active = list_project_vehicles(db, "CDL-2026-001", active_only=True)
    assert len(active) == 0
    all_veh = list_project_vehicles(db, "CDL-2026-001", active_only=False)
    assert len(all_veh) == 1


# ---------------------------------------------------------------------------
# Analytics tests
# ---------------------------------------------------------------------------

def test_project_attendance_summary(db):
    _seed_project(db)
    _seed_vehicle(db, "CDL-STAFF-01")
    assign_vehicle_to_project(db, "CDL-2026-001", "CDL-STAFF-01")
    _log_entry(db, "CDL-STAFF-01", "2026-02-01T08:15:00Z", dwell=28800.0)  # 8 hours
    _log_entry(db, "CDL-STAFF-01", "2026-02-02T08:05:00Z", dwell=28800.0)
    summary = get_project_attendance_summary(db, "CDL-2026-001",
                                             "2026-02-01", "2026-02-28")
    assert len(summary) == 1
    rec = summary[0]
    assert rec["plate_number"] == "CDL-STAFF-01"
    assert rec["days_present"] == 2
    assert rec["total_hours"] == pytest.approx(16.0, rel=1e-3)


def test_zone_occupancy(db):
    create_zone(db, "DRYDOCK_3", "Drydock 3", "DRYDOCK", ["GATE_E"])
    _seed_vehicle(db, "OCC-001")
    _seed_vehicle(db, "OCC-002")
    _log_entry(db, "OCC-001", "2026-03-01T07:00:00Z", gate="GATE_E")
    _log_entry(db, "OCC-002", "2026-03-01T07:30:00Z", gate="GATE_E")
    # OCC-001 exits at 15:00
    db.execute(
        "INSERT INTO access_log (plate_number,timestamp,gate_id,direction,status,row_hash) "
        "VALUES ('OCC-001','2026-03-01T15:00:00Z','GATE_E','EXIT','ON_TIME_EXIT','x')"
    )
    occupancy = get_zone_occupancy(db, "DRYDOCK_3",
                                   as_of_ts="2026-03-01T16:00:00Z")
    assert occupancy == 1  # only OCC-002 still inside


def test_subcontractor_hours(db):
    _seed_zone(db)
    create_subcontractor(db, "SC-STEEL", "Steel Works Lanka Pvt Ltd")
    create_project(db, "CDL-2026-100", "Hull Plating — DD1",
                   "DRYDOCK_1", "2026-03-01")
    _seed_vehicle(db, "SW-VAN-01")
    db.execute(
        "UPDATE registered_vehicles SET company_id='SC-STEEL' WHERE plate_number='SW-VAN-01'"
    )
    assign_vehicle_to_project(db, "CDL-2026-100", "SW-VAN-01",
                              role="SUBCONTRACTOR", company_id="SC-STEEL")
    _log_entry(db, "SW-VAN-01", "2026-03-10T08:00:00Z", dwell=21600.0)  # 6 hours
    _log_entry(db, "SW-VAN-01", "2026-03-11T08:00:00Z", dwell=21600.0)
    report = get_subcontractor_hours(db, "SC-STEEL", "2026-03-01", "2026-03-31")
    assert len(report) == 1
    assert report[0]["total_hours"] == pytest.approx(12.0, rel=1e-3)
    assert report[0]["project_code"] == "CDL-2026-100"
