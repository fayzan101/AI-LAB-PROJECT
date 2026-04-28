import time
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(
    subject: str,
    tenant_id: str,
    scopes: list[str] | None = None,
    expires_in_seconds: int | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "scope": " ".join(scopes or settings.default_scope.split()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + (expires_in_seconds or settings.token_exp_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
        if not payload.get("tenant_id"):
            raise jwt.InvalidTokenError("Missing tenant_id claim")
        return payload
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        ) from exc


def authenticate_service_client(client_id: str, client_secret: str) -> bool:
    return client_id == settings.service_client_id and client_secret == settings.service_client_secret


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    return verify_token(credentials.credentials)


def require_scope(token_payload: dict[str, Any], required_scope: str) -> None:
    token_scopes = set(str(token_payload.get("scope", "")).split())
    if required_scope not in token_scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required scope: {required_scope}",
        )
