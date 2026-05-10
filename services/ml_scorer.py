"""
Optional scikit-learn inference (joblib). Disabled unless AI_ML_ENABLED=1 and AI_ML_MODEL_PATH points to a file.
Feature order must match training (feature_schema_version).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from config import settings

_model: Any = None
_load_attempted = False
_load_meta: dict[str, Any] = {}


def _effective_seconds(payload: Mapping[str, Any]) -> tuple[float, float]:
    wh = float(payload.get("working_hours") or 0)
    ih = float(payload.get("idle_hours") or 0)
    a = payload.get("active_seconds")
    i = payload.get("idle_seconds")
    active_h = (int(a) / 3600.0) if a is not None else wh
    idle_h = (int(i) / 3600.0) if i is not None else ih
    return active_h, idle_h


def build_feature_vector_v1(payload: Mapping[str, Any]) -> list[float]:
    active_h, idle_h = _effective_seconds(payload)
    return [
        float(payload.get("working_hours") or 0),
        float(payload.get("idle_hours") or 0),
        float(payload.get("attendance_days") or 0),
        float(payload.get("segment_count") or 0),
        float(payload.get("focus_fragmentation_index") or 0),
        float(payload.get("task_progress") or 0),
        float(payload.get("tasks_completed") or 0),
        active_h,
        idle_h,
    ]


def _ensure_model() -> None:
    global _model, _load_attempted, _load_meta
    if _load_attempted:
        return
    _load_attempted = True
    if not settings.ai_ml_enabled or not settings.ai_ml_model_path:
        _load_meta = {"skipped": True, "reason": "AI_ML_ENABLED or path unset"}
        return
    path = Path(settings.ai_ml_model_path)
    if not path.is_file():
        _load_meta = {"skipped": True, "reason": "model file missing", "path": str(path)}
        return
    try:
        import joblib  # type: ignore[import-untyped]

        _model = joblib.load(path)
        _load_meta = {
            "loaded": True,
            "path": str(path),
            "model_version": settings.ai_ml_model_version,
            "feature_schema_version": settings.ai_ml_feature_schema_version,
        }
    except Exception as exc:  # noqa: BLE001
        _model = None
        _load_meta = {"skipped": True, "reason": f"load_failed:{exc!s}"}


def maybe_ml_scores(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """
    Returns metadata + prediction for analytics report `meta`, or None if ML unavailable.
    """
    _ensure_model()
    if _model is None:
        return None
    x = [build_feature_vector_v1(payload)]
    out: dict[str, Any] = {"feature_schema_version": settings.ai_ml_feature_schema_version, **_load_meta}
    try:
        pred = _model.predict(x)
        out["prediction"] = pred[0] if hasattr(pred, "__len__") else pred
        if hasattr(_model, "predict_proba"):
            proba = _model.predict_proba(x)
            out["proba"] = proba[0].tolist() if hasattr(proba[0], "tolist") else list(proba[0])
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "feature_schema_version": settings.ai_ml_feature_schema_version}
    return out
