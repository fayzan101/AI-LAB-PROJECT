"""Filesystem model registry with alias resolution and schema validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import settings

from ml.features import FEATURE_SCHEMA_VERSION


def registry_root() -> Path:
    root = Path(settings.ai_ml_registry_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parent.parent / root
    return root


def resolve_alias(alias: str | None = None) -> dict[str, Any] | None:
    """Return model.json for the active alias, or None."""
    name = alias or settings.ai_ml_active_alias
    aliases_path = registry_root() / "aliases.json"
    if not aliases_path.is_file():
        return None
    try:
        aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    target = aliases.get(name)
    if not target:
        return None
    model_name = target.get("model")
    version = target.get("version")
    if not model_name or not version:
        return None
    manifest = registry_root() / "models" / model_name / version / "model.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    artifact = registry_root() / "models" / model_name / version / data.get("artifact", "model.joblib")
    data["_artifact_path"] = str(artifact)
    data["_alias"] = name
    return data


def validate_manifest(manifest: dict[str, Any]) -> tuple[bool, str]:
    schema = str(manifest.get("feature_schema_version") or "")
    if schema != FEATURE_SCHEMA_VERSION:
        return False, f"feature_schema_mismatch:{schema}!={FEATURE_SCHEMA_VERSION}"
    path = Path(manifest.get("_artifact_path") or "")
    if not path.is_file():
        return False, "artifact_missing"
    metrics = manifest.get("metrics") or {}
    # Soft gate: refuse promotion-like aliases if MAE too high when present
    mae = metrics.get("mae")
    if mae is not None and float(mae) > 40:
        return False, f"mae_above_gate:{mae}"
    return True, "ok"
