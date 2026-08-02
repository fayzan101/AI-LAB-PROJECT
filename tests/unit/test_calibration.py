"""Golden calibration tests for deterministic rule engine."""

from services.ai_engine import (
    analyze_attendance_pattern,
    build_full_report,
    calculate_productivity,
    classify_telemetry_signal_quality,
    detect_burnout,
    predict_delay,
)
from services.scoring_policy import RULE_ENGINE_VERSION


BASE = {
    "tasks_completed": 10,
    "attendance_days": 5,
    "idle_hours": 1,
    "working_hours": 8,
    "task_progress": 80,
    "days_left": 5,
    "late_arrivals": 0,
    "absent_days": 0,
}


def test_rule_engine_version_present():
    report = build_full_report(BASE, tenant_id="t1", employee_id="e1", history=[])
    assert report["rule_engine_version"] == RULE_ENGINE_VERSION
    assert report["scoring_mode"] == "rules"
    assert 0.25 <= report["confidence"] <= 0.95
    assert report["data_quality"]["status"] in {"pass", "warn", "fail"}
    assert isinstance(report["explanations"], list)
    assert len(report["explanations"]) >= 3


def test_productivity_deterministic():
    a = calculate_productivity(BASE)
    b = calculate_productivity(BASE)
    assert a == b
    assert 0 <= a <= 100


def test_burnout_high_hours():
    assert detect_burnout({**BASE, "working_hours": 11}) == "High Risk"
    assert detect_burnout({**BASE, "working_hours": 6, "tasks_completed": 20, "idle_hours": 0}) == "Low Risk"


def test_delay_thresholds():
    assert predict_delay({**BASE, "task_progress": 40, "days_left": 2}) == "High Risk"
    assert predict_delay({**BASE, "task_progress": 60, "days_left": 5}) == "Medium Risk"
    assert predict_delay({**BASE, "task_progress": 90, "days_left": 5}) == "Low Risk"


def test_attendance_and_sparse_signal():
    assert analyze_attendance_pattern({**BASE, "late_arrivals": 0, "absent_days": 0}) == "Regular"
    assert analyze_attendance_pattern({**BASE, "late_arrivals": 4}) == "Irregular"
    sparse = classify_telemetry_signal_quality(
        {"working_hours": 0, "attendance_days": 0, "telemetry_days_with_data": 0}
    )
    assert sparse == "sparse"
    sufficient = classify_telemetry_signal_quality(
        {**BASE, "active_seconds": 10000, "idle_seconds": 1000, "segment_count": 20}
    )
    assert sufficient == "sufficient"


def test_sparse_lowers_confidence():
    full = build_full_report(
        {**BASE, "active_seconds": 20000, "idle_seconds": 2000, "segment_count": 30},
        tenant_id="t1",
        employee_id="e1",
        history=[{"productivity_score": 70, "working_hours": 8, "idle_hours": 1}] * 5,
    )
    sparse = build_full_report(
        {"tasks_completed": 0, "attendance_days": 0, "idle_hours": 0, "working_hours": 0, "task_progress": 0, "days_left": 0},
        tenant_id="t1",
        employee_id="e1",
        history=[],
    )
    assert sparse["confidence"] < full["confidence"]
    assert sparse["telemetry_signal_quality"] == "sparse"
