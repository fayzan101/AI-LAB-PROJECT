from services.drift import drift_severity, population_stability_index, summarize_drift
from services.model_registry import validate_manifest
from ml.features import FEATURE_SCHEMA_VERSION, build_feature_vector_v1


def test_feature_vector_length():
    v = build_feature_vector_v1({"working_hours": 8, "idle_hours": 1, "tasks_completed": 5})
    assert len(v) == 9
    assert FEATURE_SCHEMA_VERSION == "1"


def test_psi_and_severity():
    base = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    same = list(base)
    assert population_stability_index(base, same) < 0.1
    assert drift_severity(0.05) == "low"
    assert drift_severity(0.3) == "high"
    s = summarize_drift(base, [10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
    assert "psi" in s


def test_validate_manifest_schema():
    ok, reason = validate_manifest(
        {"feature_schema_version": "999", "_artifact_path": "/no/such/file"}
    )
    assert not ok
    assert "feature_schema" in reason
