"""Simple feature drift / distribution comparison helpers."""

from __future__ import annotations

import math
from typing import Sequence


def population_stability_index(expected: Sequence[float], actual: Sequence[float], buckets: int = 10) -> float:
    """Approximate PSI between two univariate samples. Returns 0 if insufficient data."""
    if len(expected) < 5 or len(actual) < 5:
        return 0.0
    lo = min(min(expected), min(actual))
    hi = max(max(expected), max(actual))
    if hi <= lo:
        return 0.0
    width = (hi - lo) / buckets
    eps = 1e-6
    psi = 0.0
    for i in range(buckets):
        a = lo + i * width
        b = lo + (i + 1) * width
        e_count = sum(1 for v in expected if a <= v < b or (i == buckets - 1 and v == b))
        a_count = sum(1 for v in actual if a <= v < b or (i == buckets - 1 and v == b))
        e_pct = e_count / len(expected) + eps
        a_pct = a_count / len(actual) + eps
        psi += (a_pct - e_pct) * math.log(a_pct / e_pct)
    return round(psi, 4)


def drift_severity(psi: float) -> str:
    if psi < 0.1:
        return "low"
    if psi < 0.25:
        return "medium"
    return "high"


def summarize_drift(baseline: Sequence[float], current: Sequence[float]) -> dict:
    psi = population_stability_index(baseline, current)
    return {
        "psi": psi,
        "severity": drift_severity(psi),
        "baseline_n": len(baseline),
        "current_n": len(current),
    }
