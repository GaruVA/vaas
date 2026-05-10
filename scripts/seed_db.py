from __future__ import annotations

"""Seed the VAAS database with demo data for development / demonstration.

Builds the database in a temp file (WAL mode supported on all filesystems),
then binary-copies the result to the target path.  This avoids disk I/O
errors on overlay / network mounts that cannot host WAL sidecar files.

Produces:
- 3 users: admin, manager, operator
- 3 shifts (DAY, EVENING, NIGHT)
- 5 CDL zones
- 3 subcontractor companies
- 2 active projects
- 12 registered vehicles
- Shift / project / user assignments for demo data

Usage:
    python scripts/seed_db.py [--db-path path/to/vaas.db]

References: section 5 (Seeding) of BUILD_SPEC.md
"""

import argparse
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bcrypt

from src.config import DB_PATH, BCRYPT_COST
from src.database import connect, migrate_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_COST)).decode()


def _populate(conn) -> None:
    """Insert all seed rows into an already-migrated connection."""
    gates_json = json.dumps(["MAIN_GATE", "WORKSHOP_GATE"])
    weekdays   = json.dumps(["MON", "TUE", "WED", "THU", "FRI"])

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    users = [
        ("admin",    "admin123",    "ADMIN",    "CDL Admin"),
        ("manager",  "manager123",  "MANAGER",  "CDL Manager"),
        ("operator", "operator123", "OPERATOR", "CDL Operator"),
    ]
    for username, pw, role, full_name in users:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            logger.info("User %s already exists -- skipping", username)
            continue
        conn.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
            (username, _hash_pw(pw), role, full_name),
        )
        logger.info("Created user: %s / %s  [%s]", username, pw, role)

    # ------------------------------------------------------------------
    # Shifts
    # ------------------------------------------------------------------
    shifts = [
        ("DAY",     "Day Shift",     "07:00", "15:00", 15),
        ("EVENING", "Evening Shift", "15:00", "23:00", 15),
        ("NIGHT",   "Night Shift",   "23:00", "07:00", 15),
    ]
    for sid, sname, start, end, grace in shifts:
        conn.execute(
            """INSERT OR IGNORE INTO shifts
               (shift_id, shift_name, start_time, end_time,
                days_of_week, permitted_gates, grace_period_minutes)
               VALUES (?,?,?,?,?,?,?)""",
            (sid, sname, start, end, weekdays, gates_json, grace),
        )
    logger.info("Shifts seeded (DAY / EVENING / NIGHT)")

    # ------------------------------------------------------------------
    # CDL zones
    # ------------------------------------------------------------------
    zones = [
        ("DRYDOCK_1",    "Dry Dock 1",             "DRYDOCK",  30),
        ("DRYDOCK_2",    "Dry Dock 2",             "DRYDOCK",  30),
        ("BERTH_NORTH",  "Berth North",            "BERTH",    20),
        ("WORKSHOP_ENG", "Engineering Workshop",   "WORKSHOP", 40),
        ("ADMIN_BLOCK",  "Administration Block",   "ADMIN",    60),
    ]
    for zid, zname, ztype, cap in zones:
        conn.execute(
            """INSERT OR IGNORE INTO cdl_zones
               (zone_id, zone_name, zone_type, associated_gates, vehicle_capacity)
               VALUES (?,?,?,?,?)""",
            (zid, zname, ztype, gates_json, cap),
        )
    logger.info("CDL zones seeded (%d)", len(zones))

    # ------------------------------------------------------------------
    # Subcontractor companies
    # ------------------------------------------------------------------
    companies = [
        ("SCO-001", "Ceylon Marine Services",   "Nimal Perera", "+94-11-2345678"),
        ("SCO-002", "Lanka Welding (Pvt) Ltd",  "Ravi Kumar",   "+94-11-3456789"),
        ("SCO-003", "Onomichi Tech Support",    "Kenji Tanaka", "+81-848-12345"),
    ]
    for cid, cname, contact, phone in companies:
        conn.execute(
            """INSERT OR IGNORE INTO subcontractor_companies
               (company_id, company_name, contact_name, contact_phone)
               VALUES (?,?,?,?)""",
            (cid, cname, contact, phone),
        )
    logger.info("Subcontractor companies seeded (%d)", len(companies))

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    projects = [
        ("PRJ-2026-001", "MV Sayuri",      "DRYDOCK_1", "2026-01-01", None, "ACTIVE", "Suresh Fernando"),
        ("PRJ-2026-002", "MV Lanka Pride", "DRYDOCK_2", "2026-02-01", None, "ACTIVE", "Anil Jayawardena"),
    ]
    for pcode, vessel, zone, start, end, status, pm in projects:
        conn.execute(
            """INSERT OR IGNORE INTO projects
               (project_code, vessel_name, zone_id, start_date, end_date, status, project_manager)
               VALUES (?,?,?,?,?,?,?)""",
            (pcode, vessel, zone, start, end, status, pm),
        )
    logger.info("Projects seeded (%d)", len(projects))

    # ------------------------------------------------------------------
    # Registered vehicles (12 total)
    # ------------------------------------------------------------------
    vehicles = [
        ("WP-CAB-1234", "STAFF",       "CAR",         "John Silva",          None,    None),
        ("WP-KA-5678",  "CONTRACTOR",  "VAN",         "ABC Builders Ltd",    None,    "SCO-001"),
        ("KL-9012",     "CONTRACTOR",  "TRUCK",       "Lanka Welding Works", None,    "SCO-002"),
        ("CAB-3456",    "MANAGEMENT",  "CAR",         None,                  "MGMT",  None),
        ("WP-GA-7890",  "STAFF",       "MOTORCYCLE",  "Jane Perera",         None,    None),
        ("CP-1122",     "FLEET",       "UTILITY",     None,                  "OPS",   None),
        ("WP-AB-3344",  "STAFF",       "CAR",         "Kamal Dias",          None,    None),
        ("KL-5566",     "CONTRACTOR",  "VAN",         "SubCo X Services",    None,    "SCO-003"),
        ("WP-CD-7788",  "MAINTENANCE", "TRUCK",       None,                  "MAINT", None),
        ("NW-9900",     "VISITOR",     "CAR",         "Visitor Corp",        None,    None),
        ("SG-1111",     "EMERGENCY",   "UTILITY",     "Fire Dept",           None,    None),
        ("WP-EF-2233",  "STAFF",       "CAR",         "Rita Raj",            None,    None),
    ]
    for plate, cat, vtype, contractor, dept, company in vehicles:
        conn.execute(
            """INSERT OR IGNORE INTO registered_vehicles
               (plate_number, vehicle_category, vehicle_type,
                contractor_name, department, company_id)
               VALUES (?,?,?,?,?,?)""",
            (plate, cat, vtype, contractor, dept, company),
        )
    logger.info("Registered vehicles seeded (%d)", len(vehicles))

    # Shift assignments
    for plate in [v[0] for v in vehicles[:8]]:
        conn.execute(
            "INSERT OR IGNORE INTO vehicle_shifts (plate_number, shift_id) VALUES (?,?)",
            (plate, "DAY"),
        )
    for plate in [v[0] for v in vehicles[2:5]]:
        conn.execute(
            "INSERT OR IGNORE INTO vehicle_shifts (plate_number, shift_id) VALUES (?,?)",
            (plate, "EVENING"),
        )
    for plate in [v[0] for v in vehicles[5:8]]:
        conn.execute(
            "INSERT OR IGNORE INTO vehicle_shifts (plate_number, shift_id) VALUES (?,?)",
            (plate, "NIGHT"),
        )
    logger.info("Shift assignments seeded")

    # Project-vehicle assignments
    pva_rows = [
        ("PRJ-2026-001", "WP-CAB-1234", "EMPLOYEE",      None),
        ("PRJ-2026-001", "WP-KA-5678",  "SUBCONTRACTOR", "SCO-001"),
        ("PRJ-2026-001", "KL-9012",     "SUBCONTRACTOR", "SCO-002"),
        ("PRJ-2026-001", "WP-AB-3344",  "SUPERVISOR",    None),
        ("PRJ-2026-002", "CAB-3456",    "EMPLOYEE",      None),
        ("PRJ-2026-002", "KL-5566",     "SUBCONTRACTOR", "SCO-003"),
        ("PRJ-2026-002", "WP-GA-7890",  "EMPLOYEE",      None),
    ]
    for pcode, plate, role, company in pva_rows:
        conn.execute(
            """INSERT OR IGNORE INTO project_vehicle_assignments
               (project_code, plate_number, role, company_id)
               VALUES (?,?,?,?)""",
            (pcode, plate, role, company),
        )
    logger.info("Project-vehicle assignments seeded")

    # Vehicle-to-user assignments (OHS demo)
    operator_id = conn.execute(
        "SELECT id FROM users WHERE username = 'operator'"
    ).fetchone()
    if operator_id:
        oid = operator_id[0]
        for plate in ["WP-CAB-1234", "WP-GA-7890"]:
            conn.execute(
                "INSERT OR IGNORE INTO vehicle_assignments (user_id, plate_number) VALUES (?,?)",
                (oid, plate),
            )
    logger.info("Vehicle-user assignments seeded")


def seed(db_path: Path | None = None) -> None:
    """Seed the database at *db_path* (defaults to config DB_PATH).

    Builds the database in a temporary file first to ensure WAL journal mode
    is always available, then binary-copies the result to *db_path*.
    """
    target = Path(db_path) if db_path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Target database: %s", target)

    # Build in /tmp where WAL is always supported
    tmp_fd, tmp_str = tempfile.mkstemp(suffix=".db", prefix="vaas_seed_")
    tmp_path = Path(tmp_str)
    import os; os.close(tmp_fd)

    try:
        conn = connect(tmp_path)
        migrate_db(conn)
        _populate(conn)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()

        shutil.copy2(str(tmp_path), str(target))
        logger.info("Database copied to %s  (%d bytes)", target, target.stat().st_size)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    logger.info("Seed complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the VAAS demo database")
    parser.add_argument("--db-path", type=Path, default=None,
                        help="Path to vaas.db (default: config DB_PATH)")
    args = parser.parse_args()
    seed(args.db_path)


if __name__ == "__main__":
    main()
