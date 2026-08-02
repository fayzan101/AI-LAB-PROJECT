"""Evidence-backed explanations and confidence for analytics reports."""

from __future__ import annotations

from typing import Any, Mapping

from services import scoring_policy as policy


def _effective_active_idle_seconds(payload: Mapping[str, Any]) -> tuple[int, int]:
    wh = float(payload.get("working_hours") or 0)
    ih = float(payload.get("idle_hours") or 0)
    raw_active = payload.get("active_seconds")
    raw_idle = payload.get("idle_seconds")
    active = int(raw_active) if raw_active is not None else max(0, int(round(wh * 3600)))
    idle = int(raw_idle) if raw_idle is not None else max(0, int(round(ih * 3600)))
    return active, idle


def _has_telemetry_extras(payload: Mapping[str, Any]) -> bool:
    return payload.get("active_seconds") is not None or payload.get("segment_count") is not None


def compute_confidence(
    *,
    signal_quality: str,
    history_count: int,
    data_quality_status: str,
    has_telemetry: bool,
) -> float:
    score = policy.CONFIDENCE_BASE
    if signal_quality == "sparse":
        score -= policy.CONFIDENCE_SPARSE_PENALTY
    bonus = min(policy.CONFIDENCE_HISTORY_BONUS_CAP, history_count * policy.CONFIDENCE_HISTORY_BONUS_PER)
    score += bonus
    if has_telemetry and signal_quality == "sufficient":
        score += policy.CONFIDENCE_TELEMETRY_BONUS
    if data_quality_status == "fail":
        score -= 0.2
    elif data_quality_status == "warn":
        score -= 0.08
    return round(max(policy.CONFIDENCE_MIN, min(policy.CONFIDENCE_MAX, score)), 3)


def build_explanations(
    payload: Mapping[str, Any],
    *,
    productivity: float,
    burnout: str,
    delay: str,
    attendance_pattern: str,
    signal_quality: str,
    anomaly: Mapping[str, Any],
) -> list[dict[str, Any]]:
    explanations: list[dict[str, Any]] = []
    tasks = float(payload.get("tasks_completed") or 0)
    attendance = float(payload.get("attendance_days") or 0)
    idle_h = float(payload.get("idle_hours") or 0)
    hours = float(payload.get("working_hours") or 0)
    progress = float(payload.get("task_progress") or 0)
    days_left = int(payload.get("days_left") or 0)

    task_contrib = tasks * policy.TASKS_COMPLETED_WEIGHT
    att_contrib = attendance * policy.ATTENDANCE_DAYS_WEIGHT
    idle_contrib = -idle_h * policy.IDLE_HOURS_PENALTY

    explanations.append(
        {
            "factor": "tasks_completed",
            "direction": "up" if tasks > 0 else "neutral",
            "weight": policy.TASKS_COMPLETED_WEIGHT,
            "evidence": f"{int(tasks)} tasks × {policy.TASKS_COMPLETED_WEIGHT} = {task_contrib:.1f}",
            "contribution": round(task_contrib, 2),
        }
    )
    explanations.append(
        {
            "factor": "attendance_days",
            "direction": "up" if attendance > 0 else "neutral",
            "weight": policy.ATTENDANCE_DAYS_WEIGHT,
            "evidence": f"{int(attendance)} days × {policy.ATTENDANCE_DAYS_WEIGHT} = {att_contrib:.1f}",
            "contribution": round(att_contrib, 2),
        }
    )
    explanations.append(
        {
            "factor": "idle_hours",
            "direction": "down" if idle_h > 0 else "neutral",
            "weight": -policy.IDLE_HOURS_PENALTY,
            "evidence": f"{idle_h:.1f} idle hours (penalty)",
            "contribution": round(idle_contrib, 2),
        }
    )

    active, idle = _effective_active_idle_seconds(payload)
    total = active + idle
    if total > policy.MIN_TELEMETRY_SECONDS_FOR_RATIO and _has_telemetry_extras(payload):
        ratio = active / total
        boost = max(-policy.ACTIVE_RATIO_CLAMP, min(policy.ACTIVE_RATIO_CLAMP, (ratio - policy.ACTIVE_RATIO_TARGET) * policy.ACTIVE_RATIO_SCALE))
        explanations.append(
            {
                "factor": "active_idle_ratio",
                "direction": "up" if boost >= 0 else "down",
                "weight": policy.ACTIVE_RATIO_SCALE,
                "evidence": f"active ratio {ratio:.2f} vs target {policy.ACTIVE_RATIO_TARGET} → {boost:+.1f}",
                "contribution": round(boost, 2),
            }
        )

    explanations.append(
        {
            "factor": "productivity_score",
            "direction": "neutral",
            "weight": 1.0,
            "evidence": f"Final productivity score {productivity}",
            "contribution": productivity,
        }
    )
    explanations.append(
        {
            "factor": "burnout_risk",
            "direction": "down" if burnout != "Low Risk" else "neutral",
            "weight": 1.0,
            "evidence": f"{burnout} (working_hours={hours:.1f})",
            "contribution": 0.0,
        }
    )
    explanations.append(
        {
            "factor": "task_delay_risk",
            "direction": "down" if delay != "Low Risk" else "neutral",
            "weight": 1.0,
            "evidence": f"{delay} (progress={progress:.0f}%, days_left={days_left})",
            "contribution": 0.0,
        }
    )
    explanations.append(
        {
            "factor": "attendance_pattern",
            "direction": "down" if attendance_pattern != "Regular" else "up",
            "weight": 1.0,
            "evidence": attendance_pattern,
            "contribution": 0.0,
        }
    )
    explanations.append(
        {
            "factor": "telemetry_signal_quality",
            "direction": "down" if signal_quality == "sparse" else "up",
            "weight": 1.0,
            "evidence": signal_quality,
            "contribution": 0.0,
        }
    )
    if anomaly.get("is_anomaly"):
        explanations.append(
            {
                "factor": "anomaly",
                "direction": "down",
                "weight": 1.0,
                "evidence": "; ".join(anomaly.get("reasons") or []) or anomaly.get("severity", "anomaly"),
                "contribution": 0.0,
            }
        )
    return explanations
