from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

def create_zone(
    conn,
    zone_id: str,
    zone_name: str,
    zone_type: str,
    associated_gates: list[str],
    vehicle_capacity: int = 50,
) -> None:
    valid_types = ("DRYDOCK", "BERTH", "WORKSHOP", "ADMIN", "SECURITY")
    if zone_type not in valid_types:
        raise ValueError(f"zone_type must be one of {valid_types}, got {zone_type!r}")
    conn.execute(
        """INSERT INTO cdl_zones
           (zone_id, zone_name, zone_type, associated_gates, vehicle_capacity)
           VALUES (?,?,?,?,?)""",
        (zone_id, zone_name, zone_type, json.dumps(associated_gates), vehicle_capacity),
    )
    logger.info("Zone created: %s (%s)", zone_id, zone_type)

def get_zone(conn, zone_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM cdl_zones WHERE zone_id = ?", (zone_id,)
    ).fetchone()
    return dict(row) if row else None

def list_zones(conn, zone_type: str | None = None) -> list[dict]:
    if zone_type:
        rows = conn.execute(
            "SELECT * FROM cdl_zones WHERE zone_type = ? ORDER BY zone_id",
            (zone_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM cdl_zones ORDER BY zone_id"
        ).fetchall()
    return [dict(r) for r in rows]

def get_zone_occupancy(conn, zone_id: str) -> int:
    row = conn.execute(
        "SELECT associated_gates FROM cdl_zones WHERE zone_id = ?", (zone_id,)
    ).fetchone()
    if row is None:
        return 0
    gates: list[str] = json.loads(row[0])
    if not gates:
        return 0
    placeholders = ",".join("?" * len(gates))
    count = conn.execute(
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
    ).fetchone()[0]
    return count or 0

def create_company(
    conn,
    company_id: str,
    company_name: str,
    contact_name: str | None = None,
    contact_phone: str | None = None,
    contact_email: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO subcontractor_companies
           (company_id, company_name, contact_name, contact_phone, contact_email)
           VALUES (?,?,?,?,?)""",
        (company_id, company_name, contact_name, contact_phone, contact_email),
    )
    logger.info("Company created: %s", company_id)

def get_company(conn, company_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM subcontractor_companies WHERE company_id = ?", (company_id,)
    ).fetchone()
    return dict(row) if row else None

def list_companies(conn, approval_status: str | None = None) -> list[dict]:
    if approval_status:
        rows = conn.execute(
            "SELECT * FROM subcontractor_companies WHERE approval_status = ? ORDER BY company_id",
            (approval_status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM subcontractor_companies ORDER BY company_id"
        ).fetchall()
    return [dict(r) for r in rows]

def create_project(
    conn,
    project_code: str,
    vessel_name: str,
    zone_id: str,
    start_date: str,
    end_date: str | None = None,
    project_manager: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO projects
           (project_code, vessel_name, zone_id, start_date, end_date,
            status, project_manager)
           VALUES (?,?,?,?,?,'ACTIVE',?)""",
        (project_code, vessel_name, zone_id, start_date, end_date, project_manager),
    )
    logger.info("Project created: %s (vessel: %s)", project_code, vessel_name)

def get_project(conn, project_code: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM projects WHERE project_code = ?", (project_code,)
    ).fetchone()
    return dict(row) if row else None

def list_projects(conn, status: str | None = None) -> list[dict]:
    if status:
        rows = conn.execute(
            "SELECT * FROM projects WHERE status = ? ORDER BY project_code",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY project_code"
        ).fetchall()
    return [dict(r) for r in rows]

def close_project(conn, project_code: str, closure_date: str) -> None:
    conn.execute(
        "UPDATE projects SET status = 'CLOSED', end_date = ? WHERE project_code = ?",
        (closure_date, project_code),
    )
    conn.execute(
        """UPDATE project_vehicle_assignments
           SET removed_at = ?
           WHERE project_code = ? AND removed_at IS NULL""",
        (closure_date, project_code),
    )
    logger.info("Project %s closed at %s", project_code, closure_date)

def assign_vehicle_to_project(
    conn,
    project_code: str,
    plate_number: str,
    role: str,
    company_id: str | None = None,
    assigned_at: str | None = None,
) -> None:
    if role == "SUBCONTRACTOR":
        if not company_id:
            raise ValueError("company_id is required for SUBCONTRACTOR role")
        exists = conn.execute(
            "SELECT 1 FROM subcontractor_companies WHERE company_id = ?",
            (company_id,),
        ).fetchone()
        if not exists:
            raise ValueError(f"company_id {company_id!r} does not exist")

    conn.execute(
        """INSERT INTO project_vehicle_assignments
           (project_code, plate_number, role, company_id, assigned_at)
           VALUES (?,?,?,?,COALESCE(?,strftime('%Y-%m-%dT%H:%M:%SZ','now')))""",
        (project_code, plate_number, role, company_id, assigned_at),
    )
    logger.info("Vehicle %s assigned to project %s as %s", plate_number, project_code, role)

def unassign_vehicle_from_project(
    conn,
    project_code: str,
    plate_number: str,
    removed_at: str | None = None,
) -> None:
    ts = removed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """UPDATE project_vehicle_assignments
           SET removed_at = ?
           WHERE project_code = ? AND plate_number = ? AND removed_at IS NULL""",
        (ts, project_code, plate_number),
    )

