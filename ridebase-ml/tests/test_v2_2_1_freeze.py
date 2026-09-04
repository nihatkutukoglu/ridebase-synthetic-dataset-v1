import hashlib
import json
from pathlib import Path

from ridebase_ml.v2_2.landmarks import FEATURE_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models/v2_2_1_v1_5"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_v2_2_1_selection_is_frozen_before_test() -> None:
    manifest = json.loads((MODEL_DIR / "v2_2_1_selection_manifest.json").read_text())
    assert manifest["status"] == "PASS"
    assert manifest["selection_frozen_before_test"] is True
    assert manifest["test_status"] == "SEALED_NOT_READ"
    assert manifest["feature_set"] == FEATURE_COLUMNS
    assert all(manifest["selection_checks"].values())
    assert not (MODEL_DIR / "test_first_touch.json").exists()


def test_v2_2_1_core_artifact_hashes_are_frozen() -> None:
    manifest = json.loads((MODEL_DIR / "v2_2_1_selection_manifest.json").read_text())
    for filename, expected in manifest["artifact_hashes"].items():
        assert _sha256(MODEL_DIR / filename) == expected


def test_final_behavior_and_product_gates_pass() -> None:
    behavior = json.loads((ROOT / "reports/v2_2_1_behavioral_audit.json").read_text())
    product = json.loads((ROOT / "reports/v2_2_1_overdue_high_usage_audit.json").read_text())
    assert behavior["status"] == "PASS"
    assert behavior["diagnostics"]["scenario_count"] >= 5000
    assert behavior["diagnostics"]["no_show_nonincreasing_rate"] >= .95
    assert behavior["probability_resolution"]["validation_p30_exact_zero_share"] == 0
    assert product["status"] == "PASS"
    assert len(product["table"]) == 24
    assert all(product["checks"].values())


def test_validation_recovery_is_statistical_not_probability_targeting() -> None:
    recovery = json.loads((ROOT / "reports/v2_2_1_recovery_selection.json").read_text())
    delta = recovery["validation_recovery_vs_existing_v2_2"]
    assert delta["ipcw_c_delta"] >= -.001
    assert delta["ibs_delta"] < 0
    assert delta["calibration_error_delta"] <= -.005
    product = json.loads((ROOT / "reports/v2_2_1_overdue_high_usage_audit.json").read_text())
    assert product["checks"]["no_exact_probability_target"] is True


def test_final_temporal_validation_is_acceptable() -> None:
    report = json.loads((ROOT / "reports/v2_2_1_temporal_cv.json").read_text())
    assert report["test_rows_read"] is False
    assert len(report["folds"]) == 3
    assert min(row["ipcw_c_index"] for row in report["folds"]) >= .68
