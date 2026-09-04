import hashlib
import json
from pathlib import Path

from ridebase_ml.v2_2.landmarks import BASE_FEATURE_COLUMNS, FEATURE_COLUMNS, OBSERVABLE_HISTORY_FEATURES


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models/v2_2_v1_5"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_selection_is_frozen_before_test() -> None:
    manifest = json.loads((MODEL_DIR / "v2_2_selection_manifest.json").read_text())
    assert manifest["status"] == "PASS"
    assert manifest["selection_split"] == "VALIDATION"
    assert manifest["test_status"] == "SEALED_NOT_READ"
    assert not (MODEL_DIR / "test_first_touch.json").exists()


def test_selection_artifact_hashes_match() -> None:
    manifest = json.loads((MODEL_DIR / "v2_2_selection_manifest.json").read_text())
    for filename, expected in manifest["artifacts"].items():
        assert _sha256(MODEL_DIR / filename) == expected


def test_behavior_gate_passes_all_predeclared_checks() -> None:
    audit = json.loads((MODEL_DIR / "massive_behavior_audit.json").read_text())
    assert audit["status"] == "PASS"
    assert audit["diagnostics"]["scenario_count"] >= 5000
    assert all(audit["checks"].values())


def test_frozen_54_prefix_and_observable_extension() -> None:
    feature_list = json.loads((MODEL_DIR / "feature_list.json").read_text())
    assert feature_list == FEATURE_COLUMNS
    assert feature_list[:54] == BASE_FEATURE_COLUMNS
    assert feature_list[54:] == OBSERVABLE_HISTORY_FEATURES


def test_selection_report_contains_no_test_result() -> None:
    report = json.loads((ROOT / "reports/v2_2_validation_selection.json").read_text())
    assert report["test_read"] is False
    assert "test_metrics" not in report
    assert report["selected"]["model"] == "xgb_cox_extended60"
    assert report["selected"]["calibration"] == "isotonic"
