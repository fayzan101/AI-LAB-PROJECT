from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from schemas import ApiEnvelope
from security import authenticate_service_client, create_access_token

router = APIRouter()


class LoginRequest(BaseModel):
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1, max_length=64)
    scopes: list[str] = Field(default_factory=lambda: ["analytics:write", "analytics:read"])


@router.post("/auth/login")
def login(data: LoginRequest) -> ApiEnvelope:
    if not authenticate_service_client(data.client_id, data.client_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service credentials",
        )

    token = create_access_token(subject=data.client_id, tenant_id=data.tenant_id, scopes=data.scopes)
    return ApiEnvelope(
        message="Login successful",
        data={
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 3600,
        },
    )
