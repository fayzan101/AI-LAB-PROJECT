from datetime import datetime, timezone
from math import sqrt
from typing import Any, Iterable, Mapping

from services import scoring_policy as policy
from services.attendance_smart import analyze_smart_attendance
from services.data_quality import assess_data_quality
from services.explanations import build_explanations, compute_confidence


def _as_dict(data: Any) -> dict[str, Any]:
    return data if isinstance(data, dict) else data.model_dump()


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _std(values: Iterable[float], mean_value: float) -> float:
    items = list(values)
    if len(items) < 2:
        return 0.0
    variance = sum((v - mean_value) ** 2 for v in items) / len(items)
    return sqrt(variance)


def _effective_active_idle_seconds(payload: Mapping[str, Any]) -> tuple[int, int]:
    """Prefer explicit agent telemetry when present."""
    wh = float(payload.get("working_hours") or 0)
    ih = float(payload.get("idle_hours") or 0)
    raw_active = payload.get("active_seconds")
    raw_idle = payload.get("idle_seconds")
    active = int(raw_active) if raw_active is not None else max(0, int(round(wh * 3600)))
    idle = int(raw_idle) if raw_idle is not None else max(0, int(round(ih * 3600)))
    return active, idle


def has_telemetry_extras(payload: Mapping[str, Any]) -> bool:
    return payload.get("active_seconds") is not None or payload.get("segment_count") is not None


def classify_telemetry_signal_quality(payload: Mapping[str, Any]) -> str:
    wh = float(payload.get("working_hours") or 0)
    days = int(payload.get("telemetry_days_with_data") or payload.get("attendance_days") or 0)
    raw_seg = payload.get("segment_count")
    telemetry_like = has_telemetry_extras(payload) or raw_seg is not None
    seg = int(raw_seg) if raw_seg is not None else 0

    if wh <= 0 and days == 0:
        return "sparse"
    if not telemetry_like:
        return "sufficient"
    if wh > policy.SPARSE_WH_SEG_THRESHOLD and seg < policy.SPARSE_MIN_SEGMENTS:
        return "sparse"
    if days > 0 and seg == 0 and wh < policy.SPARSE_LOW_WH:
        return "sparse"
    return "sufficient"


def classify_presence_consistency(attendance_pattern: str) -> str:
    if attendance_pattern == "Regular":
        return "Regular"
    if attendance_pattern == "Needs Monitoring":
        return "NeedsMonitoring"
    return "Irregular"


def calculate_productivity(data: Any) -> float:
    payload = _as_dict(data)
    raw_score = (
        float(payload.get("tasks_completed", 0)) * policy.TASKS_COMPLETED_WEIGHT
        + float(payload.get("attendance_days", 0)) * policy.ATTENDANCE_DAYS_WEIGHT
        - float(payload.get("idle_hours", 0)) * policy.IDLE_HOURS_PENALTY
    )
    base = max(policy.PRODUCTIVITY_MIN, min(policy.PRODUCTIVITY_MAX, raw_score))

    active, idle = _effective_active_idle_seconds(payload)
    total = active + idle
    frag = payload.get("focus_fragmentation_index")
    if total > policy.MIN_TELEMETRY_SECONDS_FOR_RATIO and has_telemetry_extras(payload):
        ratio = active / total
        ratio_boost = max(
            -policy.ACTIVE_RATIO_CLAMP,
            min(policy.ACTIVE_RATIO_CLAMP, (ratio - policy.ACTIVE_RATIO_TARGET) * policy.ACTIVE_RATIO_SCALE),
        )
        base = max(policy.PRODUCTIVITY_MIN, min(policy.PRODUCTIVITY_MAX, base + ratio_boost))
        if frag is not None:
            penalty = min(policy.FRAGMENTATION_PENALTY_MAX, float(frag) * policy.FRAGMENTATION_PENALTY_SCALE)
            base = max(policy.PRODUCTIVITY_MIN, base - penalty)

    return round(base, 2)


def detect_burnout(data: Any) -> str:
    payload = _as_dict(data)
    hours = float(payload.get("working_hours", 0))
    productivity = calculate_productivity(payload)
    active, idle = _effective_active_idle_seconds(payload)
    total = active + idle
    idle_ratio = idle / total if total > 0 else 0.0

    if hours > policy.BURNOUT_HIGH_HOURS or (
        hours > policy.BURNOUT_HIGH_HOURS_LOW_PROD and productivity < policy.BURNOUT_HIGH_PROD_THRESHOLD
    ):
        return "High Risk"
    if idle_ratio >= policy.BURNOUT_IDLE_RATIO and hours >= policy.BURNOUT_IDLE_HOURS_MIN:
        return "Medium Risk"
    if hours > policy.BURNOUT_MEDIUM_HOURS or productivity < policy.BURNOUT_MEDIUM_PROD:
        return "Medium Risk"
    return "Low Risk"


