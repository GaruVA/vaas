"""CDL Project and Zone Management (§6.4 — CDL Specialisation Layer).

Colombo Dockyard PLC operates a continuous-throughput shipyard inside the Port
of Colombo with four graving drydocks capable of handling vessels up to 125,000
DWT.  Vehicle attendance must be attributed to an active drydock or infrastructure
project so that:

  1. CDL management can verify contractor billing hours against gate-log data.
  2. The employee incentive programme (personal-vehicle allowance) can be
     calculated per project rather than globally — an employee who drives to
     site for a short turnaround project earns the same recognition as one on a
     long refit (both logged; management filters by project as needed).
  3. Sub-contractor compliance officers can view real-time headcounts per project.

Public API
----------
create_zone(conn, zone_id, zone_name, zone_type, gate_ids, capacity, description)
list_zones(conn) -> list[sqlite3.Row]

create_subcontractor(conn, company_id, company_name, ...) -> None
list_subcontractors(conn, status="APPROVED") -> list[sqlite3.Row]

create_project(conn, project_code, project_name, zone_id, start_date, ...) -> None
get_project(conn, project_code) -> sqlite3.Row | None
list_projects(conn, status="ACTIVE") -> list[sqlite3.Row]
close_project(conn, project_code, end_date) -> None

assign_vehicle_to_project(conn, project_code, plate_number, role, company_id, assigned_by) -> int
remove_vehicle_from_project(conn, assignment_id, removed_at) -> None
list_project_vehicles(conn, project_code, active_only=True) -> list[sqlite3.Row]

get_project_attendance_summary(conn, project_code, date_from, date_to) -> list[dict]
get_zone_occupancy(conn, zone_id, as_of_ts) -> int
get_subcontractor_hours(conn, company_id, date_from, date_to) -> list[dict]
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from src.database import transaction


# ---------------------------------------------------------------------------
# Zone management
# ---------------------------------------------------------------------------

def create_zone(
    conn: sqlite3.Connection,
    zone_id: str,
    zone_name: str,
    zone_type: str,
    gate_ids: list[str],
    capacity_vehicles: int = 50,
    description: str | None = None,
) -> None:
    """Insert a new physical zone into cdl_zones.

    Parameters
    ----------
    zone_id:           Short unique key, e.g. 'DRYDOCK_1'.
    zone_name:         Human-readable label, e.g. 'Graving Drydock No. 1'.
    zone_type:         One of DRYDOCK | BERTH | WORKSHOP | ADMIN | SECURITY.
    gate_ids:          List of gate_id values that control access to this zone.
    capacity_vehicles: Maximum number of vehicles permitted simultaneously.
    description:       Optional free-text description.
    """
    if not zone_id or not zone_id.strip():
        raise ValueError("zone_id must be a non-empty string")
    if zone_type not in ("DRYDOCK", "BERTH", "WORKSHOP", "ADMIN", "SECURITY"):
        raise ValueError(f"Invalid zone_type: {zone_type!r}")
    if capacity_vehicles < 1:
        raise ValueError("capacity_vehicles must be >= 1")
    if not gate_ids:
        raise ValueError("gate_ids must contain at least one gate")

    with transaction(conn) as cur:
        cur.execute(
            "INSERT INTO cdl_zones (zone_id, zone_name, zone_type, gate_ids, "
            "capacity_vehicles, description) VALUES (?,?,?,?,?,?)",
            (zone_id.strip(), zone_name.strip(), zone_type,
             json.dumps(gate_ids), capacity_vehicles, description),
        )


def list_zones(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all zones ordered by zone_type then zone_id."""
    return conn.execute(
        "SELECT * FROM cdl_zones ORDER BY zone_type, zone_id"
    ).fetchall()


def get_zone(conn: sqlite3.Connection, zone_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM cdl_zones WHERE zone_id=?", (zone_id,)
    ).fetchone()


# ---------------------------------------------------------------------------
# Subcontractor company management
# ---------------------------------------------------------------------------

