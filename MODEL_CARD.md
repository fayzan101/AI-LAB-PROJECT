# Model Card — Remote Work AI Analytics

## Intended use
- Produce productivity / burnout / delay / attendance analytics for internal HR dashboards.
- **Primary path:** deterministic rules (`rule_engine_version` in report meta).
- **Optional path:** classical ML regressor behind `AI_ML_ENABLED` + registry alias; results appear only in `meta.ml`.

## Out of scope
- Automated punitive HR actions without human review.
- Treating sparse telemetry as high-confidence truth.
- Claiming deep-learning or generative “AI” when rules are active.

## Data
- Portal rolls up agent `activity_logs` / `idle_logs` plus task/attendance scalars.
- Training fixtures must be synthetic or anonymized exports — never commit secrets/PII.

## Metrics & promotion
- Offline MAE gate: `mae <= 40` on holdout (`python -m ml.evaluate`).
- Promote only via explicit alias change in `ml/registry/aliases.json` (`staging` → `production`).
- Schema mismatch or load failure → skip ML; rules still return HTTP 200.

## Limitations
- Attendance “smart” clustering uses small synthetic reference data for UX labels — not a production predictor.
- Ranking RandomForest (when used) is cohort-relative, not a longitudinal forecast.
- Confidence falls when telemetry is sparse or data-quality status is `warn`/`fail`.

## Privacy
- Service-to-service JWT; tenant isolation enforced on every write/read.
- Prefer Neon/portal DB for employee facts; AI DB stores analytics reports for the AI service only.
