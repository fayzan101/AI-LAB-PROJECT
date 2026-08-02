"""Offline training CLI — writes a registry artifact (not auto-promoted)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.features import FEATURE_NAMES_V1, FEATURE_SCHEMA_VERSION, build_feature_vector_v1


def _load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(description="Train productivity baseline regressor")
    parser.add_argument("--fixture", type=Path, default=ROOT / "ml" / "datasets" / "fixtures" / "tiny.csv")
    parser.add_argument("--model-name", default="productivity_baseline")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "ml" / "registry")
    args = parser.parse_args()

    rows = _load_rows(args.fixture)
    if len(rows) < 3:
        print("Need at least 3 rows", file=sys.stderr)
        return 1

    X = []
    y = []
    for row in rows:
        payload = {k: float(row[k]) if k != "employee_id" else row[k] for k in row if k != "label"}
        # map fixture columns
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

    try:
        from sklearn.linear_model import LinearRegression  # type: ignore
        import joblib  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        print("sklearn/joblib required for training", file=sys.stderr)
        return 1

    model = LinearRegression()
    model.fit(np.array(X), np.array(y))
    preds = model.predict(np.array(X))
    mae = float(np.mean(np.abs(preds - np.array(y))))

    out = args.out_dir / "models" / args.model_name / args.version
    out.mkdir(parents=True, exist_ok=True)
    artifact = out / "model.joblib"
    joblib.dump(model, artifact)
    manifest = {
        "name": args.model_name,
        "version": args.version,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES_V1,
        "artifact": "model.joblib",
        "metrics": {"mae": round(mae, 4), "n_train": len(y)},
        "intended_use": "Optional productivity estimate; rules remain authoritative.",
    }
    (out / "model.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    aliases_path = args.out_dir / "aliases.json"
    aliases = {}
    if aliases_path.is_file():
        aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
    # Only write staging by default — production promotion is explicit
    aliases["staging"] = {"model": args.model_name, "version": args.version}
    aliases_path.write_text(json.dumps(aliases, indent=2), encoding="utf-8")

    metrics_path = ROOT / "evals" / "latest.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(
            {
                "model": args.model_name,
                "version": args.version,
                "mae": round(mae, 4),
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "promotion_gate_mae_max": 40,
                "promotable": mae <= 40,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "artifact": str(artifact), "mae": mae}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
