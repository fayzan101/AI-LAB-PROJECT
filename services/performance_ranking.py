"""
AI-based employee performance ranking: weighted composite + optional Random Forest analysis.

Primary rank uses a configurable weighted linear model over five pillars (0–100).
When cohort size >= 4 and scikit-learn is available, fits a RandomForestRegressor to
approximate the composite from pillars, blends a small ML adjustment into final_score,
and exposes feature importances in meta.
"""

from __future__ import annotations
from typing import Any, Mapping
import numpy as np

# Sum to 1.0 — productivity, task completion, attendance, desk efficiency, collaboration proxy
DEFAULT_WEIGHTS: dict[str, float] = {
    "productivity": 0.22,
    "task_completion": 0.22,
    "attendance": 0.18,
    "efficiency": 0.18,
    "collaboration": 0.20,
}

PILLARS = ("productivity", "task_completion", "attendance", "efficiency", "collaboration")


def _composite(row: Mapping[str, Any], weights: dict[str, float]) -> float:
    return float(sum(weights[k] * float(row[k]) for k in PILLARS))


def _minmax_scale(arr: np.ndarray) -> np.ndarray:
    lo = float(np.min(arr))
    hi = float(np.max(arr))
    if hi <= lo:
        return np.full_like(arr, 50.0, dtype=float)
    return (arr - lo) / (hi - lo) * 100.0


def _bands(n: int, ranks_1_based: list[int]) -> list[str]:
    """Top ~33% / bottom ~33% by rank (1 = best)."""
    if n <= 0:
        return []
    third = max(1, n // 3)
    top_cut = third
    low_cut = n - third + 1
    out: list[str] = []
    for r in ranks_1_based:
        if r <= top_cut:
            out.append("top")
        elif r >= low_cut:
            out.append("low")
        else:
            out.append("mid")
    return out


def compute_performance_ranking(
    employees: list[Mapping[str, Any]],
    *,
    weights: dict[str, float] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Returns (data dict for ApiEnvelope.data, extra meta dict).
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total_w = sum(w[k] for k in PILLARS)
    if total_w > 0:
        w = {k: w[k] / total_w for k in PILLARS}

    n = len(employees)
    composites = np.array([_composite(e, w) for e in employees], dtype=float)

    ml_meta: dict[str, Any] = {"random_forest_used": False}
    final_scores = composites.copy()

    if n >= 4:
        try:
            from sklearn.ensemble import RandomForestRegressor  # noqa: PLC0415

            X = np.array([[float(e[k]) for k in PILLARS] for e in employees], dtype=float)
            y = composites.copy()
            rf = RandomForestRegressor(
                n_estimators=64,
                max_depth=5,
                min_samples_leaf=1,
                random_state=42,
            )
            rf.fit(X, y)
            pred = np.asarray(rf.predict(X), dtype=float)
            pred_scaled = _minmax_scale(pred)
            # Small ML blend so ranking can shift slightly when trees find interactions
            final_scores = 0.72 * composites + 0.28 * pred_scaled
            imps = rf.feature_importances_
            ml_meta = {
                "random_forest_used": True,
                "feature_importances": {PILLARS[i]: round(float(imps[i]), 4) for i in range(len(PILLARS))},
            }
        except Exception as exc:  # noqa: BLE001
            ml_meta = {"random_forest_used": False, "random_forest_error": str(exc)}
            final_scores = composites.copy()

    order = np.argsort(-final_scores)  # descending
    ranks = np.empty(n, dtype=int)
    for pos, idx in enumerate(order):
        ranks[idx] = pos + 1

    bands = _bands(n, [int(ranks[i]) for i in range(n)])

    rankings: list[dict[str, Any]] = []
    for i in range(n):
        e = employees[i]
        rankings.append(
            {
                "employee_id": str(e["employee_id"]),
                "display_name": e.get("display_name"),
                "department_id": e.get("department_id"),
                "department_name": e.get("department_name"),
                "rank": int(ranks[i]),
                "composite_score": round(float(composites[i]), 2),
                "final_score": round(float(final_scores[i]), 2),
                "band": bands[i],
                "productivity": round(float(e["productivity"]), 2),
                "task_completion": round(float(e["task_completion"]), 2),
                "attendance": round(float(e["attendance"]), 2),
                "efficiency": round(float(e["efficiency"]), 2),
                "collaboration": round(float(e["collaboration"]), 2),
            }
        )

    rankings.sort(key=lambda r: r["rank"])

    top_n = max(1, min(3, n))
    top_performer_ids = [rankings[i]["employee_id"] for i in range(top_n)]
    low_performer_ids = [rankings[n - 1 - i]["employee_id"] for i in range(top_n)]

    # Department aggregates
    dept_map: dict[str, list[float]] = {}
    dept_names: dict[str, str] = {}
    for row in rankings:
        did = row.get("department_id") or "__none__"
        dname = row.get("department_name") or ("Unassigned" if did == "__none__" else str(did))
        dept_names[did] = dname
        dept_map.setdefault(did, []).append(float(row["final_score"]))

    dept_rows: list[dict[str, Any]] = []
    for did, scores in dept_map.items():
        dept_rows.append(
            {
                "department_id": None if did == "__none__" else did,
                "department_name": dept_names.get(did, "—"),
                "member_count": len(scores),
                "avg_composite": round(float(np.mean(scores)), 2),
            }
        )
    dept_rows.sort(key=lambda d: -d["avg_composite"])
    departments = [{**d, "rank": i + 1} for i, d in enumerate(dept_rows)]

    algorithms = ["weighted_linear"]
    if ml_meta.get("random_forest_used"):
        algorithms.append("random_forest_regressor")

    data = {
        "rankings": rankings,
        "departments": departments,
        "weights": {k: round(v, 4) for k, v in w.items()},
        "algorithms_used": algorithms,
        "top_performer_ids": top_performer_ids,
        "low_performer_ids": low_performer_ids,
    }
    extra_meta = {**ml_meta, "cohort_size": n}
    return data, extra_meta
