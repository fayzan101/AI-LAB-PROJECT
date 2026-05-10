# AI Server — Functionality Summaries (10 lines each) + Code Notes

Each block below has **ten short lines** summarizing what the feature does for the product, then a **code explanation** tied to the real implementation files.

---

## 1. FastAPI application shell (`main.py`)

1. Builds the FastAPI app with a description of how the portal backend should use it.
2. Registers all route modules under a configurable URL prefix (default `/api/v1`).
3. Adds CORS so allowed browser origins can call the API when needed (primary client is still the backend).
4. On startup, runs database initialization so tables and migrations exist before traffic.
5. HTTP middleware assigns a trace/request id, applies rate limits, and logs each request.
6. Exempt paths skip rate limiting: health, login, metrics, and root.
7. Global handlers normalize validation errors, HTTP errors, and uncaught exceptions into one JSON shape.
8. Exposes simple liveness, readiness (DB + startup flag), and startup status for orchestrators.
9. Serves Prometheus metrics for monitoring.
10. Root route returns a minimal “service is running” message.

**Code explanation:** The app wires routers, stores a `RateLimiter` on `app.state`, and runs `init_db()` in `on_startup`. Middleware calls `request_context_middleware`, then `is_limited` for non-exempt paths, then `observe_request` and `log_request` after `call_next`. Exception handlers always include `error_code` and `trace_id` for clients.

```29:102:ai-server/main.py
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=APP_DESCRIPTION,
    ...
)
...
@app.middleware("http")
async def request_logging_and_rate_limit(request: Request, call_next):
    start = time.perf_counter()
    request_context_middleware(request)
    path = request.url.path
    exempt_paths = {"/", "/health/live", "/health/ready", "/health/startup", f"{settings.api_prefix}/auth/login", "/metrics"}
    if path not in exempt_paths:
        ...
        if app.state.rate_limiter.is_limited(client_ip):
            return JSONResponse(...)
    response = await call_next(request)
    ...
    observe_request(request.method, path, response.status_code, duration_seconds)
    log_request(...)
    return response
```

---

## 2. Environment configuration (`config.py`)

1. Loads all tunable settings from process environment variables with safe defaults for local dev.
2. Centralizes JWT signing parameters: secret, algorithm, issuer, audience, and token lifetime.
3. Defines the expected service client id/secret pair used at login.
4. Sets default OAuth-like scopes granted in tokens unless the login request overrides them.
5. Chooses database URL (SQLite by default; Postgres in production).
6. Parses CORS origins from a comma-separated string into a tuple.
7. Configures rate limit window size and max hits per client per window.
8. Optionally points rate limiting at Redis for multi-instance deployments.
9. Gates optional ML with boolean and path/version fields for training-serving alignment.
10. Exposes a single frozen `settings` object imported everywhere else.

**Code explanation:** `Settings` is a `@dataclass(frozen=True)` so values are immutable after creation. `_to_bool` normalizes strings like `"1"`/`"true"` for flags. This keeps secrets and URLs out of source code and matches 12-factor style configuration.

```7:39:ai-server/config.py
@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Employee Analytics System")
    ...
    jwt_secret: str = os.getenv("JWT_SECRET", "change-this-secret-in-production")
    ...
    service_client_id: str = os.getenv("SERVICE_CLIENT_ID", "portal-backend")
    service_client_secret: str = os.getenv("SERVICE_CLIENT_SECRET", "change-me")
    ...
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///employee_analytics.db")
    ...
    redis_url: str | None = os.getenv("REDIS_URL")
    ai_ml_enabled: bool = _to_bool(os.getenv("AI_ML_ENABLED"), default=False)
    ...
settings = Settings()
```

---

## 3. Database access and persistence (`database.py`)

1. Creates one shared SQLAlchemy `engine` from `DATABASE_URL`.
2. Delegates schema creation/upgrade to `run_migrations()` on startup.
3. Saves employee snapshots into `employee_inputs`, including a JSON column for telemetry extras.
4. Saves task progress rows into `task_inputs`.
5. Persists full analytics reports as JSON plus denormalized risk/score columns for filtering.
6. Fetches recent reports per tenant and employee, newest first, with a limit.
7. Implements idempotent replay: hash request body, lookup key, return stored response or conflict.
8. Stores successful idempotent responses after writes for later retries.
9. Probes the database with `SELECT 1` for readiness checks used by `/health/ready`.
10. Uses raw SQL with bound parameters to avoid string concatenation SQL injection.

