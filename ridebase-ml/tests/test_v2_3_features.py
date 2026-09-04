import json
from pathlib import Path

import pandas as pd

from ridebase_ml.v2_3.features import FEATURE_COLUMNS, NEW_FEATURES


ROOT = Path(__file__).resolve().parents[2]
ML = ROOT / "ridebase-ml"


def test_feature_contract_extends_frozen_60_without_forbidden_fields():
    assert len(FEATURE_COLUMNS) == 95
    assert len(NEW_FEATURES) == 35
    forbidden = ("latent", "target", "censor", "days_observed", "split", "year", "future")
    assert not [name for name in FEATURE_COLUMNS if any(token in name.lower() for token in forbidden)]


def test_modeling_table_has_no_latent_predictor_and_preserves_rows():
    frame = pd.read_parquet(ML / "derived_outputs/v2_3_v1_5/v2_3_modeling_table.parquet")
    assert len(frame) == 259804
    assert set(FEATURE_COLUMNS).issubset(frame.columns)
    assert not any("latent" in name.lower() for name in frame.columns)


def test_parity_and_future_injection_gate_passed():
    report = json.loads((ML / "reports/v2_3_feature_parity.json").read_text())
    assert report["status"] == "PASS"
    assert report["golden_landmarks"] >= 300
    assert report["classification_counts"].get("MISMATCH", 0) == 0
    assert all(report["future_injection"].values())


def test_observability_audit_never_promotes_latent_profile():
    report = json.loads((ML / "reports/v2_3_observability_gap.json").read_text())
    assert report["status"] == "PASS"
    assert report["hidden_profile_use"] == "AUDIT_ONLY_NOT_A_PREDICTOR"
