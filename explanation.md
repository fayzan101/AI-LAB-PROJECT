# AI Server — Full Project Explanation (Easy Words)

This document explains the **`ai-server`** folder in the **Remote Work Tracker** project. The language is kept simple on purpose so you can use it for study, demos, or **viva (oral exam)** preparation.

---

## 1. What is this project, in one paragraph?

The **AI server** is a small **Python web service** built with **FastAPI**. It is **not** meant to be called directly by users in a browser. Instead, the **portal backend** (Node.js) talks to it **server-to-server** after logging in with a **service account** (client id + secret). The AI server:

- Accepts **employee snapshots** and **task updates** (and stores them in a database).
- Runs a **rule-based “analytics engine”** to compute things like **productivity score**, **burnout risk**, **delay risk**, **attendance pattern**, **personal baseline comparison**, and **anomaly hints**.
- Optionally runs a **machine learning model** (scikit-learn saved with **joblib**) if you turn it on in settings.
- Saves **full analytics reports** so they can be fetched later (e.g. “weekly” history).
- Provides **health checks**, **metrics**, **rate limiting**, **request tracing**, and **safe retries** using **idempotency keys**.

Think of it as the **“brain + notebook”** for analytics: it **calculates** insights and **writes them down** in its own database.

---

## 2. Where does it sit in the bigger system?

- **Web app (Next.js)** → talks to **Node backend**.
- **Node backend** → aggregates data (including optional **agent telemetry**), then calls this service under something like **`/api/v1/ai/*`** on its side, which **proxies** to the AI server’s real routes under **`API_PREFIX`** (default **`/api/v1`**).
- **AI server** → uses **its own database** (`DATABASE_URL`). It does **not** read the main app’s database directly.

So: **browsers never hold the service secret**; only the trusted backend does.

---

## 3. Main technologies (simple list)

| Piece | Role |
|--------|------|
| **FastAPI** | HTTP API framework (routes, validation, OpenAPI `/docs`). |
| **Pydantic** | Validates incoming JSON against schemas (correct types, ranges). |
| **SQLAlchemy + SQL** | Connects to SQLite or Postgres; runs migrations and inserts/queries. |
| **PyJWT** | Creates and checks **Bearer tokens** for service clients. |
| **Redis (optional)** | Shared **rate limit** store across multiple instances. |
| **prometheus-client** | Exposes **/metrics** for monitoring. |
| **pytest + httpx** | Automated tests. |
| **scikit-learn + joblib (optional)** | Extra ML prediction attached to report **meta** when enabled. |

---

## 4. Folder structure — what lives where?

Typical layout (names may vary slightly):

- **`main.py`** — Creates the FastAPI app, wires middleware, mounts routers, health routes, exception handlers.
- **`config.py`** — Reads **environment variables** into one `settings` object.
- **`database.py`** — DB engine, **save** helpers, **idempotency** DB helpers, **fetch recent reports**, readiness check.
- **`db_migrations.py`** — Runs numbered SQL files from **`migrations/`** in order.
- **`migrations/*.sql`** — Table definitions and upgrades (e.g. `extra_json` on employees).
- **`schemas.py`** — Pydantic models for requests/responses (shape of JSON).
- **`models.py`** — Smaller/simple data shapes (legacy or shared types).
- **`security.py`** — JWT create/verify, service client check, `require_auth`, `require_scope`.
- **`errors.py`** — Maps HTTP status codes to stable **`error_code`** strings for clients.
- **`idempotency.py`** — Wraps DB idempotency: return cached response or **409** if same key, different body.
- **`observability.py`** — Request id (`x-request-id` / trace), structured logs, Prometheus metrics.
- **`rate_limit.py`** — Per-IP sliding/window limiter: **Redis** if configured, else **in-memory**.
- **`routes/`** — One module per area: `auth`, `employee`, `tasks`, `analytics`, `reports`.
- **`services/ai_engine.py`** — Pure **rule-based** analytics (no HTTP).
- **`services/ml_scorer.py`** — Optional **joblib** model load + predict.
- **`tests/`** — Unit/integration tests.
- **`requirements.txt`** — Python dependencies.
- **`readme.md`** — Quick developer overview.
- **`.env.example`** — Hints for local env vars (not secrets committed).

---

## 5. Request flow (end-to-end, easy words)

