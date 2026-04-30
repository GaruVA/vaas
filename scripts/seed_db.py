"""Seed VAAS database with admin/manager/operator users, demo vehicles, shifts."""
from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bcrypt

from src.config import DB_PATH
from src.database import connect, init_schema, transaction


DEMO_VEHICLES = [
    ("CAB-1234", "CONTRACTOR", "Colombo Dockyard PLC", "DAY_SHIFT"),
    ("KL-5678",  "CONTRACTOR", "Lanka Logistics",      "DAY_SHIFT"),
    ("WP-CAB-9012", "EMPLOYEE", None,                  "DAY_SHIFT"),
    ("CAR-4521",  "CONTRACTOR", "Hayleys",             "DAY_SHIFT"),
    ("VAN-8801",  "DELIVERY",   "Keells",              "DAY_SHIFT"),
    ("LB-2266",   "CONTRACTOR", "John Keells Holdings","NIGHT_SHIFT"),
    ("WP-3344",   "EMPLOYEE",   None,                  "NIGHT_SHIFT"),
    ("KY-5577",   "CONTRACTOR", "MAS Holdings",        "NIGHT_SHIFT"),
    ("WP-CAR-7788","EMPLOYEE",  None,                  "DAY_SHIFT"),
    ("BUS-1010",  "EMPLOYEE",   None,                  "DAY_SHIFT"),
]


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def seed(db_path: Path | None = None,
         admin_password: str | None = None) -> dict:
    path = Path(db_path) if db_path else DB_PATH
    conn = connect(path)
    init_schema(conn)

    admin_pw = admin_password or secrets.token_urlsafe(12)
    manager_pw = secrets.token_urlsafe(12)
    operator_pw = secrets.token_urlsafe(12)

    with transaction(conn) as cur:
        cur.execute("DELETE FROM vehicle_shifts")
        cur.execute("DELETE FROM registered_vehicles")
        cur.execute("DELETE FROM shifts")
        cur.execute("DELETE FROM users")

        cur.execute(
            "INSERT INTO shifts VALUES (?,?,?,?,?,?,?)",
            ("DAY_SHIFT", "Day Shift", "08:00", "17:00",
             json.dumps(["MON", "TUE", "WED", "THU", "FRI"]),
             json.dumps(["GATE_A", "GATE_B"]), 10),
        )
        cur.execute(
            "INSERT INTO shifts VALUES (?,?,?,?,?,?,?)",
            ("NIGHT_SHIFT", "Night Shift", "20:00", "05:00",
             json.dumps(["MON", "TUE", "WED", "THU", "FRI", "SAT"]),
             json.dumps(["GATE_A", "GATE_B"]), 10),
        )

        for plate, cat, contractor, shift in DEMO_VEHICLES:
            cur.execute(
                "INSERT INTO registered_vehicles "
                "(plate_number,vehicle_category,contractor_name,registration_status) "
                "VALUES (?,?,?,'ACTIVE')",
                (plate, cat, contractor),
            )
            cur.execute(
                "INSERT INTO vehicle_shifts (plate_number,shift_id) VALUES (?,?)",
                (plate, shift),
            )

        cur.execute(
            "INSERT INTO users (username,password_hash,role) VALUES (?,?,?)",
            ("admin", hash_pw(admin_pw), "ADMIN"),
        )
        cur.execute(
            "INSERT INTO users (username,password_hash,role) VALUES (?,?,?)",
            ("manager", hash_pw(manager_pw), "MANAGER"),
        )
        cur.execute(
            "INSERT INTO users (username,password_hash,role) VALUES (?,?,?)",
            ("operator", hash_pw(operator_pw), "OPERATOR"),
        )

    conn.close()
    return {"admin": admin_pw, "manager": manager_pw, "operator": operator_pw}


if __name__ == "__main__":
    pw = input("Admin password (press Enter to autogen): ").strip() or None
    creds = seed(admin_password=pw)
    print("Seed complete. Credentials (save them now):")
    for u, p in creds.items():
        print(f"  {u:<10} : {p}")
