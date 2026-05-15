from __future__ import annotations

"""MOCK feed → pipeline end-to-end demo.

Runs the ALPR pipeline against synthetic JPEG frames using mock camera,
mock detector, and mock classifier.  Produces access_log rows with
non-PENDING row_hash values to demonstrate SHA-256 audit chain.

Usage::

    python scripts/run_demo.py [--db /path/to/vaas.db] [--gate GATE-A] \
                               [--direction ENTRY] [--frames N]

References: §9 (Phase 8 acceptance criterion) of BUILD_SPEC.md.
"""

import argparse
import logging
import shutil
import sqlite3
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.attendance import AttendanceEngine
from src.audit import verify_chain
from src.barrier import BarrierController
from src.database import migrate_db
from src.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_demo")

@dataclass
class _FakeDet:
    crop: np.ndarray
    confidence: float = 0.92

class _MockDetector:
    """Returns one detection per frame using the frame itself as the crop."""

    def detect(self, frame: np.ndarray) -> list[_FakeDet]:
        return [_FakeDet(crop=frame)]

class _MockClassifier:
    """Cycles through a list of plate strings."""

    def __init__(self, plates: list[str]) -> None:
        self._plates = plates
        self._idx = 0

    def classify(self, crop: np.ndarray) -> str:
        plate = self._plates[self._idx % len(self._plates)]
        self._idx += 1
        return plate

class _SyntheticCamera:
    """Produces *max_frames* synthetic BGR frames then stops."""

    def __init__(self, max_frames: int = 5) -> None:
        self._remaining = max_frames

    def read(self) -> np.ndarray | None:
        if self._remaining <= 0:
            return None
        self._remaining -= 1
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def release(self) -> None:
        pass

def _build_demo_db(target_path: Path) -> None:
    """Seed a minimal demo database in /tmp then copy to target."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = Path(tmpdir) / "vaas_demo.db"
        conn = sqlite3.connect(str(tmp_db))
        conn.isolation_level = None
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        migrate_db(conn)

        conn.execute("""
            INSERT OR IGNORE INTO shifts (shift_id, shift_name, start_time, end_time,
                days_of_week, permitted_gates, grace_period_minutes)
            VALUES ('SH-DAY','Day Shift','06:00','18:00','1,2,3,4,5','GATE-A,GATE-B',15)
        """)
        plates = ["WP-CAB-1234", "WP-KD-5678", "WP-DEMO-001",
                  "WP-DEMO-002", "WP-DEMO-003"]
        for plate in plates:
            conn.execute("""
                INSERT OR IGNORE INTO registered_vehicles
                    (plate_number, vehicle_category, registration_status)
                VALUES (?, 'STAFF', 'ACTIVE')
            """, (plate,))
            conn.execute("""
                INSERT OR IGNORE INTO vehicle_shifts (plate_number, shift_id)
                VALUES (?, 'SH-DAY')
            """, (plate,))
        conn.close()

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(tmp_db), str(target_path))
    logger.info("Demo DB created at %s", target_path)

def main() -> None:
    parser = argparse.ArgumentParser(description="VAAS MOCK pipeline demo")
    parser.add_argument("--db", default="data/vaas_demo.db",
                        help="SQLite DB path (created if absent)")
    parser.add_argument("--gate", default="GATE-A")
    parser.add_argument("--direction", default="ENTRY",
                        choices=["ENTRY", "EXIT"])
    parser.add_argument("--frames", type=int, default=5,
                        help="Number of synthetic frames to process")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        logger.info("No DB found at %s — seeding demo database", db_path)
        _build_demo_db(db_path)

    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(str(db_path), check_same_thread=False)
    conn.isolation_level = None
    conn.row_factory = _sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except _sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode = MEMORY")

    barrier = BarrierController(mode="MOCK")
    engine = AttendanceEngine(conn=conn, barrier=barrier)

    plates = ["WP-CAB-1234", "WP-KD-5678", "WP-DEMO-001",
              "WP-DEMO-002", "WP-DEMO-003"]
    camera = _SyntheticCamera(max_frames=args.frames)
    detector = _MockDetector()
    classifier = _MockClassifier(plates)
    stop_event = threading.Event()

    logger.info(
        "Starting pipeline: gate=%s direction=%s frames=%d",
        args.gate, args.direction, args.frames,
    )
    run_pipeline(
        camera=camera,
        detector=detector,
        classifier=classifier,
        attendance_engine=engine,
        gate_id=args.gate,
        direction=args.direction,
        stop_event=stop_event,
    )

    rows = conn.execute(
        "SELECT plate_number, timestamp, status, row_hash FROM access_log ORDER BY id"
    ).fetchall()
    print(f"\n{'='*60}")
    print(f"Demo complete — {len(rows)} access_log row(s) inserted")
    print(f"{'='*60}")
    for r in rows:
        pending = r["row_hash"] == "PENDING"
        hash_disp = r["row_hash"][:16] + "…" if not pending else "PENDING"
        status = "⚠ PENDING" if pending else "✓"
        print(f"  {status}  {r['plate_number']:<18} {r['timestamp'][:19]}  "
              f"{r['status']:<18} hash={hash_disp}")

    result = verify_chain(conn)
    integrity_label = "✓ INTACT" if result.ok else "✗ TAMPERED"
    print(f"\nChain integrity: {integrity_label}  "
          f"({result.rows_checked} rows checked)")
    if not result.ok:
        print(f"  First bad row id={result.first_bad_id}: {result.reason}")
    conn.close()

if __name__ == "__main__":
    main()
