"""Input validation and data-quality assessment for analytics payloads."""

from __future__ import annotations

from typing import Any, Mapping


def assess_data_quality(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return status + issues without blocking scoring."""
    issues: list[str] = []
    warnings: list[str] = []

    wh = float(payload.get("working_hours") or 0)
    ih = float(payload.get("idle_hours") or 0)
    progress = float(payload.get("task_progress") or 0)
    days = int(payload.get("telemetry_days_with_data") or payload.get("attendance_days") or 0)

    if wh < 0 or ih < 0:
        issues.append("negative_hours")
    if wh > 24:
        issues.append("working_hours_exceed_day")
    if ih > 24:
        issues.append("idle_hours_exceed_day")
    if progress < 0 or progress > 100:
        issues.append("task_progress_out_of_range")
    if wh == 0 and ih == 0 and days == 0:
        warnings.append("no_hours_or_attendance")

    active = payload.get("active_seconds")
    idle = payload.get("idle_seconds")
    if active is not None and int(active) < 0:
        issues.append("negative_active_seconds")
    if idle is not None and int(idle) < 0:
        issues.append("negative_idle_seconds")
    if active is not None and idle is not None:
        total = int(active) + int(idle)
        if total == 0 and wh > 0:
            warnings.append("telemetry_seconds_zero_with_working_hours")

    frag = payload.get("focus_fragmentation_index")
    if frag is not None and float(frag) < 0:
        issues.append("negative_fragmentation")

    if issues:
        status = "fail"
    elif warnings:
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "checked_fields": [
            "working_hours",
            "idle_hours",
            "task_progress",
            "active_seconds",
            "idle_seconds",
            "attendance_days",
        ],
    }
