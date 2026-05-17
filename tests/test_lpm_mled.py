from __future__ import annotations

import pytest

from src.lpm_mled import lpm_mled_correct, _substitution_cost, _weighted_edit_distance
from src.config import CONFUSION_COST, FULL_COST

def test_01_confusion_0_O():
    assert _substitution_cost("0", "O") == CONFUSION_COST
    assert _substitution_cost("O", "0") == CONFUSION_COST

def test_02_confusion_1_I():
    assert _substitution_cost("1", "I") == CONFUSION_COST
    assert _substitution_cost("I", "1") == CONFUSION_COST

def test_03_confusion_5_S():
    assert _substitution_cost("5", "S") == CONFUSION_COST
    assert _substitution_cost("S", "5") == CONFUSION_COST

def test_04_confusion_8_B():
    assert _substitution_cost("8", "B") == CONFUSION_COST
    assert _substitution_cost("B", "8") == CONFUSION_COST

def test_05_threshold_exact_rejected():

    result = lpm_mled_correct("AB", ["XB"])
    assert result is None

def test_06_threshold_just_below_accepted():

    result = lpm_mled_correct("WP-CA8-1234", ["WP-CAB-1234"])
    assert result == "WP-CAB-1234"

def test_07_case_insensitive():
    result = lpm_mled_correct("wp-cab-1234", ["WP-CAB-1234"])
    assert result == "WP-CAB-1234"

def test_08_empty_raw_returns_none():
    assert lpm_mled_correct("", ["WP-CAB-1234"]) is None

def test_09_empty_candidates_returns_none():
    assert lpm_mled_correct("WP-CAB-1234", []) is None

def test_10_two_confusion_errors_within_threshold():

    result = lpm_mled_correct("8O", ["BO"])
    assert result == "BO"

def test_11_non_confusion_substitution_rejected():

    raw = "ZZZZZZ"
    candidates = ["AAAAAA"]
    result = lpm_mled_correct(raw, candidates)
    assert result is None

def test_12_picks_closest_of_different_lengths():
    raw = "WP-CAB-1234"

    candidates = ["WP-CAB-12345", "WP-CAB-1234"]
    result = lpm_mled_correct(raw, candidates)
    assert result == "WP-CAB-1234"

def test_13_identical_raw_and_candidate():
    result = lpm_mled_correct("WP-CAB-1234", ["WP-CAB-1234"])
    assert result == "WP-CAB-1234"
    assert _weighted_edit_distance("WP-CAB-1234", "WP-CAB-1234") == 0.0

_SRI_LANKA_CASES = [

    ("WP-CA8-1234",  ["WP-CAB-1234"],                    "WP-CAB-1234"),
    ("WP-CAB-I234",  ["WP-CAB-1234"],                    "WP-CAB-1234"),
    ("WP-CA0-1234",  ["WP-CAO-1234"],                    "WP-CAO-1234"),
    ("WP-CA5-1234",  ["WP-CAS-1234"],                    "WP-CAS-1234"),
    ("KL-9OI2",      ["KL-9012"],                        "KL-9012"),
    ("CA8-34S6",     ["CAB-3456"],                       "CAB-3456"),
    ("WP-KA-567B",   ["WP-KA-5678"],                     "WP-KA-5678"),
    ("WP-G0-789O",   ["WP-GO-7890"],                     "WP-GO-7890"),
    ("5G-I111",      ["SG-1111"],                        "SG-1111"),
]

@pytest.mark.parametrize("raw,candidates,expected", _SRI_LANKA_CASES)
def test_14_to_22_sri_lanka_misreads(raw, candidates, expected):
    assert lpm_mled_correct(raw, candidates) == expected
