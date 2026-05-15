from __future__ import annotations

"""6 tests for src/barrier.py -- MOCK-mode BarrierController."""

import pytest
from src.barrier import BarrierController

def test_01_mock_mode_no_crash():
    bc = BarrierController("MOCK")
    bc.open("MAIN_GATE")
    bc.close("MAIN_GATE")

def test_02_open_records_command():
    bc = BarrierController("MOCK")
    bc.open("MAIN_GATE")
    gate, cmd = bc.last_command()
    assert gate == "MAIN_GATE"
    assert cmd == "OPEN"

def test_03_close_records_command():
    bc = BarrierController("MOCK")
    bc.close("WORKSHOP_GATE")
    gate, cmd = bc.last_command()
    assert gate == "WORKSHOP_GATE"
    assert cmd == "CLOSE"

def test_04_command_log_preserves_order():
    bc = BarrierController("MOCK")
    bc.open("GATE_A")
    bc.close("GATE_A")
    bc.open("GATE_B")
    log = bc.command_log()
    assert log == [("GATE_A", "OPEN"), ("GATE_A", "CLOSE"), ("GATE_B", "OPEN")]

def test_05_last_command_empty_returns_none():
    bc = BarrierController("MOCK")
    assert bc.last_command() is None

def test_06_last_command_filtered_by_gate():
    bc = BarrierController("MOCK")
    bc.open("GATE_X")
    bc.close("GATE_Y")
    bc.open("GATE_X")
    result = bc.last_command("GATE_Y")
    assert result == ("GATE_Y", "CLOSE")