def predict_delay(data: Any) -> str:
    payload = _as_dict(data)
    progress = float(payload.get("task_progress", 0))
    days_left = int(payload.get("days_left", 0))
    if progress < policy.DELAY_HIGH_PROGRESS and days_left < policy.DELAY_HIGH_DAYS_LEFT:
        return "High Risk"
    if progress < policy.DELAY_MEDIUM_PROGRESS:
        return "Medium Risk"
    return "Low Risk"


def analyze_attendance_pattern(data: Any) -> str:
    payload = _as_dict(data)
    late = int(payload.get("late_arrivals", 0))
    absent = int(payload.get("absent_days", 0))
    if has_telemetry_extras(payload):
        first_off = int(payload.get("first_seen_offset_minutes") or 0)
        if first_off >= policy.FIRST_SEEN_LATE_120:
            late = max(late, 3)
        if first_off >= policy.FIRST_SEEN_LATE_60:
            late = max(late, 2)
    if late >= policy.LATE_IRREGULAR or absent >= policy.ABSENT_IRREGULAR:
        return "Irregular"
    if late >= policy.LATE_MONITOR or absent >= policy.ABSENT_MONITOR:
        return "Needs Monitoring"
    return "Regular"


def adaptive_productivity_benchmark(current_productivity: float, history: list[Any]) -> dict[str, Any]:
    if not history:
        return {
            "status": "Insufficient Data",
            "z_score": 0.0,
            "baseline_mean": round(current_productivity, 2),
            "baseline_std": 0.0,
            "sample_count": 0,
            "message": "No historical productivity records available yet.",
        }

    scores: list[float] = []
    for point in history:
        if isinstance(point, dict):
            scores.append(float(point.get("productivity_score", 0)))
        else:
            scores.append(float(getattr(point, "productivity_score", 0)))
    baseline_mean = _mean(scores)
    baseline_std = _std(scores, baseline_mean)
    sample_count = len(scores)
    z_score = 0.0 if baseline_std == 0 else (current_productivity - baseline_mean) / baseline_std

    if sample_count < policy.BENCHMARK_WARMUP_SAMPLES:
        status = "Warm-up"
        message = "Collect more history for stable personalized baseline."
    elif z_score <= policy.BENCHMARK_DECLINE_Z:
        status = "Decline"
        message = "Performance is lower than personal baseline."
    elif z_score >= policy.BENCHMARK_IMPROVE_Z:
        status = "Improvement"
        message = "Performance is above personal baseline."
    else:
        status = "Stable"
        message = "Performance is within personal baseline range."

    return {
        "status": status,
        "z_score": round(z_score, 2),
        "baseline_mean": round(baseline_mean, 2),
        "baseline_std": round(baseline_std, 2),
        "sample_count": sample_count,
        "message": message,
    }


def detect_work_anomaly(data: Any, productivity: float, history: list[Any]) -> dict[str, Any]:
    payload = _as_dict(data)
    reasons: list[str] = []
    severity = "Low"

    working_hours = float(payload.get("working_hours", 0))
    idle_hours = float(payload.get("idle_hours", 0))
    active, idle = _effective_active_idle_seconds(payload)
    total = active + idle
    idle_ratio = idle / total if total > 0 else 0.0

    if working_hours >= policy.ANOMALY_EXCESSIVE_HOURS:
        reasons.append("Excessive daily working hours")
    if idle_hours >= policy.ANOMALY_IDLE_HOURS or idle_ratio >= policy.ANOMALY_IDLE_RATIO:
        reasons.append("Unusually high idle proportion")
    if productivity <= policy.ANOMALY_PROD_DROP:
        reasons.append("Sudden productivity drop")

    if history:
        historical_scores: list[float] = []
        for point in history:
            if hasattr(point, "productivity_score"):
                historical_scores.append(float(point.productivity_score))
            else:
                historical_scores.append(float(point.get("productivity_score", 0)))
        mean_val = _mean(historical_scores)
        std_val = _std(historical_scores, mean_val)
        if std_val > 0:
            z_score = (productivity - mean_val) / std_val
            if z_score <= policy.ANOMALY_OUTLIER_Z:
                reasons.append("Productivity is a statistical outlier below baseline")

    if len(reasons) >= 3:
        severity = "High"
    elif len(reasons) == 2:
        severity = "Medium"

    return {
        "is_anomaly": len(reasons) > 0,
        "severity": severity,
        "reasons": reasons,
    }