**Code explanation:** `_employee_extra_json` copies only known telemetry keys into `extra_json` so the table schema stays stable. `get_idempotent_response` compares `sha256` of canonical JSON (`sort_keys=True`) so the same logical payload always matches; a different payload with the same key raises `ValueError` (mapped to HTTP 409 in the route layer).

```34:66:ai-server/database.py
def save_employee_input(payload: dict[str, Any]) -> int:
    row_payload = {
        "tenant_id": payload["tenant_id"],
        ...
        "extra_json": _employee_extra_json(payload),
    }
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO employee_inputs (...)
                ...
                RETURNING id
                """
            ),
            row_payload,
        ).first()
    return int(row[0])
```

```146:168:ai-server/database.py
def get_idempotent_response(...) -> dict[str, Any] | None:
    request_hash = sha256(json.dumps(request_payload, sort_keys=True).encode()).hexdigest()
    ...
    if row["request_hash"] != request_hash:
        raise ValueError("Idempotency key already used with a different request payload")
    return {"status_code": row["status_code"], "body": json.loads(row["response_json"])}
```

---

## 4. Schema migrations (`db_migrations.py`)

1. Runs SQL migration files from the `migrations/` directory in sorted filename order.
2. Tracks applied versions in a `schema_migrations` table so each file runs once.
3. Splits each `.sql` file on semicolons and executes non-empty statements in one transaction per file.
4. Handles a SQLite dev edge case: drops legacy tables if `employee_inputs` exists without `tenant_id`.
5. Keeps local SQLite databases compatible when the project added multi-tenant columns.
6. Uses the same `DATABASE_URL` engine as the rest of the app.
7. Is invoked from `init_db()` during application startup.
8. Allows additive changes by adding new numbered SQL files without editing Python.
9. Fails fast if SQL is invalid (startup error surfaces misconfiguration early).
10. Works for both SQLite and Postgres dialects for the supported SQL written in files.

**Code explanation:** The loop `for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql"))` guarantees deterministic order (`001_...`, `002_...`). Each version string is the stem of the filename; inserts into `schema_migrations` mark completion.

```11:48:ai-server/db_migrations.py
def run_migrations() -> None:
    with engine.begin() as conn:
        dialect = conn.engine.dialect.name
        if dialect == "sqlite":
            ...
        conn.execute(text("""CREATE TABLE IF NOT EXISTS schema_migrations (...)"""))
        applied_rows = conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
        applied_versions = {row[0] for row in applied_rows}
        for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = migration_file.stem
            if version in applied_versions:
                continue
            ...
            conn.execute(text("INSERT INTO schema_migrations (version) VALUES (:version)"), {"version": version})
```

---

## 5. JWT authentication and authorization (`security.py`)

1. Issues signed JWT access tokens after successful service login.
2. Embeds subject, tenant id, scopes, issuer, audience, issued-at, and expiry in the payload.
3. Verifies tokens on protected routes: signature, expiry, issuer, and audience must match settings.
4. Requires `tenant_id` inside the token or validation fails (multi-tenant safety).
5. Exposes `require_auth` as a FastAPI dependency that reads the `Authorization: Bearer` header.
6. Exposes `require_scope` to enforce fine-grained permission strings per endpoint.
7. Compares login `client_id`/`client_secret` to configured service credentials (single trusted client by default).
8. Maps PyJWT errors to HTTP 401 with a clear message for callers.
9. Uses HS256 by default (symmetric key shared between issuer and verifier).
10. Keeps all crypto parameters in `settings` so environments can rotate secrets independently.

**Code explanation:** `HTTPBearer(auto_error=False)` allows returning a custom 401 when the header is missing. `verify_token` uses `jwt.decode` with `audience` and `issuer` to prevent token reuse from wrong services.

```13:72:ai-server/security.py
def create_access_token(subject: str, tenant_id: str, scopes: list[str] | None = None, ...) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "scope": " ".join(scopes or settings.default_scope.split()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        ...
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
...
def require_scope(token_payload: dict[str, Any], required_scope: str) -> None:
    token_scopes = set(str(token_payload.get("scope", "")).split())
    if required_scope not in token_scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, ...)
```

