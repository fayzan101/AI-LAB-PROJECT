"""Optional scikit-learn inference via registry or legacy path. Never replaces rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from config import settings
from ml.features import FEATURE_SCHEMA_VERSION, build_feature_vector_v1
from services.model_registry import resolve_alias, validate_manifest

_model: Any = None
_load_attempted = False
_load_meta: dict[str, Any] = {}


def _ensure_model() -> None:
    global _model, _load_attempted, _load_meta
    if _load_attempted:
        return
    _load_attempted = True
    if not settings.ai_ml_enabled:
        _load_meta = {"skipped": True, "reason": "AI_ML_ENABLED unset"}
        return

    # Prefer registry alias when available
    manifest = resolve_alias(settings.ai_ml_active_alias)
    if manifest:
        ok, reason = validate_manifest(manifest)
        if not ok:
            _load_meta = {"skipped": True, "reason": reason, "alias": settings.ai_ml_active_alias}
            return
        path = Path(manifest["_artifact_path"])
        try:
            import joblib  # type: ignore[import-untyped]

            _model = joblib.load(path)
            _load_meta = {
                "loaded": True,
                "path": str(path),
                "model_version": manifest.get("version") or settings.ai_ml_model_version,
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "alias": settings.ai_ml_active_alias,
                "metrics": manifest.get("metrics"),
            }
            return
        except Exception as exc:  # noqa: BLE001
            _model = None
            _load_meta = {"skipped": True, "reason": f"registry_load_failed:{exc!s}"}
            return

    if not settings.ai_ml_model_path:
        _load_meta = {"skipped": True, "reason": "no registry alias or AI_ML_MODEL_PATH"}
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
            "feature_schema_version": settings.ai_ml_feature_schema_version or FEATURE_SCHEMA_VERSION,
        }
    except Exception as exc:  # noqa: BLE001
        _model = None
        _load_meta = {"skipped": True, "reason": f"load_failed:{exc!s}"}


def maybe_ml_scores(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """
    Returns metadata + prediction for analytics report `meta`, or None if ML unavailable.
    Failures never raise — rules remain authoritative.
    """
    _ensure_model()
    if _model is None:
        return {**_load_meta} if _load_meta else None
    x = [build_feature_vector_v1(payload)]
    out: dict[str, Any] = {"feature_schema_version": FEATURE_SCHEMA_VERSION, **_load_meta}
    try:
        pred = _model.predict(x)
        out["prediction"] = pred[0] if hasattr(pred, "__len__") else pred
        if hasattr(_model, "predict_proba"):
            proba = _model.predict_proba(x)
            out["proba"] = proba[0].tolist() if hasattr(proba[0], "tolist") else list(proba[0])
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "feature_schema_version": FEATURE_SCHEMA_VERSION, "skipped": True}
    return out


def ml_health() -> dict[str, Any]:
    _ensure_model()
    return {
        "enabled": settings.ai_ml_enabled,
        "loaded": _model is not None,
        "meta": _load_meta,
        "active_alias": settings.ai_ml_active_alias,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
    }
