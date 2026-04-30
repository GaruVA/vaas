"""Generate 10 synthetic plate-like images for demo / tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from src.config import SAMPLE_IMAGE_DIR

PLATES = ["CAB-1234", "KL-5678", "WP-CAB-9012", "CAR-4521", "VAN-8801",
          "LB-2266",  "WP-3344",  "KY-5577",     "WP-CAR-7788", "BUS-1010"]


def render_plate_image(text: str, out_path: Path) -> None:
    img = np.full((480, 640, 3), 80, dtype=np.uint8)
    cv2.rectangle(img, (140, 200), (500, 290), (255, 255, 255), -1)
    cv2.rectangle(img, (140, 200), (500, 290), (0, 0, 0), 3)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 1.2, 3)
    x = 140 + (360 - tw) // 2
    y = 200 + (90 + th) // 2
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 0, 0), 3)
    cv2.imwrite(str(out_path), img)


def main() -> int:
    SAMPLE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for i, plate in enumerate(PLATES):
        render_plate_image(plate, SAMPLE_IMAGE_DIR / f"plate_{i:02d}.jpg")
    print(f"Wrote {len(PLATES)} sample plates to {SAMPLE_IMAGE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
