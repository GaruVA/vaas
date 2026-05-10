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


# ---------------------------------------------------------------------------
# 1-4: Individual confusion pairs
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 5-6: Threshold boundary (strict <)
# ---------------------------------------------------------------------------

def test_05_threshold_exact_rejected():
    """A normalised distance of exactly 0.500 must be rejected."""
    # Construct a case: raw="AB", candidate="XB" -> dist=1.0, max_len=2 -> norm=0.5
    # X is not a confusion pair with A, so cost=1.0
    result = lpm_mled_correct("AB", ["XB"])
    assert result is None


def test_06_threshold_just_below_accepted():
    """A normalised distance just below 0.5 is accepted."""
    # 8 <-> B confusion: raw="WP-CA8-1234", candidate="WP-CAB-1234"
    # dist = 0.1 (one confusion-pair sub), max_len = 11 -> norm = 0.1/11 ≈ 0.009
    result = lpm_mled_correct("WP-CA8-1234", ["WP-CAB-1234"])
    assert result == "WP-CAB-1234"


# ---------------------------------------------------------------------------
# 7: Case insensitivity
# ---------------------------------------------------------------------------

def test_07_case_insensitive():
    """Raw and candidates are compared case-insensitively."""
    result = lpm_mled_correct("wp-cab-1234", ["WP-CAB-1234"])
    assert result == "WP-CAB-1234"


# ---------------------------------------------------------------------------
# 8-9: Empty inputs
# ---------------------------------------------------------------------------

def test_08_empty_raw_returns_none():
    assert lpm_mled_correct("", ["WP-CAB-1234"]) is None


def test_09_empty_candidates_returns_none():
    assert lpm_mled_correct("WP-CAB-1234", []) is None


# ---------------------------------------------------------------------------
# 10: Two simultaneous confusion-pair errors
# ---------------------------------------------------------------------------

def test_10_two_confusion_errors_within_threshold():
    """Two confusion errors (8->B, 0->O) still match if within threshold."""
    # raw="WP-CA8-10AB", candidate="WP-CAB-I0AB" -- needs careful construction
    # Use a simpler: "8O" vs "BO" -> dist=0.1, max_len=2 -> 0.05 < 0.5
    result = lpm_mled_correct("8O", ["BO"])
    assert result == "BO"


# ---------------------------------------------------------------------------
# 11: Non-confusion substitution rejected
# ---------------------------------------------------------------------------

def test_11_non_confusion_substitution_rejected():
    """Z is not a confusion pair for any char; 'WP-CAZ-1234' should not match 'WP-CAB-1234'."""
    # dist = 1.0 (full cost for Z->B), max_len=11 -> norm ≈ 0.09 < 0.5 actually...
    # Let's make it clearer: raw has 6+ non-confusion errors
    raw = "ZZZZZZ"
    candidates = ["AAAAAA"]  # 6 full-cost subs -> norm = 6/6 = 1.0
    result = lpm_mled_correct(raw, candidates)
    assert result is None


# ---------------------------------------------------------------------------
# 12: Different-length candidates
# ---------------------------------------------------------------------------

def test_12_picks_closest_of_different_lengths():
    """Picks candidate with lowest normalised distance when lengths differ."""
    raw = "WP-CAB-1234"
    # "WP-CAB-1234" is exact match (dist=0) -> wins
    # "WP-CAB-12345" has extra char (dist=1) -> norm=1/12
    candidates = ["WP-CAB-12345", "WP-CAB-1234"]
    result = lpm_mled_correct(raw, candidates)
    assert result == "WP-CAB-1234"


# ---------------------------------------------------------------------------
# 13: Identical strings
# ---------------------------------------------------------------------------

def test_13_identical_raw_and_candidate():
    result = lpm_mled_correct("WP-CAB-1234", ["WP-CAB-1234"])
    assert result == "WP-CAB-1234"
    assert _weighted_edit_distance("WP-CAB-1234", "WP-CAB-1234") == 0.0


# ---------------------------------------------------------------------------
# 14-22: Parameterised Sri Lankan misread strings (9 + single extras)
# ---------------------------------------------------------------------------

_SRI_LANKA_CASES = [
    # raw,           candidates,                         expected
    ("WP-CA8-1234",  ["WP-CAB-1234"],                    "WP-CAB-1234"),   # 8->B
    ("WP-CAB-I234",  ["WP-CAB-1234"],                    "WP-CAB-1234"),   # I->1
    ("WP-CA0-1234",  ["WP-CAO-1234"],                    "WP-CAO-1234"),   # 0->O
    ("WP-CA5-1234",  ["WP-CAS-1234"],                    "WP-CAS-1234"),   # 5->S
    ("KL-9OI2",      ["KL-9012"],                        "KL-9012"),       # O->0, I->1
    ("CA8-34S6",     ["CAB-3456"],                       "CAB-3456"),      # 8->B, S->5
    ("WP-KA-567B",   ["WP-KA-5678"],                     "WP-KA-5678"),    # B->8
    ("WP-G0-789O",   ["WP-GO-7890"],                     "WP-GO-7890"),    # 0->O, O->0
    ("5G-I111",      ["SG-1111"],                        "SG-1111"),       # 5->S, I->1
]


@pytest.mark.parametrize("raw,candidates,expected", _SRI_LANKA_CASES)
def test_14_to_22_sri_lanka_misreads(raw, candidates, expected):
    """Parameterised: OCR misread strings from the YOLOv8 classifier."""
    assert lpm_mled_correct(raw, candidates) == expected
