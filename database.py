import json
from hashlib import sha256
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import settings
from db_migrations import run_migrations

engine: Engine = create_engine(settings.database_url, future=True)


def init_db() -> None:
    run_migrations()


def save_employee_input(payload: dict[str, Any]) -> int:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO employee_inputs (
                    tenant_id, employee_id, tasks_completed, attendance_days, idle_hours, working_hours,
                    task_progress, days_left, late_arrivals, absent_days
                )
                VALUES (
                    :tenant_id, :employee_id, :tasks_completed, :attendance_days, :idle_hours, :working_hours,
                    :task_progress, :days_left, :late_arrivals, :absent_days
                )
                RETURNING id
                """
            ),
            payload,
        ).first()
    return int(row[0])


def save_task_input(payload: dict[str, Any]) -> int:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO task_inputs (
                    tenant_id, employee_id, task_id, progress_percent, days_left
                )
                VALUES (
                    :tenant_id, :employee_id, :task_id, :progress_percent, :days_left
                )
                RETURNING id
                """
            ),
            payload,
        ).first()
    return int(row[0])


def save_analytics_report(report: dict[str, Any]) -> int:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO analytics_reports (
                    tenant_id, employee_id, report_json, productivity_score, burnout_risk, task_delay_risk
                )
                VALUES (
                    :tenant_id, :employee_id, :report_json, :productivity_score, :burnout_risk, :task_delay_risk
                )
                RETURNING id
                """
            ),
            {
                "tenant_id": report["tenant_id"],
                "employee_id": report["employee_id"],
                "report_json": json.dumps(report),
                "productivity_score": report["productivity_score"],
                "burnout_risk": report["burnout_risk"],
                "task_delay_risk": report["task_delay_risk"],
            },
        ).first()
    return int(row[0])


def get_recent_reports(tenant_id: str, employee_id: str, limit: int = 7) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, tenant_id, employee_id, report_json, productivity_score, burnout_risk, task_delay_risk, created_at
                FROM analytics_reports
                WHERE tenant_id = :tenant_id AND employee_id = :employee_id
                ORDER BY id DESC
                LIMIT :limit
                """
            ),
            {"tenant_id": tenant_id, "employee_id": employee_id, "limit": limit},
        ).mappings()

        reports: list[dict[str, Any]] = []
        for row in rows:
            report_data = json.loads(row["report_json"])
            reports.append(
                {
                    "id": row["id"],
                    "tenant_id": row["tenant_id"],
                    "employee_id": row["employee_id"],
                    "productivity_score": row["productivity_score"],
                    "burnout_risk": row["burnout_risk"],
                    "task_delay_risk": row["task_delay_risk"],
                    "created_at": str(row["created_at"]),
                    "report": report_data,
                }
            )
    return reports


def get_idempotent_response(
    tenant_id: str,
    endpoint: str,
    idempotency_key: str,
    request_payload: dict[str, Any],
) -> dict[str, Any] | None:
    request_hash = sha256(json.dumps(request_payload, sort_keys=True).encode()).hexdigest()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT request_hash, response_json, status_code
                FROM idempotency_keys
                WHERE tenant_id = :tenant_id AND endpoint = :endpoint AND idempotency_key = :idempotency_key
                """
            ),
            {"tenant_id": tenant_id, "endpoint": endpoint, "idempotency_key": idempotency_key},
        ).mappings().first()
    if not row:
        return None
    if row["request_hash"] != request_hash:
        raise ValueError("Idempotency key already used with a different request payload")
    return {"status_code": row["status_code"], "body": json.loads(row["response_json"])}


def save_idempotent_response(
    tenant_id: str,
    endpoint: str,
    idempotency_key: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    status_code: int,
) -> None:
    request_hash = sha256(json.dumps(request_payload, sort_keys=True).encode()).hexdigest()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO idempotency_keys (
                    tenant_id, endpoint, idempotency_key, request_hash, response_json, status_code
                )
                VALUES (
                    :tenant_id, :endpoint, :idempotency_key, :request_hash, :response_json, :status_code
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "endpoint": endpoint,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
                "response_json": json.dumps(response_payload),
                "status_code": status_code,
            },
        )


def is_db_ready() -> bool:
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
