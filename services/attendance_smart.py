"""
Smart attendance pattern analysis using K-Means (behaviour clusters) and
a Decision Tree regressor for a 0–100 reliability score.

Features: late arrivals, absenteeism, active days, work-hour consistency (from history),
and login/logout trends (first/last seen offsets, session span proxy).
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
from sklearn.cluster import KMeans
from sklearn.tree import DecisionTreeRegressor

# Feature order must stay stable for fitted models
_FEATURE_DIM = 7

# Human-readable categories from best (0) to worst (3) after ordering clusters by badness
_ATTENDANCE_CATEGORIES = [
    "Highly Consistent Attendance",
    "Stable with Minor Variation",
    "Irregular Attendance Pattern",
    "At-Risk Attendance",
]

_kmeans_model: KMeans | None = None
_reliability_tree: DecisionTreeRegressor | None = None
_cluster_order: list[int] | None = None  # cluster_id ordered best -> worst


def _as_mapping(h: Any) -> Mapping[str, Any]:
    if isinstance(h, dict):
        return h
    return h.model_dump() if hasattr(h, "model_dump") else {}


def _work_hour_consistency(history: list[Any]) -> float:
    """Higher = more stable hours week-to-week (0..1)."""
    if len(history) < 2:
        return 0.65
    hours: list[float] = []
    for point in history:
        m = _as_mapping(point)
        hours.append(float(m.get("working_hours", 0)))
    if not hours:
        return 0.65
    std = float(np.std(hours))
    # std 0 -> 1.0 consistency; std >= 4h -> 0 consistency
    return float(max(0.0, min(1.0, 1.0 - std / 4.0)))


def build_attendance_feature_row(payload: Mapping[str, Any], history: list[Any]) -> np.ndarray:
    late = float(payload.get("late_arrivals") or 0)
    absent = float(payload.get("absent_days") or 0)
    att_days = float(
        payload.get("attendance_days")
        or payload.get("telemetry_days_with_data")
        or 0
    )
    consistency = _work_hour_consistency(history)

    raw_first = payload.get("first_seen_offset_minutes")
    raw_last = payload.get("last_seen_offset_minutes")
    first_off = float(raw_first or 0)
    last_off = float(raw_last or 0)

    late_norm = min(late / 8.0, 1.0)
    absent_norm = min(absent / 10.0, 1.0)
    days_active_norm = min(att_days / 22.0, 1.0)
    login_late_norm = min(first_off / 240.0, 1.0)
    logout_late_norm = min(last_off / 240.0, 1.0)

    if raw_first is not None and raw_last is not None:
        session_span_norm = min(abs(last_off - first_off) / 480.0, 1.0)
    else:
        session_span_norm = 0.35

    row = np.array(
        [
            [
                late_norm,
                absent_norm,
                days_active_norm,
                consistency,
                login_late_norm,
                logout_late_norm,
                session_span_norm,
            ]
        ],
        dtype=np.float64,
    )
    assert row.shape == (1, _FEATURE_DIM)
    return row


def _reference_training_matrix() -> tuple[np.ndarray, np.ndarray]:
    """
    Synthetic reference employees for fitting K-Means and the reliability tree.
    Rows are plausible attendance feature vectors; y is rule-based reliability target.
    """
    rng = np.random.default_rng(42)
    rows: list[list[float]] = []

    # Archetypes: (late, absent, days, consistency, login_late, logout_late, span)
    archetypes = [
        [0.0, 0.0, 0.95, 0.92, 0.05, 0.05, 0.25],
        [0.15, 0.05, 0.85, 0.8, 0.12, 0.1, 0.3],
        [0.35, 0.2, 0.65, 0.55, 0.25, 0.22, 0.45],
        [0.55, 0.45, 0.45, 0.35, 0.45, 0.4, 0.65],
        [0.2, 0.35, 0.55, 0.45, 0.3, 0.28, 0.5],
        [0.6, 0.55, 0.4, 0.3, 0.5, 0.48, 0.7],
        [0.1, 0.15, 0.9, 0.75, 0.18, 0.15, 0.35],
        [0.45, 0.1, 0.72, 0.62, 0.35, 0.2, 0.55],
        [0.05, 0.25, 0.78, 0.68, 0.08, 0.35, 0.4],
        [0.7, 0.2, 0.5, 0.4, 0.55, 0.3, 0.6],
        [0.25, 0.5, 0.48, 0.42, 0.22, 0.38, 0.52],
        [0.5, 0.6, 0.38, 0.28, 0.42, 0.55, 0.68],
    ]
    for base in archetypes:
        for _ in range(8):
            noise = rng.normal(0, 0.03, size=_FEATURE_DIM)
            r = np.clip(np.array(base, dtype=np.float64) + noise, 0.0, 1.0)
            rows.append(r.tolist())

    x = np.array(rows, dtype=np.float64)
    # Reliability: higher when fewer lates/absences, more days, more consistency, calmer login/logout
    y = (
        100.0
        * (
            1.0
            - 0.22 * x[:, 0]
            - 0.28 * x[:, 1]
            - 0.12 * (1.0 - x[:, 2])
            - 0.18 * (1.0 - x[:, 3])
            - 0.1 * x[:, 4]
            - 0.1 * x[:, 5]
            - 0.1 * x[:, 6]
        )
    )
    y = np.clip(y + rng.normal(0, 2.0, size=y.shape), 0.0, 100.0)
    return x, y


def _ensure_models() -> None:
    global _kmeans_model, _reliability_tree, _cluster_order
    if _kmeans_model is not None and _reliability_tree is not None and _cluster_order is not None:
        return

    x_ref, y_ref = _reference_training_matrix()
    km = KMeans(n_clusters=4, random_state=42, n_init=10)
    km.fit(x_ref)
    _kmeans_model = km

    badness = []
    for cid in range(4):
        mask = km.labels_ == cid
        if not np.any(mask):
            badness.append((cid, 999.0))
            continue
        cmean = x_ref[mask].mean(axis=0)
        b = float(
            cmean[0]
            + cmean[1]
            + (1.0 - cmean[2])
            + (1.0 - cmean[3])
            + cmean[4]
            + cmean[5]
            + 0.5 * cmean[6]
        )
        badness.append((cid, b))
    badness.sort(key=lambda t: t[1])
    _cluster_order = [t[0] for t in badness]

    tree = DecisionTreeRegressor(max_depth=5, random_state=42)
    tree.fit(x_ref, y_ref)
    _reliability_tree = tree


def analyze_smart_attendance(payload: Mapping[str, Any], history: list[Any]) -> dict[str, Any]:
    """
    Run K-Means assignment + Decision Tree reliability on the current feature row.
    """
    _ensure_models()
    assert _kmeans_model is not None and _reliability_tree is not None and _cluster_order is not None

    x = build_attendance_feature_row(payload, history)
    cluster_id = int(_kmeans_model.predict(x)[0])
    rank = _cluster_order.index(cluster_id)
    category = _ATTENDANCE_CATEGORIES[rank]

    raw_reliability = float(_reliability_tree.predict(x)[0])
    reliability_score = round(max(0.0, min(100.0, raw_reliability)), 2)

    row = x[0]
    return {
        "attendance_category": category,
        "reliability_score": reliability_score,
        "kmeans_cluster_id": cluster_id,
        "category_rank": rank,
        "algorithms_used": ["KMeans", "DecisionTreeRegressor"],
        "features": {
            "late_arrival_intensity": round(float(row[0]), 4),
            "absenteeism_intensity": round(float(row[1]), 4),
            "active_days_norm": round(float(row[2]), 4),
            "work_consistency": round(float(row[3]), 4),
            "login_lateness_norm": round(float(row[4]), 4),
            "logout_lateness_norm": round(float(row[5]), 4),
            "session_span_norm": round(float(row[6]), 4),
        },
        "history_points_for_consistency": len(history),
    }
