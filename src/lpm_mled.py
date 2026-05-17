from __future__ import annotations

import logging
from typing import Optional

from src.config import CONFUSION_PAIRS, CONFUSION_COST, FULL_COST, LPM_THRESHOLD

logger = logging.getLogger(__name__)

def _substitution_cost(a: str, b: str) -> float:
    return CONFUSION_COST if frozenset({a.upper(), b.upper()}) in CONFUSION_PAIRS else FULL_COST

def _weighted_edit_distance(s: str, t: str) -> float:
    m, n = len(s), len(t)

    dp: list[list[float]] = [
        [float(i) if j == 0 else (float(j) if i == 0 else 0.0)
         for j in range(n + 1)]
        for i in range(m + 1)
    ]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0.0 if s[i - 1] == t[j - 1] else _substitution_cost(s[i - 1], t[j - 1])
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,
                dp[i][j - 1] + 1.0,
                dp[i - 1][j - 1] + cost,
            )
    return dp[m][n]

def lpm_mled_correct(
    raw: str,
    candidates: list[str],
    threshold: float = LPM_THRESHOLD,
) -> Optional[str]:
    if not raw or not candidates:
        return None

    best_plate: Optional[str] = None
    best_score: float = threshold

    for c in candidates:
        if not c:
            continue
        dist = _weighted_edit_distance(raw.upper(), c.upper())
        norm = dist / max(len(raw), len(c))
        if norm < best_score:
            best_score = norm
            best_plate = c

    return best_plate
