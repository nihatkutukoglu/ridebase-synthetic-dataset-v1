"""V1 natural-input scenario API contract."""
from __future__ import annotations

import datetime as dt

import pytest


def _payload(**updates):
    today = dt.date.today()
    payload = {
        "brand": "Yamaha",
        "model_id": "YAMAHA_NMAX125",
        "production_year": min(2024, today.year),
        "snapshot_date": today.isoformat(),
        "current_odometer_km": 12_000,
        "annual_km_baseline": 10_000,
        "usage_type": "COMMUTER",
        "riding_intensity": "MEDIUM",
        "last_service_date": (today - dt.timedelta(days=90)).isoformat(),
        "last_service_odometer_km": 9_000,
    }
    payload.update(updates)
    return payload


def test_v1_catalog_has_natural_input_options(client):
    response = client.get("/api/v1/motorcycle-models")
    assert response.status_code == 200
    body = response.json()
    assert body["consumer"] == "V1_SCENARIO"
    assert body["brand_count"] == 12
    assert body["model_count"] == 39
    assert "COMMUTER" in body["input_options"]["usage_type"]
    assert set(body["input_options"]["riding_intensity"]) == {"LOW", "MEDIUM", "HIGH"}


@pytest.mark.needs_models
def test_v1_scenario_returns_real_frozen_prediction_and_target_coverage(client, store):
    response = client.post("/api/v1/predict/scenario", json=_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "V1_SCENARIO_PARTIAL"
    assert body["prediction"]["next_service_days"] >= 0
    assert body["prediction"]["next_service_km"] >= 0
    assert body["derived"]["estimated_service_date"]
    assert body["derived"]["estimated_service_odometer_km"] >= 12_000
    assert body["decision"]["show_v1_point_estimate"] is True
    assert body["decision"]["prediction_scope"] == "PARTIAL_INPUT_SCENARIO"
    assert body["coverage"]["days"]["total"] == len(store.bundles["days"].feature_cols) == 114
    assert body["coverage"]["km"]["total"] == len(store.bundles["km"].feature_cols) == 113
    assert body["coverage"]["union"]["total"] == len({
        *store.bundles["days"].feature_cols, *store.bundles["km"].feature_cols,
    }) == 119
    provenance = {row["feature"]: row for row in body["provenance"]}
    assert provenance["brand"]["source"] == "MODEL_MASTER"
    assert provenance["annual_km_baseline"]["source"] == "USER_INPUT"
    assert provenance["snapshot_odometer_km"]["source"] == "USER_INPUT"
    assert provenance["days_since_previous_service"]["source"] == "DERIVED"
    assert {row["source"] for row in body["provenance"]} <= {
        "USER_INPUT", "MODEL_MASTER", "DERIVED", "MISSING_PREPROCESSOR",
    }


@pytest.mark.needs_models
def test_v1_scenario_is_deterministic(client):
    first = client.post("/api/v1/predict/scenario", json=_payload()).json()
    second = client.post("/api/v1/predict/scenario", json=_payload()).json()
    assert first["prediction"] == second["prediction"]
    assert first["derived"] == second["derived"]
    assert first["coverage"] == second["coverage"]


@pytest.mark.needs_models
def test_v1_scenario_never_uses_demo_sample(client, monkeypatch):
    import app.routes as routes

    def forbidden(*_args, **_kwargs):
        raise AssertionError("V1 scenario must not consult the demo sample")

    monkeypatch.setattr(routes, "read_predictions", forbidden)
    response = client.post("/api/v1/predict/scenario", json=_payload())
    assert response.status_code == 200
    assert response.json()["prediction"] is not None


@pytest.mark.needs_models
def test_missing_service_history_suppresses_v1_scenario_prediction(client):
    response = client.post(
        "/api/v1/predict/scenario",
        json=_payload(last_service_date=None, last_service_odometer_km=None),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["maintenance"]["status"] == "UNKNOWN"
    assert body["prediction"] is None
    assert body["derived"] is None
    assert body["decision"]["show_v1_point_estimate"] is False
    assert "tamamlanmadan" in body["decision"]["v1_suppressed_reason"]


@pytest.mark.needs_models
def test_overdue_policy_suppresses_future_v1_timing(client):
    today = dt.date.today()
    response = client.post(
        "/api/v1/predict/scenario",
        json=_payload(
            brand="Bajaj",
            model_id="BAJAJ_NS200",
            production_year=2020,
            current_odometer_km=15_000,
            last_service_odometer_km=9_000,
            last_service_date=(today - dt.timedelta(days=30)).isoformat(),
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["maintenance"]["status"] == "OVERDUE"
    assert body["maintenance"]["action"] == "SERVICE_NOW_REQUIRED"
    assert body["prediction"] is None
    assert body["derived"] is None
    assert body["decision"]["primary_source"] == "DETERMINISTIC_MAINTENANCE_POLICY"
    assert body["decision"]["show_v1_point_estimate"] is False


@pytest.mark.parametrize(
    "updates",
    [
        {"brand": "Honda"},
        {"last_service_odometer_km": 13_000},
        {"snapshot_date": (dt.date.today() + dt.timedelta(days=1)).isoformat()},
        {"last_service_date": (dt.date.today() + dt.timedelta(days=1)).isoformat()},
        {"unknown_feature": "not allowed"},
    ],
)
def test_v1_scenario_rejects_invalid_natural_inputs(client, updates):
    response = client.post("/api/v1/predict/scenario", json=_payload(**updates))
    assert response.status_code in {422, 503}