def create_subcontractor(
    conn: sqlite3.Connection,
    company_id: str,
    company_name: str,
    contact_name: str | None = None,
    contact_phone: str | None = None,
    approved_until: str | None = None,
) -> None:
    """Register an approved sub-contracting firm."""
    if not company_id or not company_name:
        raise ValueError("company_id and company_name are required")
    with transaction(conn) as cur:
        cur.execute(
            "INSERT INTO subcontractor_companies "
            "(company_id, company_name, contact_name, contact_phone, approved_until) "
            "VALUES (?,?,?,?,?)",
            (company_id.strip(), company_name.strip(), contact_name,
             contact_phone, approved_until),
        )


def list_subcontractors(
    conn: sqlite3.Connection, status: str = "APPROVED"
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM subcontractor_companies WHERE status=? ORDER BY company_name",
        (status,),
    ).fetchall()


def get_subcontractor(
    conn: sqlite3.Connection, company_id: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM subcontractor_companies WHERE company_id=?", (company_id,)
    ).fetchone()


def suspend_subcontractor(conn: sqlite3.Connection, company_id: str) -> None:
    """Mark a sub-contractor as SUSPENDED (e.g. failed safety audit)."""
    with transaction(conn) as cur:
        cur.execute(
            "UPDATE subcontractor_companies SET status='SUSPENDED' WHERE company_id=?",
            (company_id,),
        )


# ---------------------------------------------------------------------------
# Project (vessel / drydock job) management
# ---------------------------------------------------------------------------

def create_project(
    conn: sqlite3.Connection,
    project_code: str,
    project_name: str,
    zone_id: str,
    start_date: str,
    vessel_name: str | None = None,
    end_date: str | None = None,
    project_manager: str | None = None,
    notes: str | None = None,
) -> None:
    """Create a new drydock / infrastructure project.

    Parameters
    ----------
    project_code:    Unique code, e.g. 'CDL-2026-042'.
    project_name:    Descriptive name, e.g. 'MV Colombo Trader — Annual Survey'.
    zone_id:         Physical zone where the work is performed.
    start_date:      ISO-8601 date string, e.g. '2026-03-01'.
    vessel_name:     Name of the vessel (None for non-vessel projects).
    end_date:        Planned completion date; may be None for open-ended projects.
    project_manager: Name of the CDL project manager.
    notes:           Free-text remarks.

    Raises
    ------
    ValueError  if project_code, project_name, zone_id, or start_date are empty.
    sqlite3.IntegrityError  if zone_id does not exist in cdl_zones.
    """
    for label, value in [("project_code", project_code),
                         ("project_name", project_name),
                         ("zone_id", zone_id),
                         ("start_date", start_date)]:
        if not value or not str(value).strip():
            raise ValueError(f"{label} must be a non-empty string")

    with transaction(conn) as cur:
        cur.execute(
            "INSERT INTO projects (project_code, project_name, vessel_name, zone_id, "
            "start_date, end_date, project_manager, notes) VALUES (?,?,?,?,?,?,?,?)",
            (project_code.strip(), project_name.strip(), vessel_name,
             zone_id.strip(), start_date, end_date, project_manager, notes),
        )


def get_project(
    conn: sqlite3.Connection, project_code: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT p.*, z.zone_name, z.zone_type "
        "FROM projects p JOIN cdl_zones z ON p.zone_id=z.zone_id "
        "WHERE p.project_code=?",
        (project_code,),
    ).fetchone()


def list_projects(
    conn: sqlite3.Connection, status: str = "ACTIVE"
) -> list[sqlite3.Row]:
    """Return projects filtered by status, newest first."""
    return conn.execute(
        "SELECT p.*, z.zone_name FROM projects p "
        "JOIN cdl_zones z ON p.zone_id=z.zone_id "
        "WHERE p.status=? ORDER BY p.start_date DESC",
        (status,),
    ).fetchall()


