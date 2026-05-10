# AI Employee Analytics Service — Functionalities by Team Member

This document summarizes **what the project implements**, then divides responsibilities **evenly across three members**. Each section explains behavior in enough detail to use for coursework or handoff, with **concrete file references**.

**Project summary:** A **FastAPI** microservice that ingests employee and task snapshots (including optional **agent telemetry** scalars), runs **rule-based analytics** plus **optional classical ML** (scikit-learn / joblib), persists inputs and generated reports, and exposes **JWT-protected** JSON APIs for a portal backend (not browsers).

---

## Shared context (all members)

| Area | Role in the system |
|------|-------------------|
| **Stack** | Python, FastAPI, SQLAlchemy, Pydantic, PyJWT, Redis (optional), Prometheus client, scikit-learn, joblib |
| **Tenancy** | `tenant_id` on payloads must match the JWT claim on protected routes |
| **API prefix** | Routers are mounted under `API_PREFIX` (default `/api/v1`); see `config.py` → `settings.api_prefix` |
| **Entry point** | `main.py` — application instance, middleware, health routes, router includes |

---

## Member 1 — HTTP API, routing, and request/response contracts

**Focus:** Everything a client sees at the **HTTP boundary**: endpoints, validation shapes, success/error envelopes, idempotent retries from the API perspective, and **end-to-end API tests**.

### 1. FastAPI application shell and documentation metadata

The app is created with a description aimed at operators (portal proxies, no browser calls). **OpenAPI tags** group Authentication, Employees, Tasks, Analytics, Reports, Health, and Meta. Startup runs database initialization (migrations).

**Files:** `main.py` (FastAPI instance, `include_router`, `on_event("startup")`, OpenAPI `tags`)

### 2. Cross-cutting HTTP middleware (logging, rate limit gate, tracing header)

After assigning a **request context** (trace ID), non-exempt paths are **rate-limited** by client IP. Responses get `x-trace-id`. Duration and status feed **Prometheus** counters/histograms and **structured JSON logs**.

**Files:** `main.py` (middleware `request_logging_and_rate_limit`), `observability.py` (called from middleware), `rate_limit.py` (limiter implementation), `config.py` (rate limit and Redis settings)

### 3. Global exception handling and validation errors

Validation failures return **422** with `meta.errors`. `HTTPException` and uncaught exceptions return JSON bodies using a stable **`error_code`** string from the status.

**Files:** `main.py` (exception handlers), `errors.py` (`ERROR_CODES`, `get_error_code`)

### 4. Public and operational endpoints

- **Meta:** `GET /` — simple alive message  
- **Health:** `GET /health/live`, `/health/ready`, `/health/startup` — liveness, DB readiness after startup, startup flag  
- **Metrics:** `GET /metrics` — Prometheus scrape format  

**Files:** `main.py`, `database.py` (`is_db_ready` used by `/health/ready`), `observability.py` (`metrics_response`)

### 5. Authentication endpoint (orchestration)

`POST {prefix}/auth/login` accepts service credentials and tenant context, returns a **Bearer token** envelope on success.

**Files:** `routes/auth.py`, `schemas.py` (`ApiEnvelope`), `security.py` (called by route — token creation and credential check)

### 6. Employee data ingestion API

`POST {prefix}/employee/data` validates `EmployeeInput`, enforces scope `analytics:write` and **tenant match**, supports optional **`Idempotency-Key`** header, persists via database layer, returns `record_id` in `meta`.

**Files:** `routes/employee.py`, `schemas.py` (`EmployeeInput` — core fields + optional telemetry fields), `idempotency.py`, `database.py` (`save_employee_input`)

### 7. Task progress ingestion API

`POST {prefix}/tasks` validates task payload, same auth/tenant/idempotency pattern, persists task rows.

**Files:** `routes/tasks.py`, `idempotency.py`, `database.py` (`save_task_input`)

### 8. Full analytics report API (orchestration)

`POST {prefix}/analytics/report` builds the **full rule-engine report** via `build_full_report`, maps dict segments into `ReportResponse`, persists the report, attaches optional **`meta.ml`** from `maybe_ml_scores`, and caches response when idempotency key is present.

