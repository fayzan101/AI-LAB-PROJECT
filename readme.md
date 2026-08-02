# Remote Work Tracker – AI Server

FastAPI microservice that scores productivity, burnout risk, attendance patterns, anomalies, and team performance rankings. The portal **backend** calls this service server-to-server; browsers should not hit it directly.

## Stack

- **Runtime:** Python 3.10+, FastAPI + Uvicorn
- **DB:** SQLAlchemy (SQLite locally; PostgreSQL / Neon in production via `DATABASE_URL`)
- **Auth:** Service JWT (`client_id` / `client_secret` → Bearer token)
- **Analytics:** Rule engine + optional classical ML (`joblib` / scikit-learn)
- **Ops:** Rate limiting, Prometheus `/metrics`, liveness / readiness probes

## Features

- Productivity and burnout heuristics (tasks + optional agent telemetry scalars)
- Task delay signals, attendance patterns, z-score benchmarks, anomaly flags
- Weekly reports and team / department performance ranking
- Optional ML inference when `AI_ML_ENABLED` and model path are set
- Idempotency and schema migrations for deployed environments

## Prerequisites

- Python 3.10+
- Portal backend configured with matching `AI_SERVER_BASE_URL` and service credentials

## Setup

```bash
cd ai-server
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Key `.env` values:

```env
API_PREFIX=/api/v1
SERVICE_CLIENT_ID=portal-backend
SERVICE_CLIENT_SECRET=change-me
JWT_SECRET=change-this-secret-in-production
DATABASE_URL=sqlite:///employee_analytics.db
CORS_ORIGINS=http://localhost:3000
```

For Postgres (e.g. Neon), use a `postgresql+psycopg://…` URL.

## Running

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Live: `GET /health/live` · Ready: `GET /health/ready`

Portal backend should set:

```env
AI_SERVER_BASE_URL=http://localhost:8000
AI_SERVICE_CLIENT_ID=portal-backend
AI_SERVICE_CLIENT_SECRET=change-me
```

## Main routes (`API_PREFIX`, default `/api/v1`)

| Mount | Notes |
|-------|--------|
| `POST /auth/login` | Service client credentials → JWT |
| `POST /employee/data` | Ingest employee snapshots (+ optional telemetry) |
| `POST /tasks` | Ingest task progress |
| `POST /analytics/report` | Synchronous analytics / full report |
| `GET /reports/weekly/{employee_id}` | Historical weekly report |
| Ops / health | `/health/*`, `/metrics` (see `routes/ops.py`) |

Portal proxies live under **`/api/v1/ai/*`** on the Node backend.

## Optional ML

| Variable | Meaning |
|----------|---------|
| `AI_ML_ENABLED` | `true` / `1` to load a model |
| `AI_ML_MODEL_PATH` | Path to a `joblib` artifact |
| `AI_ML_MODEL_VERSION` | Version string echoed in `meta.ml` |

If unset or load fails, analytics still return rules-only results.

## Testing

```bash
pytest -q
```

CI: `.github/workflows/ci.yml`.

## Related packages

| Package | Role |
|---------|------|
| `backend/` | Express API that authenticates and proxies AI calls |
| `web/` | Admin portal (consumes backend, not this service directly) |
| `mobile/` | Employee app |
| `agent/` | Desktop telemetry agent |

See also `MODEL_CARD.md` and `functunality.md` for deeper model and feature notes.
