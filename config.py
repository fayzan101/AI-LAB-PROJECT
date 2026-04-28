import os
from dataclasses import dataclass
def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Employee Analytics System")
    env: str = os.getenv("ENV", "development")
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-this-secret-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_issuer: str = os.getenv("JWT_ISSUER", "remote-work-ai-server")
    jwt_audience: str = os.getenv("JWT_AUDIENCE", "remote-work-portal")
    token_exp_seconds: int = int(os.getenv("TOKEN_EXP_SECONDS", "3600"))
    service_client_id: str = os.getenv("SERVICE_CLIENT_ID", "portal-backend")
    service_client_secret: str = os.getenv("SERVICE_CLIENT_SECRET", "change-me")
    default_scope: str = os.getenv("DEFAULT_SCOPE", "analytics:write analytics:read")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///employee_analytics.db")

    # Security hardening
    cors_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()
    )
    trust_proxy_headers: bool = _to_bool(os.getenv("TRUST_PROXY_HEADERS"), default=False)
    # Rate limiting
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    rate_limit_max_requests: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "120"))
    redis_url: str | None = os.getenv("REDIS_URL")


settings = Settings()
