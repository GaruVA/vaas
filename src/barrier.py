from __future__ import annotations

"""Arduino Nano barrier (gate) controller.

Modes
-----
MOCK:
    No serial port opened.  All commands are logged only.  Used in
    development / CI where no hardware is present.

LIVE:
    Opens the Arduino serial port and sends ``b"OPEN\n"`` / ``b"CLOSE\n"``.
    Hardware: Arduino Nano on ``/dev/ttyUSB0`` (Linux) or ``COM4`` (Windows)
    at 9600 baud.

References: section 6.9 of BUILD_SPEC.md
"""

import logging
import threading
from typing import Literal

from src.config import HARDWARE_MODE, ARDUINO_PORT, ARDUINO_BAUD

logger = logging.getLogger(__name__)

class BarrierController:
    """Controls a physical gate barrier via Arduino Nano serial link.

    Parameters
    ----------
    mode:
        ``"MOCK"`` (default from config) or ``"LIVE"``.
    port:
        Serial port path.  Defaults to ``src.config.ARDUINO_PORT``.
    baud:
        Baud rate.  Defaults to ``src.config.ARDUINO_BAUD`` (9600).
    """

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
            import serial
            self._serial = serial.Serial(self._port, self._baud, timeout=1)
            logger.info("Barrier LIVE on %s @ %d baud", self._port, self._baud)
        else:
            logger.info("Barrier MOCK mode active")

    def open(self, gate_id: str) -> None:
        """Send OPEN command to the barrier for *gate_id*."""
        self._send(gate_id, "OPEN")

    def close(self, gate_id: str) -> None:
        """Send CLOSE command to the barrier for *gate_id*."""
        self._send(gate_id, "CLOSE")

    def _send(self, gate_id: str, command: str) -> None:
        with self._lock:
            if self._mode == "LIVE" and self._serial:
                self._serial.write(f"{command}\n".encode())
                self._serial.flush()
                logger.debug("Barrier[%s] LIVE -> %s", gate_id, command)
            else:
                self._log.append((gate_id, command))
                logger.info("Barrier[%s] MOCK -> %s", gate_id, command)

    def last_command(self, gate_id: str | None = None) -> tuple[str, str] | None:
        """Return the most recent (gate_id, command) pair, or None.

        Used by tests to inspect MOCK-mode behaviour without real hardware.
        If *gate_id* is given, returns the most recent entry for that gate.
        """
        if not self._log:
            return None
        if gate_id is None:
            return self._log[-1]
        for g, c in reversed(self._log):
            if g == gate_id:
                return (g, c)
        return None

    def command_log(self) -> list[tuple[str, str]]:
        """Return a copy of all (gate_id, command) pairs sent (MOCK only)."""
        return list(self._log)

    def close_port(self) -> None:
        """Close the serial port (LIVE mode only; no-op in MOCK)."""
        if self._serial:
            with self._lock:
                self._serial.close()
                self._serial = None
