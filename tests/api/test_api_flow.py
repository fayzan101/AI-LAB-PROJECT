from fastapi.testclient import TestClient

from database import init_db
from main import app


client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    init_db()
    response = client.post(
        "/api/v1/auth/login",
        json={
            "client_id": "portal-backend",
            "client_secret": "change-me",
            "tenant_id": "tenant-1",
            "scopes": ["analytics:write", "analytics:read"],
        },
    )
    assert response.status_code == 200
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_success():
    response = client.post(
        "/api/v1/auth/login",
        json={
            "client_id": "portal-backend",
            "client_secret": "change-me",
            "tenant_id": "tenant-1",
            "scopes": ["analytics:write", "analytics:read"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "access_token" in body["data"]


def test_protected_route_requires_auth():
    response = client.post(
        "/api/v1/employee/data",
        json={
            "tenant_id": "tenant-1",
            "employee_id": "e-100",
            "tasks_completed": 0,
            "attendance_days": 0,
            "idle_hours": 0,
            "working_hours": 0,
            "task_progress": 0,
            "days_left": 0,
            "late_arrivals": 0,
            "absent_days": 0,
        },
    )
    assert response.status_code == 401


def test_employee_task_and_report_flow():
    headers = _auth_headers()

    employee_payload = {
        "tenant_id": "tenant-1",
        "employee_id": "emp-001",
        "tasks_completed": 8,
        "attendance_days": 5,
        "idle_hours": 2,
        "working_hours": 9,
        "task_progress": 65,
        "days_left": 2,
        "late_arrivals": 1,
        "absent_days": 0,
    }
    employee_response = client.post("/api/v1/employee/data", json=employee_payload, headers=headers)
    assert employee_response.status_code == 200
    assert employee_response.json()["meta"]["record_id"] > 0

    task_response = client.post(
        "/api/v1/tasks",
        json={
            "tenant_id": "tenant-1",
            "employee_id": "emp-001",
            "task_id": "task-xyz",
            "progress_percent": 70,
            "days_left": 3,
        },
        headers=headers,
    )
    assert task_response.status_code == 200
    assert task_response.json()["meta"]["record_id"] > 0

    report_response = client.post(
        "/api/v1/analytics/report",
        json={
            **employee_payload,
            "history": [
                {"date": "2026-04-20", "productivity_score": 68, "working_hours": 8, "idle_hours": 2},
                {"date": "2026-04-21", "productivity_score": 70, "working_hours": 8, "idle_hours": 2},
                {"date": "2026-04-22", "productivity_score": 72, "working_hours": 8, "idle_hours": 2},
                {"date": "2026-04-23", "productivity_score": 69, "working_hours": 8, "idle_hours": 2},
                {"date": "2026-04-24", "productivity_score": 71, "working_hours": 8, "idle_hours": 2},
            ],
        },
        headers=headers,
    )
    assert report_response.status_code == 200
    report_body = report_response.json()
    assert report_body["meta"]["report_id"] > 0
    assert "adaptive_benchmark" in report_body["data"]
    assert "anomaly_detection" in report_body["data"]

    weekly_response = client.get("/api/v1/reports/weekly/emp-001?limit=5&tenant_id=tenant-1", headers=headers)
    assert weekly_response.status_code == 200
    weekly_data = weekly_response.json()["data"]
    assert weekly_data["reports_found"] >= 1
