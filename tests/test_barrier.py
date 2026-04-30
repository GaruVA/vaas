"""6 tests for BarrierController (§5.9)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.barrier import BarrierController


def test_mock_open_logs(caplog):
    bc = BarrierController(mode="MOCK")
    with caplog.at_level("INFO"):
        bc.open("GATE_A")
    assert any("OPEN" in r.message for r in caplog.records)


def test_mock_close_logs(caplog):
    bc = BarrierController(mode="MOCK")
    with caplog.at_level("INFO"):
        bc.close("GATE_B")
    assert any("CLOSE" in r.message for r in caplog.records)


def test_invalid_gate_raises():
    bc = BarrierController(mode="MOCK")
    with pytest.raises(ValueError):
        bc.open("GATE_Z")


def test_live_open_writes_bytes():
    fake = MagicMock()
    with patch("serial.Serial", return_value=fake):
        bc = BarrierController(mode="LIVE", port="COMX", baud=9600)
        bc.open("GATE_A")
    fake.write.assert_called_once_with(b"OPEN:GATE_A\n")


def test_live_close_writes_bytes():
    fake = MagicMock()
    with patch("serial.Serial", return_value=fake):
        bc = BarrierController(mode="LIVE", port="COMX")
        bc.close("GATE_B")
    fake.write.assert_called_once_with(b"CLOSE:GATE_B\n")


def test_live_port_unavailable_raises():
    with patch("serial.Serial", side_effect=OSError("no port")):
        with pytest.raises(Exception):
            BarrierController(mode="LIVE", port="COM_NOPE")
