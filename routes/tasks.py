from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from database import save_task_input
from idempotency import get_cached_response, store_response
from schemas import ApiEnvelope
from security import require_auth, require_scope

router = APIRouter()


class TaskInput(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    employee_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    progress_percent: float = Field(..., ge=0, le=100)
    days_left: int = Field(..., ge=0)


@router.post("/tasks")
def receive_task(
    data: TaskInput,
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
    cached = get_cached_response(data.tenant_id, "/tasks", idempotency_key, payload)
    if cached:
        return ApiEnvelope(**cached["body"])
    record_id = save_task_input(payload)
    response = ApiEnvelope(
        message="Task data received",
        data=payload,
        meta={"record_id": record_id},
    )
    store_response(
        tenant_id=data.tenant_id,
        endpoint="/tasks",
        idempotency_key=idempotency_key,
        request_payload=payload,
        response_payload=response.model_dump(),
    )
    return response