def list_project_vehicles(
    conn,
    project_code: str,
    active_only: bool = True,
) -> list[dict]:
    if active_only:
        rows = conn.execute(
            """SELECT * FROM project_vehicle_assignments
               WHERE project_code = ? AND removed_at IS NULL
               ORDER BY assigned_at""",
            (project_code,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM project_vehicle_assignments
               WHERE project_code = ?
               ORDER BY assigned_at""",
            (project_code,),
        ).fetchall()
    return [dict(r) for r in rows]

def get_project_attendance_summary(
    conn,
    project_code: str,
    date_from: str,
    date_to: str,
) -> list[dict]:
    rows = conn.execute(
        """SELECT
               pva.plate_number,
               pva.role,
               pva.company_id,
               COUNT(al.id)                              AS total_events,
               COUNT(DISTINCT DATE(al.timestamp))         AS days_present,
               COALESCE(SUM(al.dwell_time_seconds)/3600, 0) AS total_dwell_hours
           FROM project_vehicle_assignments pva
           LEFT JOIN access_log al
               ON al.plate_number = pva.plate_number
               AND DATE(al.timestamp) BETWEEN ? AND ?
           WHERE pva.project_code = ?
             AND pva.removed_at IS NULL
           GROUP BY pva.plate_number
           ORDER BY pva.plate_number""",
        (date_from, date_to, project_code),
    ).fetchall()
    return [dict(r) for r in rows]

def get_subcontractor_hours(
    conn,
    company_id: str,
    date_from: str,
    date_to: str,
) -> list[dict]:
    rows = conn.execute(
        """SELECT
               pva.plate_number,
               pva.project_code,
               pva.company_id,
               COUNT(al.id)                              AS trips,
               COALESCE(SUM(al.dwell_time_seconds)/3600, 0) AS billed_hours
           FROM project_vehicle_assignments pva
           JOIN access_log al
               ON al.plate_number = pva.plate_number
               AND al.direction = 'EXIT'
               AND DATE(al.timestamp) BETWEEN ? AND ?
           WHERE pva.company_id = ?
             AND pva.role = 'SUBCONTRACTOR'
             AND pva.removed_at IS NULL
           GROUP BY pva.plate_number, pva.project_code
           ORDER BY pva.company_id, pva.plate_number""",
        (date_from, date_to, company_id),
    ).fetchall()
    return [dict(r) for r in rows]

def resolve_event_attribution(
    conn,
    plate_number: str,
    gate_id: str,
    timestamp: str,
) -> tuple[str | None, str | None]:
    rows = conn.execute(
        """SELECT cz.zone_id, p.project_code, cz.associated_gates
           FROM projects p
           JOIN cdl_zones cz ON cz.zone_id = p.zone_id
           JOIN project_vehicle_assignments pva
               ON pva.project_code = p.project_code
               AND pva.plate_number = ?
               AND pva.removed_at IS NULL
           WHERE p.status = 'ACTIVE'""",
        (plate_number,),
    ).fetchall()

    for row in rows:
        zone_id, project_code, gates_json = row[0], row[1], row[2]
        try:
            gates: list[str] = json.loads(gates_json)
        except (ValueError, TypeError):
            gates = []
        if gate_id in gates:
            return (zone_id, project_code)

    return (None, None)