def close_project(
    conn: sqlite3.Connection,
    project_code: str,
    end_date: str | None = None,
) -> None:
    """Mark a project COMPLETED and record actual end_date."""
    actual_end = end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with transaction(conn) as cur:
        cur.execute(
            "UPDATE projects SET status='COMPLETED', end_date=? "
            "WHERE project_code=?",
            (actual_end, project_code),
        )
        # Automatically remove all active vehicle assignments
        cur.execute(
            "UPDATE project_vehicle_assignments SET removed_at=? "
            "WHERE project_code=? AND removed_at IS NULL",
            (actual_end, project_code),
        )


# ---------------------------------------------------------------------------
# Vehicle ↔ Project assignment
# ---------------------------------------------------------------------------

def assign_vehicle_to_project(
    conn: sqlite3.Connection,
    project_code: str,
    plate_number: str,
    role: str = "EMPLOYEE",
    company_id: str | None = None,
    assigned_by: int | None = None,
    notes: str | None = None,
) -> int:
    """Assign a vehicle to a project and return the assignment id.

    A vehicle may be assigned to multiple concurrent projects (e.g. an
    engineer's personal car used across two drydock jobs on the same day).
    The attendance analytics join on gate timestamps to disambiguate.

    Parameters
    ----------
    role:        EMPLOYEE | SUBCONTRACTOR | SUPERVISOR | VISITOR.
    company_id:  Must reference subcontractor_companies if role=SUBCONTRACTOR.

    Returns
    -------
    int  — the new project_vehicle_assignments.id value.
    """
    if role not in ("EMPLOYEE", "SUBCONTRACTOR", "SUPERVISOR", "VISITOR"):
        raise ValueError(f"Invalid role: {role!r}")
    if role == "SUBCONTRACTOR" and not company_id:
        raise ValueError("company_id is required when role='SUBCONTRACTOR'")
    if company_id:
        row = conn.execute(
            "SELECT 1 FROM subcontractor_companies WHERE company_id=?",
            (company_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"company_id {company_id!r} not found in subcontractor_companies")

    with transaction(conn) as cur:
        cur.execute(
            "INSERT INTO project_vehicle_assignments "
            "(project_code, plate_number, role, company_id, assigned_by, notes) "
            "VALUES (?,?,?,?,?,?)",
            (project_code, plate_number, role, company_id, assigned_by, notes),
        )
        return cur.lastrowid


def remove_vehicle_from_project(
    conn: sqlite3.Connection,
    assignment_id: int,
    removed_at: str | None = None,
) -> None:
    """Set removed_at on an assignment, marking it no longer active."""
    ts = removed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with transaction(conn) as cur:
        cur.execute(
            "UPDATE project_vehicle_assignments SET removed_at=? WHERE id=?",
            (ts, assignment_id),
        )


def list_project_vehicles(
    conn: sqlite3.Connection,
    project_code: str,
    active_only: bool = True,
) -> list[sqlite3.Row]:
    """Return vehicles assigned to a project, with vehicle metadata."""
    base = (
        "SELECT pva.*, rv.vehicle_category, rv.vehicle_type, rv.department, "
        "sc.company_name "
        "FROM project_vehicle_assignments pva "
        "JOIN registered_vehicles rv ON pva.plate_number=rv.plate_number "
        "LEFT JOIN subcontractor_companies sc ON pva.company_id=sc.company_id "
        "WHERE pva.project_code=?"
    )
    if active_only:
        base += " AND pva.removed_at IS NULL"
    base += " ORDER BY pva.assigned_at"
    return conn.execute(base, (project_code,)).fetchall()


# ---------------------------------------------------------------------------
# Analytics — the core value-add for CDL management
# ---------------------------------------------------------------------------

def get_project_attendance_summary(
    conn: sqlite3.Connection,
    project_code: str,
    date_from: str,
    date_to: str,
) -> list[dict]:
    """Per-vehicle attendance summary for a project over a date range.

    For each vehicle assigned to the project, computes the number of days
    it was seen at the gate and total dwell time in hours.  This directly
    feeds the employee incentive calculation and contractor billing audit.

    Parameters
    ----------
    date_from, date_to:  ISO-8601 date strings inclusive, e.g. '2026-04-01'.

    Returns
    -------
    list of dicts, one per vehicle, sorted by days_present descending.
    Keys: plate_number, role, company_name, days_present, total_hours, vehicle_category.
    """
    rows = conn.execute(
        """
        SELECT
            pva.plate_number,
            pva.role,
            COALESCE(sc.company_name, 'CDL Internal') AS company_name,
            rv.vehicle_category,
            COUNT(DISTINCT DATE(al.timestamp)) AS days_present,
            ROUND(SUM(COALESCE(al.dwell_time_seconds, 0)) / 3600.0, 2) AS total_hours
        FROM project_vehicle_assignments pva
        JOIN registered_vehicles rv ON pva.plate_number = rv.plate_number
        LEFT JOIN subcontractor_companies sc ON pva.company_id = sc.company_id
        LEFT JOIN access_log al
            ON  al.plate_number = pva.plate_number
            AND al.direction    = 'ENTRY'
            AND DATE(al.timestamp) BETWEEN ? AND ?
        WHERE pva.project_code = ?
          AND (pva.removed_at IS NULL OR DATE(pva.removed_at) >= ?)
        GROUP BY pva.plate_number, pva.role, sc.company_name, rv.vehicle_category
        ORDER BY days_present DESC, total_hours DESC
        """,
        (date_from, date_to, project_code, date_from),
    ).fetchall()
    return [dict(r) for r in rows]


def get_zone_occupancy(
    conn: sqlite3.Connection,
    zone_id: str,
    as_of_ts: str | None = None,
) -> int:
    """Count vehicles currently inside a zone (ENTRY without matching EXIT).

    Parameters
    ----------
    zone_id:   Zone to check.
    as_of_ts:  ISO-8601 timestamp ceiling; defaults to now (UTC).

    Returns
    -------
    int — number of vehicles with unmatched ENTRY events in the zone's gates.
    """
    ceiling = as_of_ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    zone = get_zone(conn, zone_id)
    if zone is None:
        raise ValueError(f"Unknown zone_id: {zone_id!r}")
    gate_ids = json.loads(zone["gate_ids"])
    placeholders = ",".join("?" * len(gate_ids))
    result = conn.execute(
        f"""
        SELECT COUNT(DISTINCT e.plate_number) AS occupancy
        FROM access_log e
        WHERE e.gate_id IN ({placeholders})
          AND e.direction = 'ENTRY'
          AND e.timestamp <= ?
          AND NOT EXISTS (
              SELECT 1 FROM access_log x
              WHERE x.plate_number = e.plate_number
                AND x.gate_id IN ({placeholders})
                AND x.direction = 'EXIT'
                AND x.timestamp > e.timestamp
                AND x.timestamp <= ?
          )
        """,
        (*gate_ids, ceiling, *gate_ids, ceiling),
    ).fetchone()
    return int(result["occupancy"]) if result else 0


def get_subcontractor_hours(
    conn: sqlite3.Connection,
    company_id: str,
    date_from: str,
    date_to: str,
) -> list[dict]:
    """Aggregate dwell hours per project for a given subcontractor company.

    Used by the billing verification workflow: CDL finance compares this
    report against the sub-contractor's invoice to detect discrepancies.

    Returns
    -------
    list of dicts: project_code, project_name, plate_number, total_hours.
    """
    rows = conn.execute(
        """
        SELECT
            pva.project_code,
            p.project_name,
            pva.plate_number,
            ROUND(SUM(COALESCE(al.dwell_time_seconds, 0)) / 3600.0, 2) AS total_hours
        FROM project_vehicle_assignments pva
        JOIN projects p ON pva.project_code = p.project_code
        LEFT JOIN access_log al
            ON  al.plate_number = pva.plate_number
            AND al.direction    = 'ENTRY'
            AND DATE(al.timestamp) BETWEEN ? AND ?
        WHERE pva.company_id = ?
        GROUP BY pva.project_code, p.project_name, pva.plate_number
        ORDER BY pva.project_code, total_hours DESC
        """,
        (date_from, date_to, company_id),
    ).fetchall()
    return [dict(r) for r in rows]
