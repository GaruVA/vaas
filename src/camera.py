"""Camera abstraction (USB Logitech C920 / mock folder cycle)."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from src.config import SAMPLE_IMAGE_DIR

logger = logging.getLogger(__name__)


class USBCamera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720):
        self.index = index
        self._cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera index {index}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self._cap.read()
        if not ok:
            return None
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()


class MockCamera:
    def __init__(self, folder: Path | str | None = None, fps: float = 5.0):
        self.folder = Path(folder) if folder else SAMPLE_IMAGE_DIR
        self.delay = 1.0 / max(fps, 0.1)
        self._files = sorted([
            p for p in self.folder.glob("*")
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp")
        ])
        self._idx = 0

    def read(self) -> Optional[np.ndarray]:
        if not self._files:
            return None
        time.sleep(self.delay)
        path = self._files[self._idx % len(self._files)]
        self._idx += 1
        img = cv2.imread(str(path))
        return img

    def release(self) -> None:
        self._files = []


def make_camera(mode: str, index: int = 0) -> "USBCamera | MockCamera":
    if mode == "LIVE":
        return USBCamera(index=index)
    return MockCamera()
