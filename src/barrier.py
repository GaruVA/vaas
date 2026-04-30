"""Arduino Nano serial barrier controller (§5.9)."""
from __future__ import annotations

import logging
import threading
from typing import Literal, Optional

from src.config import ARDUINO_BAUD, ARDUINO_PORT, HARDWARE_MODE

logger = logging.getLogger(__name__)


class BarrierController:
    """Controls servo barriers via Arduino Nano over serial.

    Both gates share one USB serial multiplexer in the testbed; commands
    are tagged with gate_id so the firmware can route to the correct servo.
    """

    VALID_GATES = {"GATE_A", "GATE_B"}

    def __init__(self, mode: Literal["MOCK", "LIVE"] = HARDWARE_MODE,
                 port: str = ARDUINO_PORT, baud: int = ARDUINO_BAUD):
        self.mode = mode
        self.port = port
        self.baud = baud
        self._serial = None
        self._lock = threading.Lock()
        if self.mode == "LIVE":
            self._open_serial()

    def _open_serial(self) -> None:
        try:
            import serial
            self._serial = serial.Serial(self.port, self.baud, timeout=1)
            logger.info("Barrier serial opened on %s @ %d", self.port, self.baud)
        except Exception as exc:
            logger.error("Failed to open Arduino on %s: %s", self.port, exc)
            raise

    def _validate_gate(self, gate_id: str) -> None:
        if gate_id not in self.VALID_GATES:
            raise ValueError(f"Unknown gate_id: {gate_id}")

    def _send(self, command: str, gate_id: str) -> None:
        self._validate_gate(gate_id)
        payload = f"{command}:{gate_id}\n".encode("ascii")
        if self.mode == "MOCK":
            logger.info("[MOCK BARRIER] %s -> %s", command, gate_id)
            return
        with self._lock:
            if self._serial is None:
                raise RuntimeError("Serial not open")
            self._serial.write(payload)
            self._serial.flush()

    def open(self, gate_id: str) -> None:
        self._send("OPEN", gate_id)

    def close(self, gate_id: str) -> None:
        self._send("CLOSE", gate_id)

    def shutdown(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