---

## 6. Service login route (`routes/auth.py`)

1. Accepts `client_id`, `client_secret`, `tenant_id`, and optional `scopes` in JSON.
2. Rejects invalid credentials with HTTP 401 before any token is minted.
3. On success, returns an `ApiEnvelope` with `access_token`, `token_type`, and `expires_in`.
4. Does not expose user passwords; this is machine-to-machine authentication.
5. Lets callers request specific scopes (still subject to what the backend allows in practice).
6. Uses Pydantic `Field` constraints so empty strings cannot be sent for ids/secrets.
7. Is the only write path that skips bearer auth (it establishes auth instead).
8. Is listed in middleware exempt paths so login is not rate-limited the same as bulk analytics (still protect via network policy in prod).
9. Returns a stable JSON envelope shape consistent with other routes.
10. Acts as the front door for the Node portal to obtain a JWT for all other calls.

**Code explanation:** `authenticate_service_client` is a constant-time string compare pattern would be ideal for production; here it uses simple equality against settings. `create_access_token` ties the token to the tenant chosen at login time.

```17:31:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/routes/auth.py
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
        data={"access_token": token, "token_type": "bearer", "expires_in": 3600},
    )
```

---

## 7. Employee data ingest (`routes/employee.py`)

1. Receives validated employee metrics plus optional telemetry fields in one POST body.
2. Requires a valid bearer token and the `analytics:write` scope.
3. Ensures JWT `tenant_id` equals payload `tenant_id` to prevent cross-tenant writes.
4. Supports `Idempotency-Key` header to safely retry the same ingest without duplicate rows.
5. Returns cached envelope immediately if the same key and body were seen before.
6. Persists via `save_employee_input` and returns the new `record_id` in `meta`.
7. Stores telemetry scalars inside `extra_json` at the database layer for forward compatibility.
8. Uses the shared `ApiEnvelope` response type for consistent client parsing.
9. Fails with standardized validation errors if numeric fields violate min/max rules from schemas.
10. Feeds downstream analytics when the portal aggregates snapshots into report requests.

**Code explanation:** The route composes three cross-cutting concerns: auth (`Depends(require_auth)`), tenant check, and idempotency (`get_cached_response` / `store_response`).

```13:42:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/routes/employee.py
@router.post("/employee/data")
def receive_employee(
    data: EmployeeInput,
    token_payload: dict[str, Any] = Depends(require_auth),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ApiEnvelope:
    require_scope(token_payload, "analytics:write")
    if token_payload["tenant_id"] != data.tenant_id:
        raise HTTPException(...)
    payload = data.model_dump()
    cached = get_cached_response(data.tenant_id, "/employee/data", idempotency_key, payload)
    if cached:
        return ApiEnvelope(**cached["body"])
    record_id = save_employee_input(payload)
    ...
```

---

## 8. Task progress ingest (`routes/tasks.py`)

1. Accepts per-task progress percentage, days remaining, and identifiers for tenant/employee/task.
2. Requires bearer auth and `analytics:write` like employee ingest.
3. Enforces tenant match between token and body to isolate customers.
4. Supports idempotent POST semantics via `Idempotency-Key` for reliable workers.
5. Validates `progress_percent` is between 0 and 100 using Pydantic constraints.
6. Persists rows in `task_inputs` for auditing and future model features.
7. Returns the inserted payload echo plus `record_id` metadata.
8. Uses a small local `TaskInput` model separate from `EmployeeInput` for clarity.
9. Shares the same caching pattern as employee and analytics routes.
10. Aligns field names (`days_left`) with what the AI engine expects in analytics payloads.

**Code explanation:** `TaskInput` is defined in this module rather than `schemas.py` (minor organizational choice); validation still runs before DB insert.

```22:40:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/routes/tasks.py
@router.post("/tasks")
def receive_task(
    data: TaskInput,
    token_payload: dict[str, Any] = Depends(require_auth),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ApiEnvelope:
    require_scope(token_payload, "analytics:write")
    ...
    record_id = save_task_input(payload)
    response = ApiEnvelope(
        message="Task data received",
        data=payload,
        meta={"record_id": record_id},
    )
```

---

## 9. Analytics report generation (`routes/analytics.py`)

