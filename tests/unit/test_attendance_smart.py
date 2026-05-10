from services.ai_engine import build_full_report
from services.attendance_smart import analyze_smart_attendance, build_attendance_feature_row


def test_smart_attendance_returns_category_and_score():
    out = analyze_smart_attendance(
        {
            "late_arrivals": 0,
            "absent_days": 0,
            "attendance_days": 20,
            "first_seen_offset_minutes": 10,
            "last_seen_offset_minutes": 30,
        },
        [],
    )
    assert "attendance_category" in out
    assert "reliability_score" in out
    assert 0 <= out["reliability_score"] <= 100
    assert out["kmeans_cluster_id"] in {0, 1, 2, 3}
    assert out["category_rank"] in {0, 1, 2, 3}
    assert out["algorithms_used"] == ["KMeans", "DecisionTreeRegressor"]
    assert "work_consistency" in out["features"]


def test_work_consistency_uses_history():
    history = [
        {"working_hours": 8, "idle_hours": 1, "productivity_score": 70, "date": "2026-01-01"},
        {"working_hours": 8.2, "idle_hours": 1, "productivity_score": 71, "date": "2026-01-02"},
        {"working_hours": 7.9, "idle_hours": 1, "productivity_score": 69, "date": "2026-01-03"},
    ]
    x = build_attendance_feature_row({"late_arrivals": 1, "absent_days": 0, "attendance_days": 15}, history)
    assert x.shape == (1, 7)
    assert x[0, 3] > 0.5  # consistency should be high with stable hours


def test_build_full_report_includes_smart_attendance():
    report = build_full_report(
        {
            "tasks_completed": 10,
            "attendance_days": 18,
            "idle_hours": 2,
            "working_hours": 8,
            "task_progress": 60,
            "days_left": 5,
            "late_arrivals": 1,
            "absent_days": 0,
        },
        tenant_id="t1",
        employee_id="e1",
        history=[],
    )
    assert "smart_attendance" in report
    assert report["smart_attendance"]["reliability_score"] >= 0