1. **Portal backend** sends `POST .../auth/login` with `client_id`, `client_secret`, `tenant_id`, and optional **scopes**.
2. AI server checks id/secret against **`SERVICE_CLIENT_ID`** / **`SERVICE_CLIENT_SECRET`**.
3. If OK, it returns a **JWT** (`access_token`) that includes **`tenant_id`** and **scopes**.
4. For other routes, the backend sends `Authorization: Bearer <token>`.
5. AI server verifies JWT (signature, expiry, issuer, audience) and checks **tenant_id** matches the request body/query where required.
6. For **write** routes, it often requires scope **`analytics:write`**; for **read** reports, **`analytics:read`**.
7. Optional header **`Idempotency-Key`**: same key + same payload → same response; same key + different payload → **409 Conflict** (so retries are safe).

---

## 6. API endpoints (what each does)

All JSON routes are under **`API_PREFIX`** (default **`/api/v1`**). Examples below use that prefix.

### Authentication

- **`POST /api/v1/auth/login`**  
  **Who:** Portal backend (service client).  
  **What:** Validates client credentials; returns **JWT**.  
  **Auth:** None (this *is* the login).

### Employees

- **`POST /api/v1/employee/data`**  
  **What:** Accepts one **employee snapshot** (tasks completed, hours, attendance, progress, etc., plus optional telemetry fields).  
  **Stores:** Row in **`employee_inputs`**; telemetry-like fields may go into **`extra_json`**.  
  **Auth:** Bearer + scope **`analytics:write`** + tenant match.

### Tasks

- **`POST /api/v1/tasks`**  
  **What:** Accepts **task progress** (`progress_percent`, `days_left`, ids).  
  **Stores:** Row in **`task_inputs`**.  
  **Auth:** Bearer + **`analytics:write`** + tenant match.

### Analytics

- **`POST /api/v1/analytics/report`**  
  **What:** Builds the **full report** using **`build_full_report`** (rules) + optional **`maybe_ml_scores`**.  
  **Stores:** Full JSON in **`analytics_reports`**; returns **`report_id`** in **`meta`**.  
  **Auth:** Bearer + **`analytics:write`** + tenant match.  
  **Note:** Request can include **`history`** (past baseline points) for z-score benchmarking.

### Reports

- **`GET /api/v1/reports/weekly/{employee_id}?tenant_id=...&limit=...`**  
  **What:** Reads recent saved reports for that employee (default limit 7, max 30).  
  **Returns:** `history`, `latest_report`, counts.  
  **Auth:** Bearer + **`analytics:read`** + tenant match on query param.

### Health & ops (usually no auth)

- **`/health/live`** — Process is up.  
- **`/health/ready`** — Can serve traffic (e.g. DB reachable).  
- **`/health/startup`** — Startup finished flag.  
- **`/metrics`** — Prometheus metrics.  
- **`/docs`** — Swagger UI (when running).

**Exempt from rate limiting (see `main.py`):** live/ready/startup, login, `/metrics`, and `/` (if used).

---

## 7. Database tables (simple meaning)

| Table | Purpose |
|--------|---------|
| **`employee_inputs`** | History of employee snapshots ingested from the portal. Core columns + **`extra_json`** for telemetry extras. |
| **`task_inputs`** | History of task progress updates. |
| **`analytics_reports`** | Saved **full reports** (JSON blob + a few indexed scalar fields like productivity and risks). |
| **`idempotency_keys`** | Remembers **Idempotency-Key** + endpoint + tenant + hash of body → stored response for safe retries. |

Indexes exist on **`(tenant_id, employee_id, created_at)`** for faster “recent history” queries.

---

## 8. Configuration (`config.py`) — what you can set

Important environment variables (see also **`.env.example`** and **`readme.md`**):

- **`API_PREFIX`** — URL prefix for all routers (default `/api/v1`).
- **`JWT_SECRET`**, **`JWT_ALGORITHM`**, **`JWT_ISSUER`**, **`JWT_AUDIENCE`**, **`TOKEN_EXP_SECONDS`** — Token signing and validation.
- **`SERVICE_CLIENT_ID`**, **`SERVICE_CLIENT_SECRET`** — The only service pair accepted at login (in default setup).
- **`DEFAULT_SCOPE`** — Space-separated scopes put in tokens if not overridden.
- **`DATABASE_URL`** — e.g. SQLite file or Postgres URL.
- **`CORS_ORIGINS`** — Comma-separated browser origins (still, **this API is for backends**).
- **`RATE_LIMIT_WINDOW_SECONDS`**, **`RATE_LIMIT_MAX_REQUESTS`** — Rate limit window.
- **`REDIS_URL`** — If set, rate limiter uses Redis; otherwise memory (per process).
- **`AI_ML_ENABLED`**, **`AI_ML_MODEL_PATH`**, **`AI_ML_MODEL_VERSION`**, **`AI_ML_FEATURE_SCHEMA_VERSION`** — Optional ML.

