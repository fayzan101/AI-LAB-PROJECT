# Datasets for offline ML training

- `fixtures/tiny.csv` — synthetic, non-sensitive smoke fixture for CI.
- Prefer exporting real labeled rows via `python -m ml.export_dataset` (never commit PII).
- Models trained here are **optional** and must not replace the deterministic rule engine.
