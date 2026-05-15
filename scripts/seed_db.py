from __future__ import annotations

"""Seed the VAAS database with 60 days of realistic demo data.

Wipes all existing data and rebuilds from scratch so the SHA-256
hash chain is clean from genesis.

Produces
--------
- 11 users (3 system + 8 named drivers)
- 3 shifts, 5 zones, 3 subcontractor companies, 2 active projects
- 18 registered vehicles (STAFF / CONTRACTOR / MANAGEMENT / FLEET /
  SUSPENDED / EXPIRED mix)
- 8 driver → vehicle assignments
- ~420 access_log rows with intact hash chain (60 working days)
- ~25 gate_rejections (SUSPENDED / EXPIRED / UNREGISTERED plates)
- ~18 admin_audit_log entries
- 4 today-only ENTRY events so zone occupancy shows live vehicles

Usage
-----
    python scripts/seed_db.py [--db-path path/to/vaas.db]

References: section 5 (Seeding) of BUILD_SPEC.md
"""

import argparse
import json
import logging
import os
import random
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bcrypt

from src.audit import log_gate_event
from src.config import BCRYPT_COST, DB_PATH
from src.database import connect, migrate_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

RNG = random.Random(42)
TODAY = date(2026, 5, 14)
START = date(2026, 3, 10)

def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_COST)).decode()

