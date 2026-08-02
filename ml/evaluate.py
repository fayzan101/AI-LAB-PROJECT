"""Offline evaluation CLI against a fixture holdout."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.features import FEATURE_SCHEMA_VERSION, build_feature_vector_v1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=ROOT / "ml" / "datasets" / "fixtures" / "tiny.csv")
    parser.add_argument("--artifact", type=Path, required=False)
    parser.add_argument("--model-name", default="productivity_baseline")
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()

    artifact = args.artifact
    if artifact is None:
        artifact = ROOT / "ml" / "registry" / "models" / args.model_name / args.version / "model.joblib"
    if not artifact.is_file():
        print(f"Artifact not found: {artifact}", file=sys.stderr)
        return 1

    import joblib  # type: ignore
    import numpy as np  # type: ignore

    model = joblib.load(artifact)
    rows = list(csv.DictReader(args.fixture.open(newline="", encoding="utf-8")))
    X, y = [], []
    for row in rows:
        feat_payload = {
            "working_hours": float(row.get("working_hours", 0)),
            "idle_hours": float(row.get("idle_hours", 0)),
            "attendance_days": float(row.get("attendance_days", 0)),
            "segment_count": float(row.get("segment_count", 0)),
            "focus_fragmentation_index": float(row.get("focus_fragmentation_index", 0)),
            "task_progress": float(row.get("task_progress", 0)),
            "tasks_completed": float(row.get("tasks_completed", 0)),
            "active_seconds": float(row.get("active_seconds", 0)) or None,
            "idle_seconds": float(row.get("idle_seconds", 0)) or None,
        }
        X.append(build_feature_vector_v1(feat_payload))
        y.append(float(row["label"]))

    preds = model.predict(np.array(X))
    mae = float(np.mean(np.abs(preds - np.array(y))))
    rmse = float(np.sqrt(np.mean((preds - np.array(y)) ** 2)))
    out = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "n": len(y),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "pass": mae <= 40,
    }
    print(json.dumps(out, indent=2))
    return 0 if out["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
