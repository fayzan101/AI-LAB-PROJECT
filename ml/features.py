"""Shared feature vectors for train and serve paths."""

from __future__ import annotations

from typing import Any, Mapping

FEATURE_SCHEMA_VERSION = "1"
FEATURE_NAMES_V1 = [
    "working_hours",
    "idle_hours",
    "attendance_days",
    "segment_count",
    "focus_fragmentation_index",
    "task_progress",
    "tasks_completed",
    "active_hours",
    "idle_hours_effective",
]


def _effective_seconds(payload: Mapping[str, Any]) -> tuple[float, float]:
    wh = float(payload.get("working_hours") or 0)
    ih = float(payload.get("idle_hours") or 0)
    a = payload.get("active_seconds")
    i = payload.get("idle_seconds")
    active_h = (int(a) / 3600.0) if a is not None else wh
    idle_h = (int(i) / 3600.0) if i is not None else ih
    return active_h, idle_h


def build_feature_vector_v1(payload: Mapping[str, Any]) -> list[float]:
    active_h, idle_h = _effective_seconds(payload)
    return [
        float(payload.get("working_hours") or 0),
        float(payload.get("idle_hours") or 0),
        float(payload.get("attendance_days") or 0),
        float(payload.get("segment_count") or 0),
        float(payload.get("focus_fragmentation_index") or 0),
        float(payload.get("task_progress") or 0),
        float(payload.get("tasks_completed") or 0),
        active_h,
        idle_h,
    ]
