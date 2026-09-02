"""V2.1 dynamic-landmark survival API. Self-skips when the Phase-3 artifacts are absent."""
from __future__ import annotations

import pytest

from app.config import settings

_ARTIFACTS_OK = (settings.MODEL_DIR / "v2_1_v1_4" / "champion_model.joblib").exists()
pytestmark = pytest.mark.skipif(not _ARTIFACTS_OK, reason="V2.1 Phase-3 artifacts not present")


@pytest.fixture(scope="module")
def sample(client):
    r = client.get("/api/v2_1/sample")
    assert r.status_code == 200
    return r.json()["features"]


def test_health_reports_v2_1(client):
    h = client.get("/health").json()
    assert h["v2_1_model_loaded"] is True
    assert h["v2_1_status"] == "ok"
    assert h["v2_1_real_fleet_validation"] == "PENDING"
    # V1 / V2.0 untouched
    assert h["v1"] == "ok"


def test_model_info(client):
    mi = client.get("/api/v2_1/model/info").json()
    assert mi["champion"] == "xgb_cox"
    assert mi["calibration_method"] == "isotonic"
    assert mi["model_validation"] == "SYNTHETICALLY_VALIDATED"
    assert mi["real_fleet_validation"] == "PENDING"
    assert "NOT" in mi["not_target"]


def test_features_contract(client):
    fe = client.get("/api/v2_1/features").json()
    assert fe["feature_count"] == len(fe["contract"]) == 54
    assert "primary_split" not in fe["contract"]
    assert not any("year" in c for c in fe["contract"])


def test_predict_shape_and_bounds(client, sample):
    r = client.post("/api/v2_1/predict", json={"features": sample})
    assert r.status_code == 200
    p = r.json()["prediction"]
    seq = [p[f"risk_{h}d"] for h in (30, 60, 90, 120)]
    assert seq == sorted(seq)
    assert all(0.0 <= v <= 1.0 for v in seq)
    assert "BEKLENİYOR" in r.json()["warning"]
    assert "NOT maintenance" in r.json()["risk_meaning"]


def test_deterministic(client, sample):
    a = client.post("/api/v2_1/predict", json={"features": sample}).json()["prediction"]
    b = client.post("/api/v2_1/predict", json={"features": sample}).json()["prediction"]
    assert a == b


@pytest.mark.parametrize("bad", [
    {"duration_days": 12}, {"event_observed": 1}, {"next_service_id": "x"},
    {"event_within_90d": 1}, {"primary_split": "TEST"}, {"administrative_cutoff_at": "2026-01-01"},
])
def test_leakage_rejected(client, sample, bad):
    r = client.post("/api/v2_1/predict", json={"features": {**sample, **bad}})
    assert r.status_code == 422


def test_batch(client, sample):
    r = client.post("/api/v2_1/predict/batch", json={"items": [sample] * 25})
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 25 and len(body["predictions"]) == 25


def test_scenario_partial_no_overlay(client):
    r = client.post("/api/v2_1/predict/scenario", json={
        "brand": "Honda", "model_id": "HONDA_PCX125", "production_year": 2022,
        "landmark_date": "2026-03-15", "current_odometer_km": 18000,
        "annual_km_baseline": 9000, "usage_type": "COMMUTE", "riding_intensity": "MODERATE",
        "last_service_date": "2025-06-01", "last_service_odometer_km": 9000,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "KISMİ BİLGİYLE SENARYO TAHMİNİ"
    assert body["provenance"]["current_odometer_km_at_landmark"] == "USER_INPUT"
    assert "initial_mileage_km" not in body["resolved_features"]
    assert body["feature_coverage"]["resolved"] < body["feature_coverage"]["contract"]
    seq = [body["prediction"][f"risk_{h}d"] for h in (30, 60, 90, 120)]
    assert seq == sorted(seq)


def test_scenario_rejects_extra_feature_map(client):
    r = client.post("/api/v2_1/predict/scenario", json={
        "brand": "Honda", "model_id": "HONDA_PCX125", "landmark_date": "2026-03-15",
        "features": {"km_due_ratio": 5.0},
    })
    assert r.status_code == 422


def test_metrics_artifact_driven(client):
    m = client.get("/api/v2_1/metrics").json()
    assert m["status"] == "PASS"
    assert m["real_fleet_validation"] == "PENDING"
    assert m["golden_prediction_parity"]["parity_pass"] is True
    assert m["test_metrics"]["ipcw_c_index"] > 0.7
