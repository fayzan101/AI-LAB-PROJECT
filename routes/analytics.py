from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from database import save_analytics_report
from idempotency import get_cached_response, store_response
from services.ai_engine import (
    calculate_productivity,
    detect_burnout,
    predict_delay,
    generate_summary,
    analyze_attendance_pattern,
    adaptive_productivity_benchmark,
    detect_work_anomaly,
    generate_recommendations,
)
from schemas import AnalyticsReportRequest, ApiEnvelope, ReportResponse
from security import require_auth, require_scope

router = APIRouter()


@router.post("/analytics/report")
def full_report(
    data: AnalyticsReportRequest,
    token_payload: dict[str, Any] = Depends(require_auth),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ApiEnvelope:
    require_scope(token_payload, "analytics:write")
    if token_payload["tenant_id"] != data.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token tenant_id does not match payload tenant_id",
        )
    payload = data.model_dump()
    cached = get_cached_response(data.tenant_id, "/analytics/report", idempotency_key, payload)
    if cached:
        return ApiEnvelope(**cached["body"])
    history = data.history

    productivity = calculate_productivity(payload)
    burnout = detect_burnout(payload)
    delay = predict_delay(payload)
    attendance_pattern = analyze_attendance_pattern(payload)
    benchmark = adaptive_productivity_benchmark(productivity, history)
    anomaly = detect_work_anomaly(payload, productivity, history)
    summary = generate_summary(
        productivity,
        burnout,
        delay,
        attendance_pattern,
        benchmark["status"],
        anomaly["is_anomaly"],
    )
    recommendations = generate_recommendations(
        burnout,
        delay,
        attendance_pattern,
        anomaly,
        benchmark,
    )

    report = ReportResponse(
        tenant_id=data.tenant_id,
        employee_id=data.employee_id,
        productivity_score=productivity,
        burnout_risk=burnout,
        task_delay_risk=delay,
        attendance_pattern=attendance_pattern,
        adaptive_benchmark=benchmark,
        anomaly_detection=anomaly,
        summary=summary,
        recommendations=recommendations,
    )

    response = ApiEnvelope(
        message="Analytics report generated successfully",
        data=report.model_dump(),
        meta={
            "history_points_used": len(history),
            "report_id": save_analytics_report(report.model_dump()),
        },
    )
    store_response(
        tenant_id=data.tenant_id,
        endpoint="/analytics/report",
        idempotency_key=idempotency_key,
        request_payload=payload,
        response_payload=response.model_dump(),
    )
    return response