def generate_recommendations(
    burnout: str,
    delay: str,
    attendance_pattern: str,
    anomaly_result: Mapping[str, Any],
    benchmark_result: Mapping[str, Any],
    signal_quality: str,
) -> list[str]:
    recommendations: list[str] = []
    if burnout == "High Risk":
        recommendations.append("Reduce workload and schedule mandatory recovery time.")
    if delay in {"High Risk", "Medium Risk"}:
        recommendations.append("Prioritize critical tasks and add interim checkpoints.")
    if attendance_pattern != "Regular":
        recommendations.append("Review attendance trends and discuss flexibility needs.")
    if anomaly_result["is_anomaly"]:
        recommendations.append("Trigger manager review for unusual work behavior patterns.")
    if benchmark_result["status"] == "Decline":
        recommendations.append("Set a short-term performance recovery plan with weekly follow-up.")
    if signal_quality == "sparse":
        recommendations.append("Telemetry coverage is sparse; verify agent pairing before drawing firm conclusions.")
    if not recommendations:
        recommendations.append("Maintain current workflow and continue periodic monitoring.")
    return recommendations


def generate_summary(
    prod: float,
    burnout: str,
    delay: str,
    attendance_pattern: str,
    benchmark_status: str,
    anomaly_flag: bool,
    signal_quality: str,
) -> str:
    if signal_quality == "sparse":
        return "Limited agent telemetry this period — interpret scores cautiously."
    if burnout == "High Risk":
        return "Employee shows high burnout risk and needs immediate workload intervention."
    if anomaly_flag:
        return "Employee behavior contains anomalies and requires closer managerial monitoring."
    if benchmark_status == "Decline":
        return "Employee is trending below personal baseline and may need support."
    if prod > 70 and delay == "Low Risk" and attendance_pattern == "Regular":
        return "Employee performance is strong and consistent."
    return "Employee performance is moderate; continue monitoring and coaching."


def build_full_report(
    payload: Mapping[str, Any],
    *,
    tenant_id: str,
    employee_id: str,
    history: list[Any],
) -> dict[str, Any]:
    """Pure rule-engine output consumed by analytics route (+ optional ML meta)."""
    dq = assess_data_quality(payload)
    productivity = calculate_productivity(payload)
    burnout = detect_burnout(payload)
    delay = predict_delay(payload)
    attendance_pattern = analyze_attendance_pattern(payload)
    benchmark = adaptive_productivity_benchmark(productivity, history)
    anomaly = detect_work_anomaly(payload, productivity, history)
    signal_quality = classify_telemetry_signal_quality(payload)
    presence = classify_presence_consistency(attendance_pattern)
    summary = generate_summary(
        productivity,
        burnout,
        delay,
        attendance_pattern,
        benchmark["status"],
        anomaly["is_anomaly"],
        signal_quality,
    )
    recommendations = generate_recommendations(
        burnout,
        delay,
        attendance_pattern,
        anomaly,
        benchmark,
        signal_quality,
    )

    smart_attendance = analyze_smart_attendance(payload, history)
    rel = smart_attendance["reliability_score"]
    rank = smart_attendance["category_rank"]
    if rel < policy.SMART_LOW_RELIABILITY:
        recommendations.append(
            "Smart attendance analysis shows low reliability — review schedule adherence, absences, and login/logout consistency."
        )
    elif rank >= policy.SMART_IRREGULAR_RANK:
        recommendations.append(
            "Attendance clustering suggests irregular patterns — discuss flexibility, workload, and barriers to consistent start times."
        )

    confidence = compute_confidence(
        signal_quality=signal_quality,
        history_count=len(history),
        data_quality_status=dq["status"],
        has_telemetry=has_telemetry_extras(payload),
    )
    explanations = build_explanations(
        payload,
        productivity=productivity,
        burnout=burnout,
        delay=delay,
        attendance_pattern=attendance_pattern,
        signal_quality=signal_quality,
        anomaly=anomaly,
    )

    return {
        "tenant_id": tenant_id,
        "employee_id": employee_id,
        "productivity_score": productivity,
        "burnout_risk": burnout,
        "task_delay_risk": delay,
        "attendance_pattern": attendance_pattern,
        "adaptive_benchmark": benchmark,
        "anomaly_detection": anomaly,
        "summary": summary,
        "recommendations": recommendations,
        "telemetry_signal_quality": signal_quality,
        "presence_consistency": presence,
        "smart_attendance": smart_attendance,
        "rule_engine_version": policy.RULE_ENGINE_VERSION,
        "scoring_mode": "rules",
        "confidence": confidence,
        "data_quality": dq,
        "explanations": explanations,
        # Persisted for historical baselines (no fabricated defaults on the portal)
        "working_hours": float(payload.get("working_hours") or 0),
        "idle_hours": float(payload.get("idle_hours") or 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
