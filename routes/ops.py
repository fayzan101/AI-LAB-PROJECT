"""Internal ops endpoints — ML health / DQ status (service JWT required)."""

from typing import Any

from fastapi import APIRouter, Depends

from schemas import ApiEnvelope
from security import require_auth, require_scope
from services.ml_scorer import ml_health
from services.scoring_policy import RULE_ENGINE_VERSION

router = APIRouter(tags=["Ops"])


@router.get("/ml/health")
def get_ml_health(token_payload: dict[str, Any] = Depends(require_auth)) -> ApiEnvelope:
    require_scope(token_payload, "analytics:read")
    return ApiEnvelope(
        message="ML health",
        data={
            "rule_engine_version": RULE_ENGINE_VERSION,
            "ml": ml_health(),
        },
        meta={"tenant_id": token_payload.get("tenant_id")},
    )
