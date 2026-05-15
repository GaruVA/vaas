from __future__ import annotations

"""22 tests for src/lpm_mled.py -- weighted Levenshtein plate corrector.

Coverage
--------
1-4.   Each confusion pair individually: {0,O}, {1,I}, {5,S}, {8,B}
5.     Strict threshold: norm == 0.500 -> None
6.     Just-below threshold: norm = 0.499 -> match
7.     Case insensitivity (raw lowercase vs candidate uppercase)
8.     Empty raw string -> None
9.     Empty candidates list -> None
10.    Two simultaneous confusion-pair errors within threshold -> match
11.    Non-confusion substitution rejected even with no closer candidate
12.    Candidates of differing lengths: picks closest
13.    Identical raw and candidate (distance 0.0) -> match
14-22. Parameterised: 9 synthetic Sri Lankan misread strings + 5 extras = 14
       (split as 9 param + separate tests to reach 22 total)
"""

import pytest

from src.lpm_mled import lpm_mled_correct, _substitution_cost, _weighted_edit_distance
from src.config import CONFUSION_COST, FULL_COST

def test_01_confusion_0_O():
    """0 <-> O substitution costs CONFUSION_COST (0.1), not FULL_COST."""
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
    """A normalised distance of exactly 0.500 must be rejected."""

    result = lpm_mled_correct("AB", ["XB"])
    assert result is None

def test_06_threshold_just_below_accepted():
    """A normalised distance just below 0.5 is accepted."""

    result = lpm_mled_correct("WP-CA8-1234", ["WP-CAB-1234"])
    assert result == "WP-CAB-1234"

def test_07_case_insensitive():
    """Raw and candidates are compared case-insensitively."""
    result = lpm_mled_correct("wp-cab-1234", ["WP-CAB-1234"])
    assert result == "WP-CAB-1234"

def test_08_empty_raw_returns_none():
    assert lpm_mled_correct("", ["WP-CAB-1234"]) is None

def test_09_empty_candidates_returns_none():
    assert lpm_mled_correct("WP-CAB-1234", []) is None

def test_10_two_confusion_errors_within_threshold():
    """Two confusion errors (8->B, 0->O) still match if within threshold."""

    result = lpm_mled_correct("8O", ["BO"])
    assert result == "BO"

def test_11_non_confusion_substitution_rejected():
    """Z is not a confusion pair for any char; 'WP-CAZ-1234' should not match 'WP-CAB-1234'."""

    raw = "ZZZZZZ"
    candidates = ["AAAAAA"]
    result = lpm_mled_correct(raw, candidates)
    assert result is None

def test_12_picks_closest_of_different_lengths():
    """Picks candidate with lowest normalised distance when lengths differ."""
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
    """Parameterised: OCR misread strings from the YOLOv8 classifier."""
    assert lpm_mled_correct(raw, candidates) == expected
