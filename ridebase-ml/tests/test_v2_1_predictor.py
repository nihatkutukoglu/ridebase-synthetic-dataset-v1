"""V2.1 packaged predictor — golden parity + behavioural invariants."""
import json
from pathlib import Path

import numpy as np
import pytest

from ridebase_ml.v2_1.golden_parity import run as run_parity
from ridebase_ml.v2_1.predictor import PredictionError, V21SurvivalPredictor
from ridebase_ml.v2_1.scenario import derive

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "ridebase-ml/models/v2_1_v1_4"
pytestmark = pytest.mark.skipif(
    not (MODEL_DIR / "champion_model.joblib").exists(),
    reason="V2.1 Phase-3 artifacts not present",
)


@pytest.fixture(scope="module")
def predictor():
    return V21SurvivalPredictor.load(MODEL_DIR)


@pytest.fixture(scope="module")
def sample_row():
    import pandas as pd

    from ridebase_ml.v2_1.landmarks import FEATURE_COLUMNS

    frame = pd.read_parquet(
        ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet",
        filters=[("modeling_role", "==", "TEST")], columns=FEATURE_COLUMNS,
    )
    return frame.iloc[0].astype(object).where(frame.iloc[0].notna(), None).to_dict()


def test_golden_parity_reproduces_frozen_test_predictions():
    result = run_parity(sample=4000)
    assert result["parity_pass"], result
    assert result["max_probability_delta"] < 5e-4
    assert result["deterministic"] and result["horizon_monotonic"]


def test_horizon_monotonic_and_deterministic(predictor, sample_row):
    a = predictor.predict([sample_row])["predictions"][0]
    b = predictor.predict([sample_row])["predictions"][0]
    assert a == b
    seq = [a[f"risk_{h}d"] for h in (30, 60, 90, 120)]
    assert seq == sorted(seq)
    assert all(0.0 <= v <= 1.0 for v in seq)


def test_leakage_and_target_keys_rejected(predictor, sample_row):
    for bad in ("duration_days", "event_observed", "next_service_id", "event_within_30d",
                "primary_split", "administrative_cutoff_at"):
        with pytest.raises(PredictionError):
            predictor.predict([{**sample_row, bad: 1}])


def test_missing_features_warn_not_crash(predictor):
    out = predictor.predict([{"annual_km_baseline": 8000.0}])["predictions"][0]
    assert 0.0 <= out["risk_90d"] <= 1.0
    assert out["warnings"] and "missing" in out["warnings"][0]


def test_scenario_never_maps_odometer_to_initial_mileage():
    derived = derive({
        "model_id": "HONDA_PCX125", "landmark_date": "2026-03-15",
        "current_odometer_km": 18000, "annual_km_baseline": 9000,
        "last_service_date": "2025-06-01", "last_service_odometer_km": 9000,
    })
    f, prov = derived["features"], derived["provenance"]
    assert "initial_mileage_km" not in f
    assert f["current_odometer_km_at_landmark"] == 18000
    assert prov["current_odometer_km_at_landmark"] == "USER_INPUT"
    assert f["km_since_last_service"] == 9000 and prov["km_since_last_service"] == "LANDMARK_DERIVED"
    assert prov["oem_interval_km"] == "POLICY_DERIVED"
    assert f["max_due_ratio"] > 0


def test_scenario_rejects_impossible_history():
    with pytest.raises(Exception):
        derive({"model_id": "HONDA_PCX125", "landmark_date": "2026-03-15",
                "current_odometer_km": 5000, "last_service_odometer_km": 9000})


def test_median_service_days_consistent_with_calibrated_horizons(predictor):
    """FAZ2/K1: median_service_days must come off the same calibrated curve as
    risk_Xd. For 200 random scenarios: median is None, or median <= the
    smallest horizon whose calibrated risk is already >= 0.5."""
    import pandas as pd

    from ridebase_ml.v2_1.landmarks import FEATURE_COLUMNS

    frame = pd.read_parquet(
        ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet",
        filters=[("modeling_role", "==", "TEST")], columns=FEATURE_COLUMNS,
    ).sample(200, random_state=42)
    rows = frame.astype(object).where(frame.notna(), None).to_dict("records")
    preds = predictor.predict(rows)["predictions"]
    checked_a_reachable_case = False
    for p in preds:
        med = p["median_service_days"]
        horizons_ge_half = [h for h in (30, 60, 90, 120) if p[f"risk_{h}d"] >= 0.5]
        if med is None:
            assert not horizons_ge_half, p
        else:
            checked_a_reachable_case = True
            assert horizons_ge_half and med <= min(horizons_ge_half) + 1e-6, p
    assert checked_a_reachable_case, "sample never crossed 0.5 -- invariant untested on its true branch"


def test_km_pressure_moves_risk(predictor, sample_row):
    """Raising km-since / due-ratio must not leave 90d risk flat (V2.0 failure)."""
    def at(km):
        row = dict(sample_row)
        row["km_since_last_service"] = km
        row["km_due_ratio"] = km / max(float(row.get("oem_interval_km") or 6000), 1)
        row["max_due_ratio"] = max(float(row.get("days_due_ratio") or 0), row["km_due_ratio"])
        return predictor.predict([row])["predictions"][0]["risk_90d"]

    low, high = at(500), at(20000)
    assert high - low >= 0.05, (low, high)