---

## 9. Security model (viva-friendly)

- **Service JWT**: After login, every protected route needs **`Authorization: Bearer`**.  
- **Tenant isolation**: Token’s **`tenant_id`** must match the **`tenant_id`** in body or query; otherwise **403**.  
- **Scopes**: Write vs read separated (`analytics:write` vs `analytics:read`).  
- **No user passwords here**: This service trusts **one backend client** (plus optional extension if you change code).  
- **Secrets**: Must come from env vars in real deployments; never hardcode in git.

---

## 10. Idempotency (why it matters)

**Problem:** Networks retry. Without idempotency, the same request might **insert twice**.

**Solution:** Client sends **`Idempotency-Key`** (unique per logical operation).  
Server stores a **hash of the request body** with that key:

- Same key + same body → return **cached** response.  
- Same key + **different** body → **409 Conflict** (prevents silent corruption).

If the header is **omitted**, each call is treated as a **new** operation.

---

## 11. Rate limiting (`rate_limit.py`)

- Counts requests **per client IP** (from the TCP connection; optional proxy trust can be configured via **`TRUST_PROXY_HEADERS`** in settings).
- If **`REDIS_URL`** is set, limits are shared across replicas.
- If not, each server process has its **own** memory counter (fine for single instance, not for clusters).

---

## 12. Observability (`observability.py`)

- Assigns / propagates a **request id** (trace id) for logs and response headers.
- Records request **duration** and **status** for Prometheus.
- **`/metrics`** exposes counters/histograms for operators.

---

## 13. Rule-based AI engine (`services/ai_engine.py`) — detailed but simple

This is **deterministic logic**, not a neural network. It turns a **payload** (dict) + optional **history** into a **report dict**.

### Helper ideas

- **`_as_dict`** — Accepts either a dict or an object with **`model_dump()`** (Pydantic).
- **`_mean` / `_std`** — Average and standard deviation for z-scores.
- **`_effective_active_idle_seconds`** — If **`active_seconds`** / **`idle_seconds`** exist, use them; else approximate from **`working_hours`** and **`idle_hours`** (hours × 3600).

### Telemetry awareness

- **`has_telemetry_extras`** — True if **`active_seconds`** or **`segment_count`** is present (signals “agent-style” data).
- **`classify_telemetry_signal_quality`** — Returns **`sparse`** or **`sufficient`**. If data looks incomplete (e.g. long work window but almost no segments), the report should be interpreted cautiously.

### Scoring and risk

- **`calculate_productivity`** — Starts from tasks, attendance days, and idle hours; clamps 0–100. If good telemetry exists, adjusts using **active vs idle ratio** and optional **focus fragmentation** penalty.
- **`detect_burnout`** — Uses long hours, productivity, and idle ratio → **High / Medium / Low** risk (heuristic).
- **`predict_delay`** — Uses **`task_progress`** and **`days_left`** → delay risk levels.
- **`analyze_attendance_pattern`** — Uses late/absent counts; can infer stricter “lateness” from **`first_seen_offset_minutes`** when telemetry exists → **Regular / Needs Monitoring / Irregular**.

### Personal baseline

- **`adaptive_productivity_benchmark`** — Compares current productivity to **`history`** list of past scores:
  - Computes **z-score** (how many standard deviations from their own mean).
  - If fewer than 5 points: **Warm-up** (not enough history).
  - Else: **Decline / Improvement / Stable** based on z-score thresholds (e.g. ±1.5).

### Anomalies

- **`detect_work_anomaly`** — Collects **reasons** (very long hours, high idle, low productivity, or statistical outlier vs history). Severity **Low / Medium / High** depends on how many reasons fired.

### Natural language style outputs

- **`generate_recommendations`** — Turns all signals into a **short list of actions** (e.g. reduce workload, manager review, verify agent pairing if telemetry sparse).
- **`generate_summary`** — One **paragraph-style** sentence capturing the overall story (with special case if telemetry is sparse).

### Main entry

- **`build_full_report`** — Calls everything above and returns a single dictionary with **tenant_id**, **employee_id**, all metrics, **adaptive_benchmark**, **anomaly_detection**, **summary**, **recommendations**, **telemetry_signal_quality**, **presence_consistency** (mapped from attendance pattern).

---

## 14. Optional ML (`services/ml_scorer.py`)

