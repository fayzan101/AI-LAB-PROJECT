# 🤖 AI-Based Employee Productivity & Analytics System

## 📌 Overview

This project is an **AI-powered FastAPI microservice** that analyzes employee data to generate insights like productivity, burnout risk, task delays, performance trends, and workload balance recommendations.

It acts as an **intelligent analytics layer** for HR dashboards and workforce management systems.

---

## 🏗️ Architecture

Portal backend (Node) aggregates **agent telemetry** (`activity_logs` + `idle_logs`) and pushes scalars to this service. No direct reads of the main app database.

Employee / report payloads → **rule engine** (+ optional scikit-learn joblib) → JSON insights → dashboards / workers.

---

## ⚙️ Tech Stack

* Python (FastAPI)
* Rule-based scoring (productivity, burnout heuristic, attendance pattern, z-score benchmark, anomalies)
* Optional classical ML: `joblib` model + `AI_ML_ENABLED` / `AI_ML_MODEL_PATH`
* JSON-based persistence (`employee_inputs.extra_json` stores telemetry keys)
* Postman / pytest (testing)

---

## 📁 Project Structure

```
fastapi-ai-system/
├── main.py
├── database.py
├── models.py
├── schemas.py
├── routes/
├── services/
│   ├── ai_engine.py
│   ├── analytics_service.py
├── utils/
├── data/
```

---

## 🚀 Features

### 📊 AI Analytics

* Productivity score (tasks + **telemetry-aware** active/idle ratio and fragmentation penalty when `active_seconds` / `segment_count` are present)
* Burnout risk heuristic (hours + idle proportion)
* Task delay prediction (rule-based)
* Attendance pattern (**late** signal can use `first_seen_offset_minutes`; `attendance_days` = days with agent data when sent from telemetry snapshot)
* Adaptive productivity benchmarking (z-score vs history)
* Work behavior anomaly flags
* Deterministic **telemetry_signal_quality** (`sparse` | `sufficient`) and **presence_consistency** labels on reports

---

## Agent telemetry fields (optional on ingest)

When the portal sends agent rollups, JSON may include: `active_seconds`, `idle_seconds`, `telemetry_days_with_data`, `segment_count`, `focus_fragmentation_index`, `first_seen_offset_minutes`, `last_seen_offset_minutes`. Older clients may omit them; the engine falls back to `working_hours` / `idle_hours` only.

### Optional ML inference

Set environment variables:

| Variable | Meaning |
|----------|---------|
| `AI_ML_ENABLED` | `1` / `true` to attempt loading a model |
| `AI_ML_MODEL_PATH` | Filesystem path to a `joblib` artifact (e.g. sklearn classifier) |
| `AI_ML_MODEL_VERSION` | Arbitrary version string echoed in `meta.ml` |
| `AI_ML_FEATURE_SCHEMA_VERSION` | Must match training feature order in `services/ml_scorer.build_feature_vector_v1` |

If unset or load fails, analytics still succeed with rules-only output.

---

## 🔗 API Endpoints

All JSON routes below are mounted under **`API_PREFIX`** (default **`/api/v1`**), e.g. `POST /api/v1/auth/login`. Interactive **OpenAPI** (**Swagger UI**) is at **`/docs`** while the app is running (`http://127.0.0.1:8000/docs` by default). The portal backend OpenAPI (`/docs` on the Node app) documents **`/api/v1/ai/*`** proxies that call this service server-to-server.

### Auth API

* POST `/auth/login`

### Core APIs (Bearer token required)

* POST `/employee/data`
* POST `/tasks`

### Analytics APIs

* POST `/analytics/report`
* GET `/reports/weekly/{employee_id}`

### Health APIs

* GET `/health/live`
* GET `/health/ready`
* GET `/health/startup`

---

## 🧠 AI Engine

The AI module uses:

* Weighted scoring models
* Rule-based decision making
* Pattern & trend detection
* Risk classification logic
* Personalized baseline comparison (z-score)
* Work behavior anomaly detection

---

## ✅ Testing

Run locally:

```bash
pytest -q
```

CI is configured in `.github/workflows/ci.yml` and runs syntax checks plus tests on push/PR.

---

## 👨‍💻 Team Roles

* **Backend Developer:** FastAPI APIs & integration
* **AI Developer:** Core analytics & AI logic
* **Tester/Doc Writer:** Dataset, testing & documentation

---

## 📈 Output

The system returns structured JSON insights for HR dashboards, enabling smarter decision-making for employee performance management.

---

## 🏁 Goal

To build an intelligent system that helps organizations **analyze employee performance, detect risks early, and optimize workload efficiently.**

---

If you want, I can also make a **GitHub-ready README with badges + diagrams + deployment steps**.
