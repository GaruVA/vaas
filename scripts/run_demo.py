"""End-to-end demo: cycles sample images / live feed through pipeline."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.attendance import AttendanceEngine
from src.barrier import BarrierController
from src.camera import MockCamera, USBCamera
from src.classifier import CharClassifier
from src.config import (
    CAMERA_INDEX_GATE_A, CAMERA_INDEX_GATE_B, DB_PATH, HARDWARE_MODE,
)
from src.database import connect, init_schema
from src.detection import PlateDetector
from src.pipeline import run_pipeline


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gate", default="GATE_A", choices=["GATE_A", "GATE_B"])
    p.add_argument("--direction", default="ENTRY", choices=["ENTRY", "EXIT"])
    p.add_argument("--duration", type=int, default=30,
                   help="Max frames to process (rough seconds in mock mode)")
    p.add_argument("--mode", default=HARDWARE_MODE, choices=["LIVE", "MOCK"])
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    conn = connect(DB_PATH)
    init_schema(conn)

    barrier = BarrierController(mode=args.mode)
    engine = AttendanceEngine(conn, barrier=barrier)

    detector = PlateDetector()
    classifier = CharClassifier()

    if args.mode == "LIVE":
        idx = CAMERA_INDEX_GATE_A if args.gate == "GATE_A" else CAMERA_INDEX_GATE_B
        cam = USBCamera(index=idx)
    else:
        cam = MockCamera()

    n = run_pipeline(cam, detector, classifier, engine, args.gate, args.direction,
                     max_frames=args.duration)
    print(f"Processed {n} frames at {args.gate} ({args.direction})")
    cam.release()
    engine.shutdown()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
