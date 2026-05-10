from __future__ import annotations

"""LPM-MLED: Licence Plate Matching via Minimum Levenshtein Edit Distance.

Implements a weighted edit-distance corrector that exploits the specific
character confusion pairs produced by the YOLOv8 37-class character
classifier at Colombo Dockyard.

Confusion pairs (substitution cost 0.1):
    {0, O}  {1, I}  {5, S}  {8, B}

All other substitutions: cost 1.0
Insertions / deletions:  cost 1.0
Normalisation:           dist / max(len(raw), len(candidate))
Acceptance threshold:    strict < 0.5  (exactly 0.5 is REJECTED)

References: section 6.3 of BUILD_SPEC.md
"""

import logging
from typing import Optional

from src.config import CONFUSION_PAIRS, CONFUSION_COST, FULL_COST, LPM_THRESHOLD

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core weighted edit-distance
# ---------------------------------------------------------------------------

def _substitution_cost(a: str, b: str) -> float:
    """Return the substitution cost between two characters.

    Returns ``CONFUSION_COST`` (0.1) if the pair is in the confusion set,
    otherwise ``FULL_COST`` (1.0).
    """
    return CONFUSION_COST if frozenset({a.upper(), b.upper()}) in CONFUSION_PAIRS else FULL_COST


def _weighted_edit_distance(s: str, t: str) -> float:
    """Wagner-Fischer weighted Levenshtein distance between *s* and *t*.

    Insertion / deletion cost: 1.0.
    Substitution cost: see ``_substitution_cost``.
    """
    m, n = len(s), len(t)
    # Initialise DP table
    dp: list[list[float]] = [
        [float(i) if j == 0 else (float(j) if i == 0 else 0.0)
         for j in range(n + 1)]
        for i in range(m + 1)
    ]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0.0 if s[i - 1] == t[j - 1] else _substitution_cost(s[i - 1], t[j - 1])
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,       # deletion
                dp[i][j - 1] + 1.0,       # insertion
                dp[i - 1][j - 1] + cost,  # substitution / match
            )
    return dp[m][n]


# ---------------------------------------------------------------------------
# Public corrector
# ---------------------------------------------------------------------------

def lpm_mled_correct(
    raw: str,
    candidates: list[str],
    threshold: float = LPM_THRESHOLD,
) -> Optional[str]:
    """Return the closest candidate plate to *raw*, or ``None``.

    Parameters
    ----------
    raw:
        The raw string produced by the character classifier (may contain
        OCR errors).
    candidates:
        Iterable of registered plate strings to match against.
    threshold:
        Normalised distance threshold.  Only candidates with
        ``normalised_dist < threshold`` are accepted.  **Strict less-than**:
        a normalised distance of exactly ``threshold`` is rejected.

    Returns
    -------
    str | None
        The best-matching candidate, or ``None`` if no candidate is within
        the threshold.
    """
    if not raw or not candidates:
        return None

    best_plate: Optional[str] = None
    best_score: float = threshold  # strict < only; starts at threshold

    for c in candidates:
        if not c:
            continue
        dist = _weighted_edit_distance(raw.upper(), c.upper())
        norm = dist / max(len(raw), len(c))
        if norm < best_score:
            best_score = norm
            best_plate = c

    return best_plate
