from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from database import get_recent_reports
from schemas import ApiEnvelope
from security import require_auth, require_scope

router = APIRouter()


@router.get("/reports/weekly/{employee_id}")
def weekly_report(
    employee_id: str,
    tenant_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=7, ge=1, le=30),
    token_payload: dict[str, Any] = Depends(require_auth),
) -> ApiEnvelope:
    require_scope(token_payload, "analytics:read")
    if token_payload["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token tenant_id does not match query tenant_id",
        )
    reports = get_recent_reports(tenant_id=tenant_id, employee_id=employee_id, limit=limit)
    latest = reports[0]["report"] if reports else None
    return ApiEnvelope(
        message="Weekly report fetched successfully",
        data={
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "reports_found": len(reports),
            "latest_report": latest,
            "history": reports,
        },
    )
