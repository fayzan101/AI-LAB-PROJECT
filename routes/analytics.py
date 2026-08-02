from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from database import save_analytics_report
from idempotency import get_cached_response, store_response
from schemas import (
    AnalyticsReportRequest,
    ApiEnvelope,
    AnomalyResult,
    BenchmarkResult,
    DataQualityResult,
    ExplanationItem,
    PerformanceRankingRequest,
    ReportResponse,
    SmartAttendanceAnalysis,
)
from security import require_auth, require_scope
from services.ai_engine import build_full_report
from services.ml_scorer import maybe_ml_scores
from services.performance_ranking import compute_performance_ranking
from services.scoring_policy import RULE_ENGINE_VERSION

router = APIRouter(tags=["Analytics"])


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
    # JSON-serializable dict (history dates as strings) for idempotency hashing + ML extras
    payload = data.model_dump(mode="json")
    cached = get_cached_response(data.tenant_id, "/analytics/report", idempotency_key, payload)
    if cached:
        return ApiEnvelope(**cached["body"])
    history = data.history

    report_dict = build_full_report(
        payload,
        tenant_id=data.tenant_id,
        employee_id=data.employee_id,
        history=history,
    )
    benchmark = BenchmarkResult(**report_dict["adaptive_benchmark"])
    anomaly = AnomalyResult(**report_dict["anomaly_detection"])
    smart = SmartAttendanceAnalysis(**report_dict["smart_attendance"])
    dq = DataQualityResult(**report_dict["data_quality"]) if report_dict.get("data_quality") else None
    explanations = (
        [ExplanationItem(**item) for item in report_dict.get("explanations") or []]
        if report_dict.get("explanations") is not None
        else None
    )
    report = ReportResponse(
        tenant_id=report_dict["tenant_id"],
        employee_id=report_dict["employee_id"],
        productivity_score=report_dict["productivity_score"],
        burnout_risk=report_dict["burnout_risk"],
        task_delay_risk=report_dict["task_delay_risk"],
        attendance_pattern=report_dict["attendance_pattern"],
        adaptive_benchmark=benchmark,
        anomaly_detection=anomaly,
        summary=report_dict["summary"],
        recommendations=report_dict["recommendations"],
        telemetry_signal_quality=report_dict.get("telemetry_signal_quality"),
        presence_consistency=report_dict.get("presence_consistency"),
        smart_attendance=smart,
        rule_engine_version=report_dict.get("rule_engine_version") or RULE_ENGINE_VERSION,
        scoring_mode=report_dict.get("scoring_mode") or "rules",
        confidence=report_dict.get("confidence"),
        data_quality=dq,
        explanations=explanations,
        working_hours=report_dict.get("working_hours"),
        idle_hours=report_dict.get("idle_hours"),
        created_at=report_dict.get("created_at"),
    )

    # ML is additive metadata only — never replaces deterministic rule fields.
    ml_meta = maybe_ml_scores(payload)
    scoring_mode = "hybrid" if ml_meta and not ml_meta.get("error") and not ml_meta.get("skipped") else "rules"
    report.scoring_mode = scoring_mode
    if ml_meta and isinstance(ml_meta.get("model_version"), str):
        report.model_version = ml_meta["model_version"]
    meta: dict[str, Any] = {
        "history_points_used": len(history),
        "report_id": save_analytics_report(report.model_dump()),
        "rule_engine_version": report.rule_engine_version,
        "scoring_mode": scoring_mode,
        "confidence": report.confidence,
        "data_quality": report.data_quality.model_dump() if report.data_quality else None,
        "model_version": report.model_version,
    }
    if ml_meta is not None:
        meta["ml"] = ml_meta

    response = ApiEnvelope(
        message="Analytics report generated successfully",
        data=report.model_dump(),
        meta=meta,
    )
    store_response(
        tenant_id=data.tenant_id,
        endpoint="/analytics/report",
        idempotency_key=idempotency_key,
        request_payload=payload,
        response_payload=response.model_dump(),
    )
    return response


@router.post("/analytics/performance-ranking")
def performance_ranking(
    data: PerformanceRankingRequest,
    token_payload: dict[str, Any] = Depends(require_auth),
) -> ApiEnvelope:
    require_scope(token_payload, "analytics:write")
    if token_payload["tenant_id"] != data.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token tenant_id does not match payload tenant_id",
        )
    raw_employees = [e.model_dump(mode="json") for e in data.employees]
    result, extra_meta = compute_performance_ranking(raw_employees)
    return ApiEnvelope(
        message="Performance ranking computed",
        data=result,
        meta=extra_meta,
    )
