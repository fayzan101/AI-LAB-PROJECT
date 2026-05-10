from services.performance_ranking import compute_performance_ranking


def test_weighted_ranking_order():
    employees = [
        {
            "employee_id": "a",
            "productivity": 50,
            "task_completion": 50,
            "attendance": 50,
            "efficiency": 50,
            "collaboration": 50,
        },
        {
            "employee_id": "b",
            "productivity": 90,
            "task_completion": 90,
            "attendance": 90,
            "efficiency": 90,
            "collaboration": 90,
        },
        {
            "employee_id": "c",
            "productivity": 10,
            "task_completion": 10,
            "attendance": 10,
            "efficiency": 10,
            "collaboration": 10,
        },
        {
            "employee_id": "d",
            "productivity": 40,
            "task_completion": 40,
            "attendance": 40,
            "efficiency": 40,
            "collaboration": 40,
        },
    ]
    data, meta = compute_performance_ranking(employees)
    assert meta["cohort_size"] == 4
    ranks = {r["employee_id"]: r["rank"] for r in data["rankings"]}
    assert ranks["b"] == 1
    assert ranks["c"] == 4
    assert "b" in data["top_performer_ids"]
    assert "c" in data["low_performer_ids"]
    assert "weighted_linear" in data["algorithms_used"]


def test_department_aggregate():
    employees = [
        {
            "employee_id": "u1",
            "department_id": "d1",
            "department_name": "Eng",
            "productivity": 80,
            "task_completion": 80,
            "attendance": 80,
            "efficiency": 80,
            "collaboration": 80,
        },
        {
            "employee_id": "u2",
            "department_id": "d1",
            "department_name": "Eng",
            "productivity": 60,
            "task_completion": 60,
            "attendance": 60,
            "efficiency": 60,
            "collaboration": 60,
        },
        {
            "employee_id": "u3",
            "department_id": "d2",
            "department_name": "Sales",
            "productivity": 20,
            "task_completion": 20,
            "attendance": 20,
            "efficiency": 20,
            "collaboration": 20,
        },
        {
            "employee_id": "u4",
            "department_id": "d2",
            "department_name": "Sales",
            "productivity": 30,
            "task_completion": 30,
            "attendance": 30,
            "efficiency": 30,
            "collaboration": 30,
        },
    ]
    data, _ = compute_performance_ranking(employees)
    depts = {d["department_name"]: d for d in data["departments"]}
    assert depts["Eng"]["rank"] == 1
    assert depts["Sales"]["rank"] == 2