**Files:** `routes/analytics.py`, `schemas.py` (`AnalyticsReportRequest`, `ReportResponse`, `BenchmarkResult`, `AnomalyResult`, `SmartAttendanceAnalysis`), `services/ai_engine.py` (called), `services/ml_scorer.py` (`maybe_ml_scores`), `database.py` (`save_analytics_report`), `idempotency.py`

### 9. Performance ranking API (orchestration)

`POST {prefix}/analytics/performance-ranking` accepts a cohort with five 0–100 pillars per employee, returns rankings, department aggregates, weights, and algorithm metadata from `compute_performance_ranking`.

**Files:** `routes/analytics.py`, `schemas.py` (`PerformanceRankingRequest`, `RankingEmployeeMetric`), `services/performance_ranking.py` (called)

### 10. Weekly / historical report retrieval API

`GET {prefix}/reports/weekly/{employee_id}` with query `tenant_id` and optional `limit` returns recent stored reports and surfaces `latest_report` plus full `history`.

**Files:** `routes/reports.py`, `database.py` (`get_recent_reports`), `schemas.py` (`ApiEnvelope`)

### 11. Idempotency at the API layer

When `Idempotency-Key` is sent, the service returns the **same response body** for the same tenant, endpoint, key, and **request hash**; mismatched payload with same key yields **409**.

**Files:** `idempotency.py`, `database.py` (`get_idempotent_response`, `save_idempotent_response`)

### 12. API integration tests

Tests cover login, 401 on missing auth, employee → task → report → weekly flow (including telemetry-rich report), and performance ranking.

**Files:** `tests/api/test_api_flow.py`, `pytest.ini`, `main.py` / `database.py` (test client uses `init_db`)

---

## Member 2 — Security, configuration, reliability, and data persistence

**Focus:** **Who can call what**, **how settings are loaded**, **rate limiting and observability primitives**, and **all SQL-backed persistence** including migrations and telemetry storage.

### 1. Central configuration

Frozen `Settings` dataclass reads environment variables: app name, API prefix, JWT parameters, service client ID/secret, database URL, CORS origins, proxy trust flag, rate limit window/max, optional `REDIS_URL`, and optional ML flags (`AI_ML_ENABLED`, model path, versions).

**Files:** `config.py`, `.env.example` (documented examples for local/portal)

### 2. Service client authentication

Login validates `client_id` / `client_secret` against configured service credentials (shared secret for portal backend).

**Files:** `security.py` (`authenticate_service_client`), `routes/auth.py`

### 3. JWT issuance and verification

Access tokens embed `sub`, `tenant_id`, space-delimited `scope`, `iss`, `aud`, `iat`, `exp`. Verification enforces algorithm, secret, audience, issuer, and requires `tenant_id`.

**Files:** `security.py` (`create_access_token`, `verify_token`, `HTTPBearer` dependency)

### 4. Authorization: Bearer dependency and scopes

`require_auth` extracts Bearer token; `require_scope` ensures tokens include `analytics:write` or `analytics:read` as required by each route.

**Files:** `security.py`, all protected `routes/*.py` (via `Depends`)

### 5. Rate limiting implementation

`RateLimiter` supports **Redis-backed** fixed windows (if `REDIS_URL` set) or **in-memory** sliding behavior per client key; used from middleware for non-exempt paths.

**Files:** `rate_limit.py`, `main.py` (instantiation on `app.state.rate_limiter`), `config.py`

### 6. Observability: trace ID, structured logs, Prometheus

Request IDs come from `x-request-id` or a new UUID; logs are JSON lines; Prometheus `Counter` and `Histogram` record method, path, status, latency.

**Files:** `observability.py`, `main.py` (middleware)

### 7. Database engine and connectivity check

SQLAlchemy engine from `DATABASE_URL`; `is_db_ready()` runs `SELECT 1` for readiness probes.

**Files:** `database.py`, `db_migrations.py` (separate engine for migrations), `config.py`

### 8. Migration runner and schema versioning

On startup, `init_db()` runs `run_migrations()`: ensures `schema_migrations` table, applies ordered `.sql` files once each; **SQLite** dev path can drop legacy single-tenant tables if `tenant_id` column missing.

**Files:** `db_migrations.py`, `migrations/001_init.sql`, `migrations/002_employee_inputs_extra.sql`, `database.py` (`init_db`)

### 9. Relational schema (DDL)

Tables: `employee_inputs`, `task_inputs`, `analytics_reports`, `idempotency_keys` with indexes on tenant/employee/time where appropriate. `002` adds `extra_json` for telemetry snapshot.