- **Off by default.** Turn on with **`AI_ML_ENABLED=1`** and set **`AI_ML_MODEL_PATH`** to a file.
- Loads **`joblib`** artifact once; remembers load success/failure in **`_load_meta`**.
- **`build_feature_vector_v1`** — Fixed **order** of numbers derived from payload (must match training — **`AI_ML_FEATURE_SCHEMA_VERSION`** documents this version).
- **`maybe_ml_scores`** — If model loads, returns **`meta.ml`** with **prediction** and maybe **`predict_proba`**; if anything fails, may return an **error** object — **analytics route still succeeds** with rules output.

**Important:** The ML output is **extra metadata**, not a replacement for the rule engine’s main fields (unless you change the product design).

---

## 15. Analytics route (`routes/analytics.py`) — ties it together

1. Authenticates and checks **scope** and **tenant**.
2. Checks **idempotency** cache.
3. Calls **`build_full_report`**.
4. Wraps results in **`ReportResponse`** / Pydantic types.
5. Calls **`maybe_ml_scores`** and attaches under **`meta["ml"]`** if present.
6. **`save_analytics_report`** → DB; puts **`report_id`** in **`meta`**.
7. Stores idempotent response if key provided.

---

## 16. Employee ingest (`routes/employee.py`) & tasks (`routes/tasks.py`)

- Validate payload, tenant, scope.
- Idempotency same pattern as analytics.
- **`save_employee_input`** / **`save_task_input`** persist rows.

**Telemetry:** Only known extra keys are stripped into **`extra_json`** in **`database.py`** so the main columns stay stable while still storing agent rollups.

---

## 17. Reports route (`routes/reports.py`)

- Read-only for **`analytics:read`**.
- **`get_recent_reports`** returns a list; route exposes **latest** plus **full list** up to **`limit`**.

---

## 18. Auth route (`routes/auth.py`)

- Accepts **`LoginRequest`**: client id/secret, tenant, scopes list.
- **`authenticate_service_client`** compares to settings.
- **`create_access_token`** embeds tenant and scopes.

---

## 19. Testing

- **`pytest`** runs unit tests (see **`tests/unit/test_ai_engine.py`**) for productivity, burnout, delay, attendance, benchmark, anomaly, telemetry ratio, etc.
- CI (if enabled in repo) runs checks on push/PR — see **`.github/workflows`** at repo level if present.

---

## 20. Limitations & honest notes (good for viva)

- **Heuristics are not “medical truth”** — burnout and productivity are **indicators**, not diagnoses.
- **Fairness**: Rules can bias toward certain work styles; ML adds **extra responsibility** (data quality, drift, fairness).
- **Telemetry sparse** — The engine itself warns when agent data is thin.
- **Single service client** by default — fine for class projects; real systems use **OAuth2 client credentials**, **key rotation**, **mTLS**, etc.
- **Rate limit by IP** — Behind NAT, many users may share one IP (usually OK for server-to-server from one backend).

---

## 21. Summary — each functionality in one place

| Functionality | One-line summary |
|---------------|------------------|
| **FastAPI app (`main.py`)** | Starts the service, adds CORS, logging, rate limit, metrics, routers, and global error shape. |
| **Settings (`config.py`)** | Central place for secrets, DB URL, JWT, CORS, rate limits, optional ML flags. |
| **Migrations (`db_migrations.py` + `migrations/`)** | Creates/updates tables in order. |
| **Employee save (`database.save_employee_input`)** | Inserts snapshot + telemetry JSON extras. |
| **Task save (`save_task_input`)** | Inserts task progress record. |
| **Report save (`save_analytics_report`)** | Persists analytics JSON and key scalars. |
| **Recent reports (`get_recent_reports`)** | Fetches history for dashboards. |
| **DB readiness (`is_db_ready`)** | Used by health checks. |
| **JWT (`security.py`)** | Mint and verify bearer tokens with tenant + scopes. |
| **Route guards (`require_auth`, `require_scope`)** | Reject bad/missing tokens or wrong scope. |
| **Idempotency (`idempotency.py` + DB)** | Safe retries with `Idempotency-Key`. |
| **Errors (`errors.py`)** | Stable `error_code` for machines. |
| **Rate limit (`rate_limit.py`)** | Throttle abusive traffic (Redis or memory). |
| **Observability (`observability.py`)** | Trace ids, logs, Prometheus. |
| **Rule engine (`ai_engine.py`)** | All main analytics fields and narrative outputs. |
| **ML scorer (`ml_scorer.py`)** | Optional joblib predict for `meta.ml`. |
| **Auth route** | Service login → JWT. |
| **Employee route** | Ingest employee metrics. |
| **Tasks route** | Ingest task metrics. |
| **Analytics route** | Full report + save + optional ML meta. |
| **Reports route** | Read weekly/history style data. |
| **Health/metrics** | Operations endpoints for deploys and monitoring. |

