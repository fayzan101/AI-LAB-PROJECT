from fastapi import HTTPException, status

from database import get_idempotent_response, save_idempotent_response
def get_cached_response(
    tenant_id: str,
    endpoint: str,
    idempotency_key: str | None,
    request_payload: dict,
) -> dict | None:
    if not idempotency_key:
        return None
    try:
        return get_idempotent_response(
            tenant_id=tenant_id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


def store_response(
    tenant_id: str,
    endpoint: str,
    idempotency_key: str | None,
    request_payload: dict,
    response_payload: dict,
    status_code: int = status.HTTP_200_OK,
) -> None:
    if not idempotency_key:
        return
    save_idempotent_response(
        tenant_id=tenant_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_payload=request_payload,
        response_payload=response_payload,
        status_code=status_code,
    )