**Files:** `migrations/001_init.sql`, `migrations/002_employee_inputs_extra.sql`

### 10. Employee persistence with telemetry extraction

`save_employee_input` inserts scalar columns and builds `extra_json` from a fixed allowlist of telemetry keys (`active_seconds`, `idle_seconds`, `telemetry_days_with_data`, `segment_count`, `focus_fragmentation_index`, `first_seen_offset_minutes`, `last_seen_offset_minutes`).

**Files:** `database.py` (`_employee_extra_json`, `save_employee_input`, `_TELEMETRY_EXTRA_KEYS`)

### 11. Task and analytics report persistence

Tasks: insert into `task_inputs`. Reports: insert full JSON blob plus denormalized `productivity_score`, `burnout_risk`, `task_delay_risk` for listing/filtering.

**Files:** `database.py` (`save_task_input`, `save_analytics_report`)

### 12. Historical report reads

`get_recent_reports` returns decoded `report_json` rows with metadata for weekly/history API.

**Files:** `database.py` (`get_recent_reports`)

### 13. Idempotency storage

Stores `request_hash` (SHA-256 of canonical JSON), response JSON, and HTTP status per `(tenant_id, endpoint, idempotency_key)`; retrieval detects payload mismatch.

**Files:** `database.py` (`get_idempotent_response`, `save_idempotent_response`), `idempotency.py` (HTTP mapping)

### 14. Error code catalog for clients

Maps HTTP statuses to stable machine-readable `error_code` strings used in JSON error envelopes.

**Files:** `errors.py`, `main.py` (handlers)

---

## Member 3 — Analytics rules, ML features, and automated tests for intelligence

**Focus:** **All scoring and insight logic**: rule engine, telemetry-aware signals, **smart attendance** (K-Means + decision tree), **cohort performance ranking** (weighted + optional Random Forest), **optional joblib model**, lightweight domain types, and **unit tests** for analytics.

### 1. Productivity scoring (tasks + attendance + idle, telemetry-aware)

Base score from tasks, attendance days, and idle hours (capped 0–100). If rich telemetry exists (`active_seconds` / `segment_count`), adjusts using **active/total time ratio** and optional **focus fragmentation** penalty.

**Files:** `services/ai_engine.py` (`calculate_productivity`, `_effective_active_idle_seconds`, `has_telemetry_extras`)

### 2. Burnout risk heuristic

Combines **working hours**, productivity, and **idle ratio** (from seconds if available) into Low / Medium / High Risk labels.

**Files:** `services/ai_engine.py` (`detect_burnout`)

### 3. Task delay risk (rule-based)

Uses `task_progress` and `days_left` thresholds for Low / Medium / High Risk.

**Files:** `services/ai_engine.py` (`predict_delay`)

### 4. Attendance pattern classification

Uses late arrivals and absent days; if telemetry present, **`first_seen_offset_minutes`** can escalate effective lateness. Outputs Regular / Needs Monitoring / Irregular.

**Files:** `services/ai_engine.py` (`analyze_attendance_pattern`)

### 5. Adaptive productivity benchmark (personal z-score)

From `history` baseline points, computes mean/std of past `productivity_score`, z-score for current productivity, and statuses: Insufficient Data, Warm-up, Decline, Stable, Improvement.

**Files:** `services/ai_engine.py` (`adaptive_productivity_benchmark`, `_mean`, `_std`)

### 6. Work behavior anomaly detection

Flags combinations of excessive hours, high idle, low productivity, and **large negative z-score vs history**; severity scales with number of reasons.

**Files:** `services/ai_engine.py` (`detect_work_anomaly`)

### 7. Telemetry signal quality and presence consistency

`telemetry_signal_quality` is `sparse` or `sufficient` based on hours, days, segments, and telemetry presence. `presence_consistency` maps attendance pattern to Regular / NeedsMonitoring / Irregular.

**Files:** `services/ai_engine.py` (`classify_telemetry_signal_quality`, `classify_presence_consistency`)

### 8. Narrative summary and actionable recommendations

`generate_summary` prioritizes sparse telemetry, burnout, anomalies, benchmark decline, and strong performance. `generate_recommendations` merges risks, attendance, anomalies, benchmark, signal quality, and **smart attendance** follow-ups from `build_full_report`.