1. Accepts the same employee-like fields as ingest plus optional `history` baseline points.
2. Requires `analytics:write` and matching tenant id in token and body.
3. Applies idempotency so duplicate report jobs return the same envelope.
4. Calls `build_full_report` to compute all rule-based metrics and narratives.
5. Wraps nested dicts into `BenchmarkResult` and `AnomalyResult` for response typing.
6. Builds a full `ReportResponse` including telemetry quality and presence labels.
7. Optionally calls `maybe_ml_scores` and attaches results under `meta["ml"]` without failing the request.
8. Saves the report JSON to `analytics_reports` and returns `report_id` in `meta`.
9. Returns everything inside `ApiEnvelope` for uniform API design.
10. Is the main “AI insight” endpoint product dashboards depend on.

**Code explanation:** History is passed straight into the engine for z-score benchmarking. ML is strictly additive: `maybe_ml_scores` returns `None` when disabled or broken.

```14:75:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/routes/analytics.py
@router.post("/analytics/report")
def full_report(
    data: AnalyticsReportRequest,
    token_payload: dict[str, Any] = Depends(require_auth),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ApiEnvelope:
    require_scope(token_payload, "analytics:write")
    ...
    report_dict = build_full_report(
        payload,
        tenant_id=data.tenant_id,
        employee_id=data.employee_id,
        history=history,
    )
    ...
    ml_meta = maybe_ml_scores(payload)
    meta: dict[str, Any] = {"history_points_used": len(history), "report_id": save_analytics_report(report.model_dump())}
    if ml_meta is not None:
        meta["ml"] = ml_meta
```

---

## 10. Historical reports retrieval (`routes/reports.py`)

1. Provides read-only access to previously saved analytics reports for one employee.
2. Requires bearer auth and the `analytics:read` scope (write is not needed to query history).
3. Accepts `tenant_id` as a query parameter and compares it to the JWT tenant claim.
4. Supports a `limit` parameter (bounded min/max) for how many recent reports to return.
5. Returns count of rows found, the latest report object, and the full ordered history list.
6. Uses `get_recent_reports` which orders by primary key descending (newest first).
7. Helps dashboards show trends without recomputing old reports.
8. Returns an empty-friendly structure when no analytics rows exist yet.
9. Uses GET semantics (safe, cacheable in principle) unlike ingest POST endpoints.
10. Completes the write/read split for analytics data lifecycle.

**Code explanation:** The path parameter is `employee_id`; tenant scoping is explicit in query string to match how some gateways cache URLs.

```12:36:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/routes/reports.py
@router.get("/reports/weekly/{employee_id}")
def weekly_report(
    employee_id: str,
    tenant_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=7, ge=1, le=30),
    token_payload: dict[str, Any] = Depends(require_auth),
) -> ApiEnvelope:
    require_scope(token_payload, "analytics:read")
    if token_payload["tenant_id"] != tenant_id:
        raise HTTPException(...)
    reports = get_recent_reports(tenant_id=tenant_id, employee_id=employee_id, limit=limit)
    ...
```

---

## 11. Idempotency helper (`idempotency.py`)

1. Bridges HTTP headers and database-backed deduplication for mutating routes.
2. If no `Idempotency-Key` is provided, behaves as a no-cache pass-through (returns `None`).
3. Delegates lookup to `get_idempotent_response` which enforces body hash equality.
4. Converts hash conflicts into HTTP 409 via `HTTPException` for API clarity.
5. `store_response` only persists when a key is present, avoiding empty inserts.
6. Associates records with tenant id and logical endpoint string for isolation.
7. Lets clients retry after timeouts without creating duplicate analytics or ingests.
8. Encourages keys to be unique per logical operation id from the caller.
9. Stores full JSON response bodies so replay is byte-identical for the client.
10. Centralizes error translation (`ValueError` → 409) once for all routes.

**Code explanation:** Routes pass a stable endpoint constant like `"/analytics/report"` so the same key can be reused on different endpoints without collision in the composite unique key.

```4:44:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/idempotency.py
def get_cached_response(...) -> dict | None:
    if not idempotency_key:
        return None
    try:
        return get_idempotent_response(...)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
...
def store_response(...) -> None:
    if not idempotency_key:
        return
    save_idempotent_response(...)
```

---

## 12. Request and response schemas (`schemas.py`)