---

## 22. Viva / oral exam questions (with short answer hints)

### Big picture

1. **What is the AI server’s job in this project?**  
   *Hint:* Backend-only analytics microservice: ingest, compute report, store, expose health/metrics.

2. **Why shouldn’t the browser call the AI server directly?**  
   *Hint:* Service secret and JWT would be exposed; tenant trust boundary is the portal backend.

3. **How does multi-tenant isolation work?**  
   *Hint:* `tenant_id` inside JWT must match request payload/query.

### Security

4. **What is a JWT and what claims are important here?**  
   *Hint:* Signed token; `tenant_id`, `scope`, `exp`, `iss`, `aud`.

5. **Difference between authentication and authorization?**  
   *Hint:* Auth = who you are; authorize = scopes (`analytics:read` vs `write`).

6. **What happens if `SERVICE_CLIENT_SECRET` is wrong?**  
   *Hint:* Login fails with 401.

### API design

7. **Why separate `POST /employee/data`, `POST /tasks`, and `POST /analytics/report`?**  
   *Hint:* Separation of concerns: raw ingest vs derived analytics; different write scopes/frequencies.

8. **What is idempotency and why 409?**  
   *Hint:* Retry safety; 409 means “same key reused for a different body — conflict.”

9. **What does `GET /reports/weekly/{employee_id}` return?**  
   *Hint:* Recent saved reports + latest snapshot for an employee.

### Data & DB

10. **Why store `extra_json` for employees?**  
    *Hint:* Forward-compatible storage for telemetry fields without migrating columns every time.

11. **What tables would you query to debug “missing history”?**  
    *Hint:* `analytics_reports` and/or `employee_inputs` by tenant + employee + time.

### Observability & reliability

12. **Why `/health/live` vs `/health/ready`?**  
    *Hint:* Live = process up; ready = dependencies OK (e.g. DB).

13. **What does `/metrics` help with?**  
    *Hint:* Prometheus scraping, SLOs, alerts.

14. **Redis vs in-memory rate limiting tradeoff?**  
    *Hint:* Redis = shared across instances; memory = per process only.

### AI / analytics logic

15. **Is this “AI” in the deep learning sense?**  
    *Hint:* Core is rule-based heuristics; optional classical ML.

16. **How is productivity score computed at a high level?**  
    *Hint:* Weighted mix of tasks/attendance minus idle, clamped; telemetry adjusts active/idle ratio and fragmentation penalty.

17. **What is a z-score in `adaptive_productivity_benchmark`?**  
    *Hint:* How far current score is from the employee’s own historical mean in standard deviations.

18. **Why “Warm-up” status?**  
    *Hint:* Not enough history points (<5) for stable personal baseline.

19. **What triggers anomaly “severity High”?**  
    *Hint:* Multiple simultaneous reasons (e.g. long hours + idle + outlier).

20. **What does `telemetry_signal_quality: sparse` imply?**  
    *Hint:* Interpret scores carefully; maybe agent not paired or incomplete segments.

### ML optional

21. **When does `maybe_ml_scores` return `None`?**  
    *Hint:* ML disabled, path missing, load failed, or model not loaded.

22. **Why `feature_schema_version`?**  
    *Hint:* Training-serving skew guardrail; vector order must match training.

### Ethics / product

23. **Why should managers not use “burnout risk” as a medical label?**  
    *Hint:* Heuristic from work metrics; not clinical assessment.

24. **What privacy considerations apply?**  
    *Hint:* Employee telemetry is sensitive; minimize retention, secure DB, access control.

25. **How would you improve fairness?**  
    *Hint:* Review rules per role, validate across teams, audit ML, allow human override.

---

## 23. Quick revision checklist

- [ ] Draw diagram: Web → Node → AI server → DB.  
- [ ] List routes with correct HTTP methods.  
- [ ] Explain JWT + tenant + scopes.  
- [ ] Explain idempotency header behavior.  
- [ ] Walk through **`build_full_report`** outputs.  
- [ ] Mention optional ML and where it appears (**`meta.ml`**).  
- [ ] Mention health: live/ready/startup + metrics.

---

*End of `explanation.md` — generated for study and viva prep for the `ai-server` service.*