def _ts(d: date, hour: int, minute: int, second: int = 0) -> str:
    return datetime(d.year, d.month, d.day, hour, minute, second,
                    tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _working_days(start: date, end: date):
    """Yield every Mon–Fri between start and end (inclusive)."""
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            yield cur
        cur += timedelta(days=1)

USERS = [

    ("admin",           "admin123",    "ADMIN",    "K. Perera (IT Admin)"),
    ("manager",         "manager123",  "MANAGER",  "S. Fernando (Security Manager)"),
    ("operator",        "operator123", "OPERATOR", "A. Jayawardena (Gate Operator)"),
    ("nsilva",          "driver123",   "OPERATOR", "Nimal Silva"),
    ("rkumar",          "driver123",   "OPERATOR", "Ranjit Kumar"),
    ("tjayawardena",    "driver123",   "OPERATOR", "Thilini Jayawardena"),
    ("abandara",        "driver123",   "OPERATOR", "Arjun Bandara"),
    ("srathnayake",     "driver123",   "OPERATOR", "Saman Rathnayake"),
    ("dwicks",          "driver123",   "OPERATOR", "Dasun Wickramasinghe"),
    ("ndissanayake",    "driver123",   "OPERATOR", "Nalaka Dissanayake"),
    ("pfernando",       "driver123",   "OPERATOR", "Priya Fernando"),
]

SHIFTS = [

    (1, "Day Shift",     "07:00", "15:00", 15),
    (2, "Evening Shift", "15:00", "23:00", 15),
    (3, "Night Shift",   "23:00", "07:00", 15),
]

ZONES = [

    ("DRYDOCK_1",    "Dry Dock 1",           "DRYDOCK",  30),
    ("DRYDOCK_2",    "Dry Dock 2",           "DRYDOCK",  30),
    ("BERTH_NORTH",  "Berth North",          "BERTH",    20),
    ("WORKSHOP_ENG", "Engineering Workshop", "WORKSHOP", 40),
    ("ADMIN_BLOCK",  "Administration Block", "ADMIN",    60),
]

COMPANIES = [

    ("SCO-001", "Ceylon Marine Services",  "Nimal Perera", "+94-11-2345678"),
    ("SCO-002", "Lanka Welding (Pvt) Ltd", "Ravi Kumar",   "+94-11-3456789"),
    ("SCO-003", "Onomichi Tech Support",   "Kenji Tanaka", "+81-848-12345"),
]

PROJECTS = [

    ("PRJ-2026-001", "MV Sayuri",      "DRYDOCK_1", "2026-01-01", None, "ACTIVE", "Suresh Fernando"),
    ("PRJ-2026-002", "MV Lanka Pride", "DRYDOCK_2", "2026-02-01", None, "ACTIVE", "Anil Jayawardena"),
]

VEHICLES = [
    ("WP-CAB-1234", "STAFF",       "CAR",      "ACTIVE",    "Nimal Silva",             None,    None),
    ("WP-KA-5678",  "STAFF",       "CAR",      "ACTIVE",    "Ranjit Kumar",            None,    None),
    ("WP-GA-7890",  "STAFF",       "MOTORCYCLE","ACTIVE",   "Thilini Jayawardena",     None,    None),
    ("WP-AB-3344",  "STAFF",       "CAR",      "ACTIVE",    "Arjun Bandara",           None,    None),
    ("KL-9012",     "CONTRACTOR",  "TRUCK",    "ACTIVE",    "Lanka Welding Works",     None,    "SCO-002"),
    ("KL-5566",     "CONTRACTOR",  "VAN",      "ACTIVE",    "Onomichi Tech Support",   None,    "SCO-003"),
    ("WP-EF-2233",  "STAFF",       "CAR",      "ACTIVE",    "Nalaka Dissanayake",      None,    None),
    ("WP-MN-4455",  "STAFF",       "CAR",      "ACTIVE",    "Priya Fernando",          None,    None),
    ("CAB-3456",    "MANAGEMENT",  "CAR",      "ACTIVE",    None,                      "MGMT",  None),
    ("WP-CD-7788",  "MAINTENANCE", "TRUCK",    "ACTIVE",    None,                      "MAINT", None),
    ("CP-1122",     "FLEET",       "UTILITY",  "ACTIVE",    "Ceylon Marine Services",  "OPS",   "SCO-001"),
    ("KL-3300",     "CONTRACTOR",  "VAN",      "ACTIVE",    "Ceylon Marine Services",  None,    "SCO-001"),
    ("KL-7712",     "CONTRACTOR",  "TRUCK",    "ACTIVE",    "Lanka Welding Works",     None,    "SCO-002"),
    ("WP-QR-8899",  "STAFF",       "CAR",      "ACTIVE",    "Roshan Mendis",           None,    None),
    ("SG-1111",     "EMERGENCY",   "UTILITY",  "ACTIVE",    "Fire & Rescue Dept",      None,    None),
    ("NW-9900",     "VISITOR",     "CAR",      "ACTIVE",    "Visitor Corp",            None,    None),
    ("WP-ST-0011",  "STAFF",       "CAR",      "SUSPENDED", "Former Employee",         None,    None),
    ("WP-ZZ-9988",  "STAFF",       "CAR",      "EXPIRED",   "Ex-Contractor",           None,    None),
]

DRIVER_ASSIGNMENTS = [
    ("nsilva",       "WP-CAB-1234"),
    ("rkumar",       "WP-KA-5678"),
    ("tjayawardena", "WP-GA-7890"),
    ("abandara",     "WP-AB-3344"),
    ("srathnayake",  "KL-9012"),
    ("dwicks",       "KL-5566"),
    ("ndissanayake", "WP-EF-2233"),
    ("pfernando",    "WP-MN-4455"),
]

PROJECT_VEHICLES = [
    ("PRJ-2026-001", "WP-CAB-1234", "EMPLOYEE",      None),
    ("PRJ-2026-001", "WP-AB-3344",  "SUPERVISOR",    None),
    ("PRJ-2026-001", "KL-9012",     "SUBCONTRACTOR", "SCO-002"),
    ("PRJ-2026-001", "KL-7712",     "SUBCONTRACTOR", "SCO-002"),
    ("PRJ-2026-001", "CP-1122",     "SUBCONTRACTOR", "SCO-001"),
    ("PRJ-2026-002", "WP-KA-5678",  "EMPLOYEE",      None),
    ("PRJ-2026-002", "WP-MN-4455",  "SUPERVISOR",    None),
    ("PRJ-2026-002", "KL-5566",     "SUBCONTRACTOR", "SCO-003"),
    ("PRJ-2026-002", "KL-3300",     "SUBCONTRACTOR", "SCO-001"),
]

PROFILES = {

    "WP-CAB-1234": dict(attendance=0.95, ontime=0.95, early=0.10, overstay=0.02,
                        project="PRJ-2026-001", zone="DRYDOCK_1",  gate="MAIN_GATE",    shift=1),
    "WP-KA-5678":  dict(attendance=0.92, ontime=0.93, early=0.08, overstay=0.02,
                        project="PRJ-2026-002", zone="DRYDOCK_2",  gate="MAIN_GATE",    shift=1),
    "WP-MN-4455":  dict(attendance=0.90, ontime=0.91, early=0.12, overstay=0.01,
                        project="PRJ-2026-002", zone="DRYDOCK_2",  gate="MAIN_GATE",    shift=1),

    "WP-GA-7890":  dict(attendance=0.85, ontime=0.76, early=0.05, overstay=0.06,
                        project=None,           zone="WORKSHOP_ENG",gate="WORKSHOP_GATE",shift=1),
    "WP-AB-3344":  dict(attendance=0.82, ontime=0.72, early=0.04, overstay=0.08,
                        project="PRJ-2026-001", zone="DRYDOCK_1",  gate="MAIN_GATE",    shift=1),
    "WP-EF-2233":  dict(attendance=0.88, ontime=0.80, early=0.06, overstay=0.05,
                        project=None,           zone="ADMIN_BLOCK", gate="MAIN_GATE",    shift=1),
    "WP-QR-8899":  dict(attendance=0.78, ontime=0.74, early=0.05, overstay=0.07,
                        project=None,           zone="WORKSHOP_ENG",gate="WORKSHOP_GATE",shift=1),

    "KL-9012":     dict(attendance=0.72, ontime=0.50, early=0.03, overstay=0.22,
                        project="PRJ-2026-001", zone="DRYDOCK_1",  gate="MAIN_GATE",    shift=1),
    "KL-5566":     dict(attendance=0.65, ontime=0.44, early=0.02, overstay=0.18,
                        project="PRJ-2026-002", zone="DRYDOCK_2",  gate="MAIN_GATE",    shift=1),

    "KL-7712":     dict(attendance=0.55, ontime=0.60, early=0.02, overstay=0.25,
                        project="PRJ-2026-001", zone="DRYDOCK_1",  gate="MAIN_GATE",    shift=1),
    "KL-3300":     dict(attendance=0.50, ontime=0.65, early=0.03, overstay=0.15,
                        project="PRJ-2026-002", zone="DRYDOCK_2",  gate="MAIN_GATE",    shift=1),

    "CAB-3456":    dict(attendance=0.40, ontime=0.62, early=0.05, overstay=0.05,
                        project=None,           zone="ADMIN_BLOCK", gate="MAIN_GATE",    shift=1),
    "CP-1122":     dict(attendance=0.60, ontime=0.70, early=0.05, overstay=0.08,
                        project="PRJ-2026-001", zone="DRYDOCK_1",  gate="MAIN_GATE",    shift=1),
}

def _entry_time(profile: dict) -> tuple[int, int]:
    """Return (hour, minute) for an ENTRY event given compliance profile."""
    r = RNG.random()
    ontime = profile["ontime"]
    early  = profile["early"]
    if r < ontime * early:

        return 6, RNG.randint(15, 44)
    elif r < ontime:

        return 7 if RNG.random() < 0.7 else 6, RNG.randint(0, 15) if RNG.random() < 0.7 else RNG.randint(45, 59)
    else:

        late_mins = RNG.randint(30, 180)
        h = 7 + late_mins // 60
        m = late_mins % 60
        return h, m

def _exit_time(entry_h: int, entry_m: int, profile: dict) -> tuple[int, int]:
    """Return (hour, minute) for EXIT given entry time and profile."""
    if RNG.random() < profile["overstay"]:

        return RNG.randint(17, 19), RNG.randint(0, 30)

    dwell_mins = RNG.randint(450, 540)
    total = entry_h * 60 + entry_m + dwell_mins
    return total // 60, total % 60

def _entry_status(hour: int, minute: int) -> str:
    total = hour * 60 + minute

    if total < 6 * 60 + 45:
        return "EARLY_ARRIVAL"
    if total <= 7 * 60 + 15:
        return "ON_TIME_ENTRY"
    return "LATE_ARRIVAL"

def _exit_status(entry_h: int, entry_m: int, exit_h: int, exit_m: int) -> str:
    dwell = (exit_h * 60 + exit_m) - (entry_h * 60 + entry_m)
    if dwell > 600:
        return "OVERSTAY"
    if exit_h * 60 + exit_m < 14 * 60 + 30:
        return "EARLY_DEPARTURE"
    if exit_h * 60 + exit_m <= 15 * 60 + 15:
        return "ON_TIME_EXIT"
    return "OVERSTAY"

def _populate(conn) -> None:

    conn.execute("PRAGMA foreign_keys = OFF")

    gates_json = json.dumps(["MAIN_GATE", "WORKSHOP_GATE"])
    weekdays   = json.dumps(["MON", "TUE", "WED", "THU", "FRI"])

    wipe_order = [
        "access_log", "gate_rejections", "admin_audit_log",
        "vehicle_assignments", "vehicle_shifts",
        "project_vehicle_assignments", "projects",
        "registered_vehicles", "subcontractor_companies",
        "cdl_zones", "shifts", "users",
    ]
    for tbl in wipe_order:
        conn.execute(f"DELETE FROM {tbl}")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ({})".format(
        ",".join("?" * len(wipe_order))
    ), wipe_order)
    conn.commit()
    logger.info("All tables wiped")

    user_ids: dict[str, int] = {}
    for username, pw, role, full_name in USERS:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
            (username, _hash_pw(pw), role, full_name),
        )
        user_ids[username] = cur.lastrowid
        logger.info("User  %s / %s  [%s]", username, pw, role)
    conn.commit()

    for sid, sname, start, end, grace in SHIFTS:
        conn.execute(
            """INSERT INTO shifts
               (shift_id, shift_name, start_time, end_time,
                days_of_week, permitted_gates, grace_period_minutes)
               VALUES (?,?,?,?,?,?,?)""",
            (sid, sname, start, end, weekdays, gates_json, grace),
        )
    conn.commit()
    logger.info("Shifts seeded (%d)", len(SHIFTS))

    for zid, zname, ztype, cap in ZONES:
        conn.execute(
            """INSERT INTO cdl_zones
               (zone_id, zone_name, zone_type, associated_gates, vehicle_capacity)
               VALUES (?,?,?,?,?)""",
            (zid, zname, ztype, gates_json, cap),
        )
    conn.commit()
    logger.info("Zones seeded (%d)", len(ZONES))

    for cid, cname, contact, phone in COMPANIES:
        conn.execute(
            """INSERT INTO subcontractor_companies
               (company_id, company_name, contact_name, contact_phone)
               VALUES (?,?,?,?)""",
            (cid, cname, contact, phone),
        )
    conn.commit()
    logger.info("Companies seeded (%d)", len(COMPANIES))

    for pcode, vessel, zone, start, end, status, pm in PROJECTS:
        conn.execute(
            """INSERT INTO projects
               (project_code, vessel_name, zone_id, start_date, end_date, status, project_manager)
               VALUES (?,?,?,?,?,?,?)""",
            (pcode, vessel, zone, start, end, status, pm),
        )
    conn.commit()
    logger.info("Projects seeded (%d)", len(PROJECTS))

    for plate, cat, vtype, reg_status, contractor, dept, company in VEHICLES:
        conn.execute(
            """INSERT INTO registered_vehicles
               (plate_number, vehicle_category, vehicle_type, registration_status,
                contractor_name, department, company_id)
               VALUES (?,?,?,?,?,?,?)""",
            (plate, cat, vtype, reg_status, contractor, dept, company),
        )
    conn.commit()
    logger.info("Vehicles seeded (%d)", len(VEHICLES))

    for plate in PROFILES:
        conn.execute(
            "INSERT OR IGNORE INTO vehicle_shifts (plate_number, shift_id) VALUES (?,?)",
            (plate, PROFILES[plate]["shift"]),
        )
    conn.commit()

    for pcode, plate, role, company in PROJECT_VEHICLES:
        conn.execute(
            """INSERT INTO project_vehicle_assignments
               (project_code, plate_number, role, company_id)
               VALUES (?,?,?,?)""",
            (pcode, plate, role, company),
        )
    conn.commit()

    for username, plate in DRIVER_ASSIGNMENTS:
        conn.execute(
            "INSERT INTO vehicle_assignments (user_id, plate_number) VALUES (?,?)",
            (user_ids[username], plate),
        )
    conn.commit()
    logger.info("Driver assignments seeded (%d)", len(DRIVER_ASSIGNMENTS))

    events: list[dict] = []

    working_days = list(_working_days(START, TODAY - timedelta(days=1)))
    for day in working_days:
        for plate, p in PROFILES.items():
            if RNG.random() > p["attendance"]:
                continue

            entry_h, entry_m = _entry_time(p)
            entry_sec = RNG.randint(0, 59)
            entry_status = _entry_status(entry_h, entry_m)

            exit_h, exit_m = _exit_time(entry_h, entry_m, p)
            exit_sec = RNG.randint(0, 59)
            dwell = max(60.0, (exit_h * 3600 + exit_m * 60 + exit_sec) -
                               (entry_h * 3600 + entry_m * 60 + entry_sec))
            exit_status = _exit_status(entry_h, entry_m, exit_h, exit_m)

            conf_entry = round(RNG.uniform(0.82, 0.97), 3)
            conf_exit  = round(RNG.uniform(0.82, 0.97), 3)

            events.append(dict(
                plate=plate, direction="ENTRY",
                ts=_ts(day, entry_h, entry_m, entry_sec),
                status=entry_status, shift_id=p["shift"],
                confidence=conf_entry, dwell=None,
                zone=p["zone"], project=p["project"], gate=p["gate"],
            ))
            events.append(dict(
                plate=plate, direction="EXIT",
                ts=_ts(day, exit_h, exit_m, exit_sec),
                status=exit_status, shift_id=p["shift"],
                confidence=conf_exit, dwell=dwell,
                zone=p["zone"], project=p["project"], gate=p["gate"],
            ))

        if RNG.random() < 0.25:
            fake_plate = f"UN-{RNG.randint(1000,9999)}"
            events.append(dict(
                plate=fake_plate, direction="ENTRY",
                ts=_ts(day, RNG.randint(7, 14), RNG.randint(0, 59), RNG.randint(0, 59)),
                status="VISITOR", shift_id=None,
                confidence=round(RNG.uniform(0.55, 0.75), 3),
                dwell=None, zone=None, project=None, gate="MAIN_GATE",
            ))

    events.sort(key=lambda e: e["ts"])

    logger.info("Inserting %d access_log events…", len(events))
    for ev in events:
        log_gate_event(
            conn,
            ev["plate"],
            ev["ts"],
            ev["gate"],
            ev["direction"],
            status=ev["status"],
            shift_id=ev["shift_id"],
            confidence_score=ev["confidence"],
            dwell_time_seconds=ev["dwell"],
            zone_id=ev["zone"],
            project_code=ev["project"],
        )
    conn.commit()
    logger.info("Access log seeded (%d rows)", len(events))

    live_today = [
        ("WP-CAB-1234", "MAIN_GATE",     "DRYDOCK_1",   "PRJ-2026-001"),
        ("KL-9012",     "MAIN_GATE",     "DRYDOCK_1",   "PRJ-2026-001"),
        ("WP-KA-5678",  "MAIN_GATE",     "DRYDOCK_2",   "PRJ-2026-002"),
        ("KL-5566",     "MAIN_GATE",     "DRYDOCK_2",   "PRJ-2026-002"),
        ("WP-EF-2233",  "MAIN_GATE",     "ADMIN_BLOCK",  None),
        ("CAB-3456",    "MAIN_GATE",     "ADMIN_BLOCK",  None),
    ]
    for plate, gate, zone, project in live_today:
        h = RNG.randint(7, 9)
        m = RNG.randint(0, 30)
        p = PROFILES.get(plate, {})
        log_gate_event(
            conn, plate,
            _ts(TODAY, h, m, RNG.randint(0, 59)),
            gate, "ENTRY",
            status=_entry_status(h, m),
            shift_id=1,
            confidence_score=round(RNG.uniform(0.85, 0.97), 3),
            zone_id=zone, project_code=project,
        )
    conn.commit()
    logger.info("Today live entries seeded (%d)", len(live_today))

    rejection_days = RNG.sample(working_days[-40:], 22)
    rejection_plates = (
        [("WP-ST-0011", "SUSPENDED")] * 7 +
        [("WP-ZZ-9988", "EXPIRED")]   * 6 +
        [(f"XX-{RNG.randint(1000,9999)}", "UNREGISTERED") for _ in range(9)]
    )
    RNG.shuffle(rejection_plates)

    for i, (plate, reason) in enumerate(rejection_plates[:len(rejection_days)]):
        day = rejection_days[i % len(rejection_days)]
        conn.execute(
            """INSERT INTO gate_rejections
               (plate_number, timestamp, gate_id, reason, confidence_score)
               VALUES (?,?,?,?,?)""",
            (
                plate,
                _ts(day, RNG.randint(7, 16), RNG.randint(0, 59), RNG.randint(0, 59)),
                RNG.choice(["MAIN_GATE", "WORKSHOP_GATE"]),
                reason,
                round(RNG.uniform(0.72, 0.95), 3),
            ),
        )
    conn.commit()
    logger.info("Gate rejections seeded (%d)", len(rejection_plates))

    audit_entries = [
        ("admin",   "CREATE",   "user",    "4",  {"username": "nsilva",       "role": "OPERATOR"}),
        ("admin",   "CREATE",   "user",    "5",  {"username": "rkumar",       "role": "OPERATOR"}),
        ("admin",   "CREATE",   "user",    "6",  {"username": "tjayawardena", "role": "OPERATOR"}),
        ("admin",   "CREATE",   "user",    "7",  {"username": "abandara",     "role": "OPERATOR"}),
        ("admin",   "CREATE",   "user",    "8",  {"username": "srathnayake",  "role": "OPERATOR"}),
        ("admin",   "CREATE",   "user",    "9",  {"username": "dwicks",       "role": "OPERATOR"}),
        ("manager", "UPDATE",   "vehicle", "WP-ST-0011", {"registration_status": "SUSPENDED", "reason": "Contract terminated"}),
        ("manager", "UPDATE",   "vehicle", "WP-ZZ-9988", {"registration_status": "EXPIRED",   "reason": "Registration lapsed"}),
        ("admin",   "CREATE",   "vehicle", "KL-7712",    {"category": "CONTRACTOR", "company_id": "SCO-002"}),
        ("admin",   "ASSIGN",   "vehicle", "KL-9012",    {"project": "PRJ-2026-001", "role": "SUBCONTRACTOR"}),
        ("admin",   "ASSIGN",   "vehicle", "KL-5566",    {"project": "PRJ-2026-002", "role": "SUBCONTRACTOR"}),
        ("manager", "CREATE",   "project", "PRJ-2026-002",{"vessel": "MV Lanka Pride", "zone": "DRYDOCK_2"}),
        ("admin",   "UPDATE",   "shift",   "DAY",        {"grace_period_minutes": 15}),
        ("manager", "UPDATE",   "vehicle", "CAB-3456",   {"department": "MGMT", "note": "Management pool vehicle"}),
        ("admin",   "CREATE",   "zone",    "DRYDOCK_2",  {"type": "DRYDOCK", "capacity": 30}),
        ("admin",   "ASSIGN",   "user",    "8",          {"plate": "KL-9012", "action": "vehicle_assignment"}),
        ("admin",   "ASSIGN",   "user",    "9",          {"plate": "KL-5566", "action": "vehicle_assignment"}),
        ("manager", "UPDATE",   "vehicle", "WP-QR-8899", {"registration_status": "ACTIVE", "note": "Renewed registration"}),
    ]
    audit_days = [START + timedelta(days=i * 3) for i in range(len(audit_entries))]
    for i, (username, action, entity_type, entity_id, delta) in enumerate(audit_entries):
        uid = user_ids.get(username, 1)
        day = audit_days[i % len(audit_days)]
        conn.execute(
            """INSERT INTO admin_audit_log
               (user_id, username, action, entity_type, entity_id, delta_json, timestamp)
               VALUES (?,?,?,?,?,?,?)""",
            (
                uid, username, action, entity_type, str(entity_id),
                json.dumps(delta),
                _ts(day, RNG.randint(8, 17), RNG.randint(0, 59)),
            ),
        )
    conn.commit()
    logger.info("Admin audit log seeded (%d entries)", len(audit_entries))

    conn.execute("PRAGMA foreign_keys = ON")