**Files:** `services/ai_engine.py` (`generate_summary`, `generate_recommendations`, `build_full_report`)

### 9. Smart attendance: K-Means + Decision Tree reliability

Builds a **7-D feature row** (normalized lates, absences, active days, hour consistency from history, login/logout offsets, session span). Fits **KMeans(4)** on synthetic reference data, orders clusters by “badness,” assigns category labels; **DecisionTreeRegressor** predicts a **0–100 reliability** score. Exposes feature breakdown and algorithms used.

**Files:** `services/attendance_smart.py`, `services/ai_engine.py` (imports `analyze_smart_attendance`)

### 10. Performance ranking: weighted pillars + optional Random Forest

Default weights over five pillars (productivity, task completion, attendance, efficiency, collaboration). For cohort size ≥ 4, fits **RandomForestRegressor** to predict composite from pillars, **blends** prediction with composite, min-max scales, exposes **feature importances** in meta. Produces per-employee ranks, **top/bottom performer IDs**, **band** (top/mid/low thirds), and **department aggregates**.

**Files:** `services/performance_ranking.py`, `routes/analytics.py`

### 11. Optional external ML scorer (joblib)

If enabled and model path exists, loads sklearn artifact via joblib, builds **feature vector v1** from payload (aligned with `AI_ML_FEATURE_SCHEMA_VERSION`), runs `predict` and optional `predict_proba`; failures return error meta without breaking the main report.

**Files:** `services/ml_scorer.py`, `config.py` (ML env vars), `routes/analytics.py` (`meta["ml"]`)

### 12. Lightweight domain records (non-ORM)

Dataclasses for employee and task scalar records used elsewhere in design (ORM is SQL via `database.py`).

**Files:** `models.py`

### 13. Unit tests for analytics services

Tests cover productivity bounds, burnout/delay/attendance rules, benchmark decline, anomalies, telemetry ratio behavior, smart attendance outputs, full report inclusion, ranking order, and department aggregates.

**Files:** `tests/unit/test_ai_engine.py`, `tests/unit/test_attendance_smart.py`, `tests/unit/test_performance_ranking.py`, `pytest.ini`

### 14. Dependencies for ML stack

Declared packages for numpy, scikit-learn, joblib, etc.

**Files:** `requirements.txt`

---

## Balance note (how the split stays “equal”)

| Member | Approximate scope |
|--------|-------------------|
| **Member 1** | **12** feature areas — HTTP surface, middleware orchestration, all routes, schemas, idempotency usage, API tests |
| **Member 2** | **14** feature areas — security, config, rate limit, observability, DB, migrations, persistence, idempotency storage |
| **Member 3** | **14** feature areas — rules engine, smart attendance, ranking, optional ML, models, unit tests, requirements for ML |

If you need **strictly identical counts**, you can move **“Optional joblib ML”** (Member 3 §11) under Member 2 as “ML deployment configuration + inference hook” — the code still lives in `services/ml_scorer.py` and `routes/analytics.py`.

---

## Quick file index (by path)

| Path | Primary owner (for this division) |
|------|-----------------------------------|
| `main.py` | Member 1 (routes/middleware); Member 2 (rate limiter config wiring) |
| `config.py` | Member 2 |
| `security.py` | Member 2 |
| `rate_limit.py` | Member 2 |
| `observability.py` | Member 2 (implementation); Member 1 (middleware calls) |
| `errors.py` | Member 2 |
| `database.py` | Member 2 |
| `db_migrations.py`, `migrations/*.sql` | Member 2 |
| `idempotency.py` | Member 1 (API) + Member 2 (DB) |
| `schemas.py` | Member 1 |
| `models.py` | Member 3 |
| `routes/*.py` | Member 1 |
| `services/ai_engine.py` | Member 3 |
| `services/attendance_smart.py` | Member 3 |
| `services/performance_ranking.py` | Member 3 |
| `services/ml_scorer.py` | Member 3 (logic) / Member 2 (env toggles) |
| `tests/api/test_api_flow.py` | Member 1 |
| `tests/unit/*.py` | Member 3 |
| `requirements.txt` | Shared; ML lines emphasized for Member 3 |
| `.env.example` | Member 2 |
| `readme.md` | Project-wide documentation |

---

*Generated for team planning; adjust ownership to match your course’s rubric if instructors expect different grouping.*
