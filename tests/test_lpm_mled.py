"""22 tests for LPM-MLED (FR-01.4, §6.3, §7.2)."""
from __future__ import annotations

from src.lpm_mled import (
    _substitution_cost,
    _weighted_edit_distance,
    lpm_mled_correct,
)


CANDS = ["CAB-1234", "KL-5678", "WP-CAB-9012"]


def test_exact_match_returns_input():
    assert lpm_mled_correct("CAB-1234", CANDS) == "CAB-1234"


def test_exact_match_zero_distance():
    assert _weighted_edit_distance("CAB-1234", "CAB-1234") == 0.0


def test_confusion_pair_8_B_accepted():
    assert lpm_mled_correct("CA8-1234", ["CAB-1234"]) == "CAB-1234"


def test_confusion_pair_0_O_accepted():
    assert lpm_mled_correct("0PEL-12", ["OPEL-12"]) == "OPEL-12"


def test_confusion_pair_1_I_accepted():
    assert lpm_mled_correct("1NDIA1", ["INDIA1"]) == "INDIA1"


def test_confusion_pair_5_S_accepted():
    assert lpm_mled_correct("5UN-1234", ["SUN-1234"]) == "SUN-1234"


def test_two_confusion_pairs_within_threshold():
    # B->8 and O->0 in a longer plate
    assert lpm_mled_correct("CA8-O123", ["CAB-O123"]) == "CAB-O123"


def test_non_confusion_substitution_rejected():
    # Z is not in a confusion pair with B; on length-2 plate, full sub -> 0.5 = threshold
    assert lpm_mled_correct("AZ", ["AB"]) is None


def test_threshold_boundary_exact_returns_none():
    # Pure non-confusion full substitution at full cost on length-2 string -> normalised 0.5
    assert lpm_mled_correct("AB", ["AC"]) is None


def test_empty_candidates_returns_none():
    assert lpm_mled_correct("CAB-1234", []) is None


def test_empty_raw_returns_none():
    assert lpm_mled_correct("", CANDS) is None


def test_empty_raw_and_candidates():
    assert lpm_mled_correct("", []) is None


def test_different_lengths_handled():
    # Insertion cost 1.0 across length 8 = 0.125 < 0.5
    assert lpm_mled_correct("CAB-123", ["CAB-1234"]) == "CAB-1234"


def test_case_insensitivity():
    assert lpm_mled_correct("cab-1234", ["CAB-1234"]) == "CAB-1234"


def test_picks_closest_among_many():
    cands = ["CAR-9999", "CAB-1234", "VAN-0000"]
    assert lpm_mled_correct("CA8-1234", cands) == "CAB-1234"


def test_substitution_cost_identity_zero():
    assert _substitution_cost("A", "A") == 0.0


def test_substitution_cost_confusion_low():
    assert _substitution_cost("8", "B") == 0.1
    assert _substitution_cost("0", "O") == 0.1
    assert _substitution_cost("1", "I") == 0.1
    assert _substitution_cost("5", "S") == 0.1


def test_substitution_cost_full():
    assert _substitution_cost("A", "Z") == 1.0


def test_distance_is_symmetric_for_letters():
    assert _weighted_edit_distance("CAB", "CA8") == _weighted_edit_distance("CA8", "CAB")


def test_distance_handles_one_empty():
    assert _weighted_edit_distance("", "ABC") == 3.0
    assert _weighted_edit_distance("ABC", "") == 3.0


def test_long_plate_with_one_confusion():
    # 8 chars, one confusion -> 0.1 / 8 = 0.0125 < 0.5
    assert lpm_mled_correct("CA8-1234", ["CAB-1234"]) == "CAB-1234"


def test_far_match_not_returned_over_close_match():
    cands = ["XYZ-9999", "CAB-1234"]
    assert lpm_mled_correct("CAB-1235", cands) == "CAB-1234"
