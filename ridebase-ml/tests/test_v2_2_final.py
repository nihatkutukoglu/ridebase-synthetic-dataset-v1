import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ridebase_ml.v2_2.landmarks import FEATURE_COLUMNS
from ridebase_ml.v2_2.shadow import V22ShadowPredictor


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models/v2_2_v1_5"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_first_touch_follows_frozen_selection() -> None:
    first = json.loads((MODEL_DIR / "test_first_touch.json").read_text())
    assert first["selection_manifest_sha256"] == _sha256(MODEL_DIR / "v2_2_selection_manifest.json")
    assert "first and only" in first["protocol"]
    public_manifest = json.loads((ROOT / "v2_2_selection_manifest.json").read_text())
    assert public_manifest["selection_frozen_before_test"] is True
    assert public_manifest["hash_chain_verified"] is True


def test_frozen_test_and_unseen_gates_pass() -> None:
    result = json.loads((MODEL_DIR / "test_evaluation.json").read_text())
    assert result["status"] == "PASS"
    assert all(result["test_checks"].values())
    assert result["test_metrics"]["ipcw_c_index"] >= .65
    assert result["unseen_motorcycle_metrics"]["ipcw_c_index"] >= .65
    assert result["p30_distribution"]["exact_zero_share"] < .05


def test_dedicated_product_audit_preserves_semantics() -> None:
    audit = json.loads((ROOT / "reports/v2_2_overdue_high_usage_audit.json").read_text())
    assert audit["status"] == "PASS"
    assert all(audit["checks"].values())
    assert "not the same outcome" in audit["semantic_note"]


def test_shadow_package_is_offline_and_deterministic_with_ood_warning() -> None:
    data = ROOT / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet"
    row = pd.read_parquet(data, filters=[("modeling_role", "==", "VALIDATION")]).iloc[[0]][FEATURE_COLUMNS]
    predictor = V22ShadowPredictor(MODEL_DIR)
    assert predictor.card["deployment_status"] == "OFFLINE_SHADOW_ONLY"
    duplicated = pd.concat([row, row], ignore_index=True)
    first, warnings = predictor.predict(duplicated)
    assert not warnings
    assert np.array_equal(first.iloc[0].to_numpy(), first.iloc[1].to_numpy())
    probabilities = first.filter(like="return_probability").to_numpy()
    assert (np.diff(probabilities, axis=1) >= -1e-9).all()
    ood = row.copy()
    ood["annual_km_baseline"] = 500000
    output, warnings = predictor.predict(ood)
    assert warnings
    assert np.isfinite(output.to_numpy()).all()


def test_shadow_artifact_manifest_matches_all_files() -> None:
    manifest = json.loads((MODEL_DIR / "artifact_manifest.json").read_text())
    for filename, expected in manifest.items():
        assert _sha256(MODEL_DIR / filename) == expected


def test_comparison_keeps_v2_1_in_production() -> None:
    comparison = json.loads((ROOT / "reports/v2_1_vs_v2_2_comparison.json").read_text())
    assert comparison["decision"] == "CHALLENGER_ACCEPTED"
    assert comparison["production"] == "V2.1 REMAINS PRODUCTION CHAMPION"
    assert comparison["real_fleet_validation"] == "PENDING"
    assert all(comparison["all_v2_2_acceptance_gates"].values())
