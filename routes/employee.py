from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from database import save_employee_input
from idempotency import get_cached_response, store_response
from schemas import ApiEnvelope, EmployeeInput
from security import require_auth, require_scope

router = APIRouter()


@router.post("/employee/data")
def receive_employee(
    data: EmployeeInput,
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
    cached = get_cached_response(data.tenant_id, "/employee/data", idempotency_key, payload)
    if cached:
        return ApiEnvelope(**cached["body"])
    record_id = save_employee_input(payload)
    response = ApiEnvelope(
        message="Employee data received",
        data=payload,
        meta={"record_id": record_id},
    )
    store_response(
        tenant_id=data.tenant_id,
        endpoint="/employee/data",
        idempotency_key=idempotency_key,
        request_payload=payload,
        response_payload=response.model_dump(),
    )
    return response