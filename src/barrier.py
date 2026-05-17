from __future__ import annotations

import logging
import threading
from typing import Literal

from src.config import HARDWARE_MODE, ARDUINO_PORT, ARDUINO_BAUD

logger = logging.getLogger(__name__)

class BarrierController:

    def __init__(
        self,
        mode: str | None = None,
        port: str | None = None,
        baud: int = ARDUINO_BAUD,
    ) -> None:
        self._mode = (mode or HARDWARE_MODE).upper()
        self._port = port or ARDUINO_PORT
        self._baud = baud
        self._serial = None
        self._lock   = threading.Lock()
        self._log: list[tuple[str, str]] = []

        if self._mode == "LIVE":
            import serial, time
            self._serial = serial.Serial(self._port, self._baud, timeout=1)
            time.sleep(2)
            logger.info("Barrier LIVE on %s @ %d baud (ready)", self._port, self._baud)
        else:
            logger.info("Barrier MOCK mode active")

    def open(self, gate_id: str) -> None:
        self._send(gate_id, "OPEN")

    def close(self, gate_id: str) -> None:
        self._send(gate_id, "CLOSE")

    def _send(self, gate_id: str, command: str) -> None:
        with self._lock:
            if self._mode == "LIVE" and self._serial:
                self._serial.write(f"{command}:{gate_id}\n".encode())
                self._serial.flush()
                logger.info("Barrier[%s] LIVE -> %s:%s", gate_id, command, gate_id)
            else:
                self._log.append((gate_id, command))
                logger.info("Barrier[%s] MOCK -> %s", gate_id, command)

    def last_command(self, gate_id: str | None = None) -> tuple[str, str] | None:
        if not self._log:
            return None
        if gate_id is None:
            return self._log[-1]
        for g, c in reversed(self._log):
            if g == gate_id:
                return (g, c)
        return None

    def command_log(self) -> list[tuple[str, str]]:
        return list(self._log)

    def close_port(self) -> None:
        if self._serial:
            with self._lock:
                self._serial.close()
                self._serial = None
