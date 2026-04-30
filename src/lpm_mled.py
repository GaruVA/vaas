"""LPM-MLED: Licence Plate Matching via Modified Levenshtein Edit Distance (FR-01.4, §6.3)."""
from __future__ import annotations

from typing import Optional

from src.config import CONFUSION_PAIRS, CONFUSION_COST, FULL_COST, LPM_THRESHOLD


def _substitution_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    pair = frozenset({a.upper(), b.upper()})
    return CONFUSION_COST if pair in CONFUSION_PAIRS else FULL_COST


def _weighted_edit_distance(s: str, t: str) -> float:
    m, n = len(s), len(t)
    if m == 0:
        return float(n)
    if n == 0:
        return float(m)
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = float(i)
    for j in range(n + 1):
        dp[0][j] = float(j)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = _substitution_cost(s[i - 1], t[j - 1])
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,
                dp[i][j - 1] + 1.0,
                dp[i - 1][j - 1] + cost,
            )
    return dp[m][n]


def lpm_mled_correct(raw: str, candidates: list[str]) -> Optional[str]:
    if not raw or not candidates:
        return None
    best_plate: Optional[str] = None
    best_score = LPM_THRESHOLD
    for c in candidates:
        if not c:
            continue
        norm = _weighted_edit_distance(raw.upper(), c.upper()) / max(len(raw), len(c))
        if norm < best_score:
            best_score = norm
            best_plate = c
    return best_plate
