from services.ai_engine import (
    adaptive_productivity_benchmark,
    analyze_attendance_pattern,
    calculate_productivity,
    detect_burnout,
    detect_work_anomaly,
    predict_delay,
)
from schemas import BaselinePoint


def test_calculate_productivity_normalized():
    score = calculate_productivity(
        {
            "tasks_completed": 20,
            "attendance_days": 20,
            "idle_hours": 4,
        }
    )
    assert 0 <= score <= 100


def test_detect_burnout_high_risk():
    risk = detect_burnout({"working_hours": 11, "tasks_completed": 2, "attendance_days": 1, "idle_hours": 8})
    assert risk == "High Risk"


def test_predict_delay_high_risk():
    risk = predict_delay({"task_progress": 40, "days_left": 1})
    assert risk == "High Risk"


def test_attendance_pattern_irregular():
    pattern = analyze_attendance_pattern({"late_arrivals": 4, "absent_days": 0})
    assert pattern == "Irregular"


def test_adaptive_benchmark_decline_status():
    history = [
        BaselinePoint(date="2026-04-01", productivity_score=72, working_hours=8, idle_hours=2),
        BaselinePoint(date="2026-04-02", productivity_score=70, working_hours=8, idle_hours=2),
        BaselinePoint(date="2026-04-03", productivity_score=71, working_hours=8, idle_hours=2),
        BaselinePoint(date="2026-04-04", productivity_score=73, working_hours=8, idle_hours=2),
        BaselinePoint(date="2026-04-05", productivity_score=72, working_hours=8, idle_hours=2),
    ]
    result = adaptive_productivity_benchmark(45, history)
    assert result["status"] == "Decline"


def test_detect_work_anomaly_flags_low_productivity():
    anomaly = detect_work_anomaly(
        {"working_hours": 11, "idle_hours": 7},
        productivity=20,
        history=[],
    )
    assert anomaly["is_anomaly"] is True
    assert anomaly["severity"] in {"Medium", "High"}
