from __future__ import annotations

"""Camera abstractions for the VAAS ALPR pipeline.

MockCamera   -- cycles through JPEG files in a folder (200 ms sleep between reads).
USBCamera    -- wraps cv2.VideoCapture for a real USB/IP camera.

Both expose:
    read()    -> np.ndarray | None
    release() -> None

References: §6.10 of BUILD_SPEC.md.
"""

import logging
import time
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class MockCamera:
    """Cycles through JPEG images in *folder* indefinitely.

    Sleeps 200 ms between frames to simulate ~5 fps capture.  If *folder*
    contains no image files, ``read()`` returns ``None`` on every call.

    Parameters
    ----------
    folder:
        Directory containing ``*.jpg`` / ``*.jpeg`` / ``*.png`` files.
    sleep_ms:
        Inter-frame sleep in milliseconds (default 200).
    """

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
        """Return next frame as BGR ndarray, or None if no images available."""
        time.sleep(self._sleep_s)
        if self._iter is None:
            return None
        path = next(self._iter)
        frame = cv2.imread(str(path))
        if frame is None:
            logger.warning("MockCamera: could not decode %s", path)
        return frame

    def release(self) -> None:
        """No-op for mock camera (no hardware to release)."""
        logger.debug("MockCamera.release() called")


class USBCamera:
    """Wraps ``cv2.VideoCapture`` for a USB or RTSP camera.

    Parameters
    ----------
    index:
        Camera index (int) or RTSP URL (str) passed directly to
        ``cv2.VideoCapture``.
    width, height:
        Optional resolution hints.  Set to 0 to use camera default.
    """

    def __init__(
        self,
        index: int | str = 0,
        width: int = 1920,
        height: int = 1080,
    ) -> None:
        self._cap = cv2.VideoCapture(index)
        if width and height:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self._cap.isOpened():
            logger.error("USBCamera: could not open capture device %s", index)
        else:
            logger.info("USBCamera opened: index=%s res=%dx%d", index, width, height)

    def read(self) -> np.ndarray | None:
        """Return current frame as BGR ndarray, or None on failure."""
        ret, frame = self._cap.read()
        if not ret:
            logger.warning("USBCamera.read() returned no frame")
            return None
        return frame

    def release(self) -> None:
        """Release the underlying VideoCapture handle."""
        self._cap.release()
        logger.info("USBCamera released")