1. Defines `EmployeeInput` columns and optional telemetry fields with validation ranges.
2. Defines `BaselinePoint` for historical productivity samples used in benchmarking.
3. Extends employee input into `AnalyticsReportRequest` by adding a `history` list.
4. Models nested report parts: `BenchmarkResult`, `AnomalyResult`, and full `ReportResponse`.
5. Standardizes the success wrapper `ApiEnvelope` used across routes.
6. Includes `ErrorEnvelope` shape documentation for clients (errors still built manually in handlers).
7. Uses `Optional` fields where newer report fields may be absent for backward compatibility.
8. Enforces string length limits on tenant ids to reduce abuse and oversized rows.
9. Ensures percentages and non-negative counters are impossible to accept if invalid.
10. Acts as the contract between FastAPI, OpenAPI docs, and the Node proxy.

**Code explanation:** Subclassing `EmployeeInput` for `AnalyticsReportRequest` reuses all field definitions and avoids duplication drift.

```7:36:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/schemas.py
class EmployeeInput(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    employee_id: str = Field(..., min_length=1, max_length=64)
    ...
    active_seconds: Optional[int] = Field(default=None, ge=0)
    ...
class AnalyticsReportRequest(EmployeeInput):
    history: List[BaselinePoint] = Field(default_factory=list)
```

---

## 13. Stable machine-readable error codes (`errors.py`)

1. Maps common HTTP status codes to short uppercase `error_code` strings.
2. Lets frontend and automation handle failures without parsing free-text messages.
3. Covers 400, 401, 403, 404, 409, 422, 429, and 500 explicitly.
4. Falls back to `UNKNOWN_ERROR` for unlisted statuses to stay defensive.
5. Is imported by middleware and exception handlers in `main.py`.
6. Keeps error semantics consistent between validation and business logic errors.
7. Complements `trace_id` which correlates logs to user-visible responses.
8. Avoids leaking stack traces in JSON (handled separately for 500).
9. Is tiny on purpose: one dictionary and one accessor function.
10. Improves interoperability with API gateways that classify traffic by error class.

**Code explanation:** `get_error_code` is a single lookup used when building `JSONResponse` content.

```4:17:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/errors.py
ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    ...
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
}
def get_error_code(status_code: int) -> str:
    return ERROR_CODES.get(status_code, "UNKNOWN_ERROR")
```

---

## 14. Rate limiting (`rate_limit.py`)

1. Implements a fixed time window counter per logical client key (here: IP string).
2. Uses Redis `INCR` with TTL when `redis_url` is configured for distributed deployments.
3. Falls back to an in-memory deque per key that drops timestamps outside the window.
4. Returns `True` from `is_limited` when the client has exceeded `max_requests` in the window.
5. Prevents abusive bursts from starving CPU or database connections.
6. Is constructed once on app startup and reused for all requests.
7. Redis key includes the current window bucket: `rate_limit:{client}:{window_index}`.
8. In-memory path simulates sliding behavior by popping old timestamps.
9. Depends on accurate client IP extraction at the middleware layer.
10. Trades perfect global accuracy for simplicity (good enough for service-to-service).

**Code explanation:** When `count == 1` after `INCR`, `expire` sets the key lifetime to the window seconds so counts reset automatically.

```7:29:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/rate_limit.py
class RateLimiter:
    def __init__(self, window_seconds: int, max_requests: int, redis_url: str | None = None) -> None:
        ...
        self.redis = Redis.from_url(redis_url, decode_responses=True) if redis_url else None
        self.in_memory_hits: dict[str, deque[int]] = defaultdict(deque)

    def is_limited(self, client_id: str) -> bool:
        now = int(time.time())
        if self.redis:
            key = f"rate_limit:{client_id}:{now // self.window_seconds}"
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, self.window_seconds)
            return count > self.max_requests
        ...
```

---

## 15. Logging and Prometheus metrics (`observability.py`)

1. Stores a per-request id in a `ContextVar` so async handlers can read it safely.
2. Accepts incoming `x-request-id` or generates a UUID for distributed tracing.
3. Attaches the id to `request.state` for exception handlers.
4. Emits structured JSON logs with method, path, status, duration, and trace id.
5. Declares a Prometheus `Counter` labeled by method/path/status.
6. Declares a `Histogram` for latency labeled by method/path.
7. Exposes `metrics_response()` using `generate_latest()` for scraping.
8. Configures a single StreamHandler logger named `ai-server`.
9. Keeps log formatting machine-parseable (one JSON object per line).
10. Separates observability from business logic so routes stay thin.

