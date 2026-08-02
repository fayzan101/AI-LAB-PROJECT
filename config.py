import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///employee_analytics.db")
    # Neon/Vercel often set postgresql://; SQLAlchemy + psycopg3 needs this dialect.
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


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
    database_url: str = _database_url()

    # Security hardening
    cors_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()
    )
    trust_proxy_headers: bool = _to_bool(os.getenv("TRUST_PROXY_HEADERS"), default=False)
    # Rate limiting
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    rate_limit_max_requests: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "120"))
    redis_url: str | None = os.getenv("REDIS_URL")

    # Optional classical ML (e.g. scikit-learn joblib); disabled unless enabled + model path present
    ai_ml_enabled: bool = _to_bool(os.getenv("AI_ML_ENABLED"), default=False)
    ai_ml_model_path: str | None = os.getenv("AI_ML_MODEL_PATH") or None
    ai_ml_model_version: str = os.getenv("AI_ML_MODEL_VERSION", "none")
    ai_ml_feature_schema_version: str = os.getenv("AI_ML_FEATURE_SCHEMA_VERSION", "1")
    ai_ml_registry_dir: str = os.getenv("AI_ML_REGISTRY_DIR", "ml/registry")
    ai_ml_active_alias: str = os.getenv("AI_ML_ACTIVE_ALIAS", "production")
    ai_rule_engine_version: str = os.getenv("AI_RULE_ENGINE_VERSION", "1.0.0")


settings = Settings()
