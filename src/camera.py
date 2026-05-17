from __future__ import annotations

import logging
import platform
import time
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

logger = logging.getLogger(__name__)

class MockCamera:

    _IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

    def __init__(self, folder: str | Path, sleep_ms: int = 200) -> None:
        self._folder = Path(folder)
        self._sleep_s = sleep_ms / 1000.0
        self._files: list[Path] = sorted(
            p for p in self._folder.iterdir() if p.suffix.lower() in self._IMAGE_EXTS
        ) if self._folder.is_dir() else []
        self._iter: Iterator[Path] | None = self._cycle() if self._files else None
        logger.info("MockCamera initialised: %d files in %s", len(self._files), self._folder)

    def _cycle(self) -> Iterator[Path]:
        while True:
            yield from self._files

    def read(self) -> np.ndarray | None:
        time.sleep(self._sleep_s)
        if self._iter is None:
            return None
        path = next(self._iter)
        frame = cv2.imread(str(path))
        if frame is None:
            logger.warning("MockCamera: could not decode %s", path)
        return frame

    def release(self) -> None:
        logger.debug("MockCamera.release() called")

class USBCamera:

    def __init__(
        self,
        index: int | str = 0,
        width: int = 1920,
        height: int = 1080,
    ) -> None:

        if isinstance(index, int) and platform.system() == "Windows":
            backend = cv2.CAP_DSHOW
        else:
            backend = cv2.CAP_ANY
        self._cap = cv2.VideoCapture(index, backend)
        if width and height:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open capture device {index}")
        logger.info("USBCamera opened: index=%s res=%dx%d", index, width, height)

    def read(self) -> np.ndarray | None:
        ret, frame = self._cap.read()
        if not ret:
            logger.warning("USBCamera.read() returned no frame")
            return None
        return frame

    def release(self) -> None:
        self._cap.release()
        logger.info("USBCamera released")