**Code explanation:** `observe_request` increments counters and records histogram observation after the response is known.

```11:64:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/observability.py
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "path", "status_code"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request duration in seconds", ["method", "path"])
...
def request_context_middleware(request: Request):
    header_request_id = request.headers.get("x-request-id", "").strip()
    request_id = header_request_id or str(uuid.uuid4())
    request_id_ctx.set(request_id)
    request.state.request_id = request_id
...
def observe_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    REQUEST_COUNT.labels(method=method, path=path, status_code=str(status_code)).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration_seconds)
```

---

## 16. Rule-based analytics engine (`services/ai_engine.py`)

1. Converts employee/task/telemetry scalars into a single structured “full report” dictionary.
2. Computes a clamped productivity score using tasks, attendance, idle time, and optional telemetry ratio.
3. Classifies burnout risk using hours, productivity, and idle share heuristics.
4. Classifies schedule slip risk from task progress versus days left.
5. Labels attendance patterns from late/absent counts and optional first-seen offsets.
6. Builds a personal z-score benchmark when enough history exists; otherwise “Warm-up”.
7. Flags anomalies with reasons and escalates severity when multiple signals align.
8. Labels telemetry as `sparse` or `sufficient` to warn dashboards about data quality.
9. Derives human-readable summary text and actionable recommendation bullets.
10. Exposes `build_full_report` as the single orchestrator used by the analytics route.

**Code explanation:** `build_full_report` is pure Python: no I/O, easy to unit test. Telemetry boosts/penalties run only when `has_telemetry_extras` and enough seconds accrue.

```270:317:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/services/ai_engine.py
def build_full_report(
    payload: Mapping[str, Any],
    *,
    tenant_id: str,
    employee_id: str,
    history: list[Any],
) -> dict[str, Any]:
    productivity = calculate_productivity(payload)
    burnout = detect_burnout(payload)
    delay = predict_delay(payload)
    attendance_pattern = analyze_attendance_pattern(payload)
    benchmark = adaptive_productivity_benchmark(productivity, history)
    anomaly = detect_work_anomaly(payload, productivity, history)
    signal_quality = classify_telemetry_signal_quality(payload)
    presence = classify_presence_consistency(attendance_pattern)
    summary = generate_summary(...)
    recommendations = generate_recommendations(...)
    return {
        "tenant_id": tenant_id,
        "employee_id": employee_id,
        "productivity_score": productivity,
        ...
    }
```

---

## 17. Optional ML inference (`services/ml_scorer.py`)

1. Lazily loads a scikit-learn model saved with `joblib` only once per process.
2. Honors `AI_ML_ENABLED` and `AI_ML_MODEL_PATH`; skips cleanly when unset or file missing.
3. Builds `build_feature_vector_v1` in a fixed order matching training-time features.
4. Converts seconds-based telemetry into hour floats consistently with the rule engine.
5. Returns `None` when ML is unavailable so HTTP handlers ignore it without error.
6. On success, returns metadata like path, model version, and feature schema version.
7. Adds `prediction` and optional `predict_proba` arrays for classifiers that support them.
8. Catches load and predict exceptions and surfaces them as structured error dicts instead of crashing.
9. Uses module-level globals `_model` and `_load_attempted` to avoid reloading on every request.
10. Keeps ML as supplemental `meta.ml` rather than replacing core report fields.

**Code explanation:** `_ensure_model` sets `_load_attempted` so failed loads are not retried every request in a tight loop (still permanent until restart).

```43:87:F:/Desktop/Projects/Course/remote-work-tracker/ai-server/services/ml_scorer.py
def _ensure_model() -> None:
    global _model, _load_attempted, _load_meta
    if _load_attempted:
        return
    _load_attempted = True
    if not settings.ai_ml_enabled or not settings.ai_ml_model_path:
        _load_meta = {"skipped": True, "reason": "AI_ML_ENABLED or path unset"}
        return
    ...
def maybe_ml_scores(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    _ensure_model()
    if _model is None:
        return None
    x = [build_feature_vector_v1(payload)]
    ...
```

---

*File: `functunality.md` — summaries are intentionally ~10 lines per feature; line counts may wrap in editors but each numbered list is ten items.*
