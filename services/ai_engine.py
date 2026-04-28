from math import sqrt
from typing import Iterable


def _as_dict(data):
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


def calculate_productivity(data):
    payload = _as_dict(data)
    raw_score = (
        payload.get("tasks_completed", 0) * 3
        + payload.get("attendance_days", 0) * 2
        - payload.get("idle_hours", 0)
    )
    return round(max(0.0, min(100.0, raw_score)), 2)


def detect_burnout(data):
    payload = _as_dict(data)
    hours = payload.get("working_hours", 0)
    productivity = calculate_productivity(payload)
    if hours > 10 or (hours > 9 and productivity < 45):
        return "High Risk"
    if hours > 8 or productivity < 55:
        return "Medium Risk"
    return "Low Risk"


def predict_delay(data):
    payload = _as_dict(data)
    progress = payload.get("task_progress", 0)
    days_left = payload.get("days_left", 0)
    if progress < 50 and days_left < 3:
        return "High Risk"
    if progress < 70:
        return "Medium Risk"
    return "Low Risk"


def analyze_attendance_pattern(data):
    payload = _as_dict(data)
    late_arrivals = payload.get("late_arrivals", 0)
    absent_days = payload.get("absent_days", 0)
    if late_arrivals >= 4 or absent_days >= 3:
        return "Irregular"
    if late_arrivals >= 2 or absent_days >= 1:
        return "Needs Monitoring"
    return "Regular"


def adaptive_productivity_benchmark(current_productivity: float, history):
    if not history:
        return {
            "status": "Insufficient Data",
            "z_score": 0.0,
            "baseline_mean": round(current_productivity, 2),
            "baseline_std": 0.0,
            "sample_count": 0,
            "message": "No historical productivity records available yet.",
        }

    scores = [point.productivity_score for point in history]
    baseline_mean = _mean(scores)
    baseline_std = _std(scores, baseline_mean)
    sample_count = len(scores)
    z_score = 0.0 if baseline_std == 0 else (current_productivity - baseline_mean) / baseline_std

    if sample_count < 5:
        status = "Warm-up"
        message = "Collect more history for stable personalized baseline."
    elif z_score <= -1.5:
        status = "Decline"
        message = "Performance is lower than personal baseline."
    elif z_score >= 1.5:
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


def detect_work_anomaly(data, productivity, history):
    payload = _as_dict(data)
    reasons = []
    severity = "Low"

    working_hours = payload.get("working_hours", 0)
    idle_hours = payload.get("idle_hours", 0)

    if working_hours >= 11:
        reasons.append("Excessive daily working hours")
    if idle_hours >= 6:
        reasons.append("Unusually high idle hours")
    if productivity <= 30:
        reasons.append("Sudden productivity drop")

    if history:
        historical_scores = [point.productivity_score for point in history]
        mean_val = _mean(historical_scores)
        std_val = _std(historical_scores, mean_val)
        if std_val > 0:
            z_score = (productivity - mean_val) / std_val
            if z_score <= -2:
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


def generate_recommendations(burnout, delay, attendance_pattern, anomaly_result, benchmark_result):
    recommendations = []
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
    if not recommendations:
        recommendations.append("Maintain current workflow and continue periodic monitoring.")
    return recommendations


def generate_summary(prod, burnout, delay, attendance_pattern, benchmark_status, anomaly_flag):
    if burnout == "High Risk":
        return "Employee shows high burnout risk and needs immediate workload intervention."
    if anomaly_flag:
        return "Employee behavior contains anomalies and requires closer managerial monitoring."
    if benchmark_status == "Decline":
        return "Employee is trending below personal baseline and may need support."
    if prod > 70 and delay == "Low Risk" and attendance_pattern == "Regular":
        return "Employee performance is strong and consistent."
    return "Employee performance is moderate; continue monitoring and coaching."