def seed(db_path: Path | None = None, in_place: bool = False) -> None:
    """Seed the database.

    If *in_place* is True (or the target file is locked by another process),
    write directly into the target rather than building a temp file and
    copying.  This is safe when the Flask app is running because _populate()
    issues DELETE FROM on every table first.
    """
    target = Path(db_path) if db_path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Target database: %s", target)

    if not in_place:
        tmp_fd, tmp_str = tempfile.mkstemp(suffix=".db", prefix="vaas_seed_")
        tmp_path = Path(tmp_str)
        os.close(tmp_fd)
        try:
            conn = connect(tmp_path)
            migrate_db(conn)
            _populate(conn)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            try:
                shutil.copy2(str(tmp_path), str(target))
                logger.info("Database written to %s  (%d bytes)", target, target.stat().st_size)
            except (PermissionError, OSError) as exc:
                logger.warning("Could not replace DB file (%s) — falling back to in-place seed", exc)
                tmp_path.unlink(missing_ok=True)
                in_place = True
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    if in_place:
        conn = connect(target)
        migrate_db(conn)
        _populate(conn)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        logger.info("In-place seed complete. Database: %s", target)

    logger.info("Seed complete.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the VAAS demo database")
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--in-place", action="store_true",
                        help="Write directly into the target DB (safe while app is running)")
    args = parser.parse_args()
    seed(args.db_path, in_place=args.in_place)

if __name__ == "__main__":
    main()
