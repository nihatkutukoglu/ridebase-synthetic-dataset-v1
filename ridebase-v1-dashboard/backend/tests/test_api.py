"""API + inference contract tests."""
import math

import pytest


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    b = r.json()
    assert b["status"] in ("ok", "degraded")
    assert b["days_model_loaded"] is True
    assert b["km_model_loaded"] is True
    assert b["dataset_version"]


@pytest.mark.needs_models
def test_model_loading(store):
    assert store.bundles["days"].ok and store.bundles["km"].ok
    assert store.bundles["days"].model is not None
    assert store.bundles["km"].model is not None
    assert store.leakage_report["status"] == "PASS"


@pytest.mark.needs_models
def test_model_info(client):
    b = client.get("/api/v1/model/info").json()
    assert b["dataset_version"]
    assert b["feature_count_days"] > 50
    assert b["feature_count_km"] > 50
    assert b["production_validation_status"].startswith("PENDING")
    assert "synthetic" in b["synthetic_validation"].lower()


@pytest.mark.needs_models
def test_features_endpoint(client):
    b = client.get("/api/v1/features").json()
    assert b["count"] == len(b["features"])
    assert b["leakage_guard"]["status"] == "PASS"
    names = {f["name"] for f in b["features"]}
    for leak in ("next_service_days", "km_to_next_service", "days_to_next_service"):
        assert leak not in names
    simple = client.get("/api/v1/features?mode=simple").json()
    assert 0 < simple["count"] < b["count"]


@pytest.mark.needs_models
def test_feature_order_preserved(store):
    """The model must receive columns in its trained order."""
    import pandas as pd
    from app.predictor import _predict_one_target

    for tgt in ("days", "km"):
        b = store.bundles[tgt]
        row = pd.DataFrame([{c: 1.0 for c in b.feature_cols}])
        # reindex inside _predict_one_target must yield exactly feature_cols, in order
        sub = row.reindex(columns=b.feature_cols)
        assert list(sub.columns) == list(b.feature_cols)
        val = _predict_one_target(b, row)
        assert isinstance(val, float) and math.isfinite(val) and val >= 0.0


@pytest.mark.needs_models
def test_valid_prediction(client, sample_payload):
    r = client.post("/api/v1/predict", json=sample_payload)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["prediction"]["next_service_days"] >= 0
    assert b["prediction"]["next_service_km"] >= 0
    assert b["warning"].lower().startswith("model developed on synthetic")
    if sample_payload["snapshot_date"]:
        assert b["derived"]["estimated_service_date"] is not None
    assert b["model"]["deterministic"] is True


@pytest.mark.needs_models
def test_deterministic_prediction(client, sample_payload):
    a = client.post("/api/v1/predict", json=sample_payload).json()
    b = client.post("/api/v1/predict", json=sample_payload).json()
    assert a["prediction"] == b["prediction"]


@pytest.mark.needs_models
def test_missing_input_is_imputed(client):
    """A near-empty payload must still return a prediction (preprocessor imputes)."""
    r = client.post("/api/v1/predict", json={"features": {"brand": "Yamaha"},
                                             "snapshot_date": "2026-01-15", "strict": False})
    assert r.status_code == 200, r.text
    assert r.json()["prediction"]["next_service_days"] >= 0


@pytest.mark.needs_models
def test_invalid_input_rejected(client):
    r = client.post("/api/v1/predict", json={"features": {"snapshot_odometer_km": -5}})
    assert r.status_code == 422
    r2 = client.post("/api/v1/predict", json={"features": {"brand": "NotARealBrand"}})
    assert r2.status_code == 422


def test_leakage_field_rejected(client):
    r = client.post("/api/v1/predict",
                    json={"features": {"next_service_days": 10, "brand": "Yamaha"}})
    assert r.status_code == 422


@pytest.mark.needs_models
def test_ood_warning(client):
    r = client.post("/api/v1/predict", json={
        "features": {"brand": "Yamaha", "snapshot_odometer_km": 5_000_000,
                     "recent_90d_km": 900_000},
        "snapshot_date": "2026-02-01", "strict": False})
    assert r.status_code == 200
    ood = r.json()["input_diagnostics"]["out_of_distribution"]
    assert any(f["field"] == "snapshot_odometer_km" for f in ood)


@pytest.mark.needs_models
def test_analytics_endpoints(client):
    for path in ("overview", "models", "features", "errors", "drift", "experiments", "verdict"):
        r = client.get(f"/api/v1/analytics/{path}")
        assert r.status_code == 200, path
        assert "available" in r.json()
    for tgt in ("DAYS", "KM"):
        r = client.get(f"/api/v1/analytics/target/{tgt}")
        assert r.status_code == 200
