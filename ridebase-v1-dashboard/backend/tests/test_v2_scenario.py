"""Catalog + honest partial-snapshot scenario contract."""
from __future__ import annotations

import datetime as dt

from app.v2_schemas import V2ScenarioRequest
from app.v2_scenario import derive_scenario
from app.v2_service import get_predictor


def _payload(**updates):
    today = dt.date.today()
    base = {
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
    base.update(updates)
    return base


def test_motorcycle_catalog_inventory_and_brand_filtering(client):
    response = client.get("/api/v2/motorcycle-models")
    assert response.status_code == 200
    body = response.json()
    assert body["brand_count"] == 12
    assert body["model_count"] == 39
    assert len(body["models"]) == 39
    assert all(model["brand"] == "Honda" for model in body["models"] if model["brand"] == "Honda")
    assert {model["brand"] for model in body["models"]} == set(body["brands"])


def test_model_master_specs_are_resolved_from_selected_model(client):
    models = client.get("/api/v2/motorcycle-models").json()["models"]
    nmax = next(model for model in models if model["model_id"] == "YAMAHA_NMAX125")
    assert nmax["brand"] == "Yamaha"
    assert nmax["model_name"] == "NMAX 125"
    assert nmax["engine_displacement_cc"] == 125
    assert nmax["category"] == "SCOOTER"
    assert nmax["powertrain_type"] == "ICE"
    assert nmax["final_drive_type"] == "V_BELT"
    em1 = next(model for model in models if model["model_id"] == "HONDA_EM1E")
    assert em1["powertrain_type"] == "EV"
    assert em1["fuel_type"] == "ELECTRIC"
    assert em1["cooling_type"] == "NONE"
    assert em1["transmission_type"] == "DIRECT_DRIVE"


def test_demo_sample_has_separate_human_identity_and_current_odometer(client):
    body = client.get("/api/v2/sample").json()
    assert body["display"]["model_name"]
    assert body["display"]["model_id"]
    assert body["display"]["snapshot_odometer_km"] >= 0
    assert body["display"]["days_since_previous_service"] >= 0
    assert "model_name" not in body["features"]
    assert "model_id" not in body["features"]


def test_scenario_derivation_is_deterministic_and_has_full_provenance():
    req = V2ScenarioRequest.model_validate(_payload())
    first = derive_scenario(req, get_predictor())
    second = derive_scenario(req, get_predictor())
    assert first["features"] == second["features"]
    assert first["coverage"] == second["coverage"]
    assert len(first["provenance"]) == first["coverage"]["total"] == 117
    assert first["features"]["days_since_previous_service"] == 90
    assert first["features"]["km_since_previous_service"] == 3_000
    assert first["features"]["avg_km_per_day_since_previous_service"] == 3_000 / 90
    assert first["features"]["brand"] == "Yamaha"
    assert first["origins"]["brand"]["source"] == "MODEL_MASTER"
    assert first["origins"]["production_year"]["source"] == "USER_INPUT"


def test_scenario_never_uses_sample_snapshot(client, monkeypatch):
    predictor = get_predictor()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("scenario must not consult a sample motorcycle")

    monkeypatch.setattr(type(predictor), "sample_snapshot", forbidden)
    response = client.post("/api/v2/predict/scenario", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "SCENARIO_PARTIAL"
    assert {row["source"] for row in body["provenance"]} <= {
        "USER_INPUT", "MODEL_MASTER", "DERIVED", "MISSING_PREPROCESSOR",
    }
    assert "MISSING_PREPROCESSOR" in {row["source"] for row in body["provenance"]}


def test_invalid_brand_model_pair_rejected(client):
    response = client.post("/api/v2/predict/scenario", json=_payload(brand="Honda"))
    assert response.status_code == 422
    assert "brand/model" in response.json()["detail"]


def test_last_service_odometer_cannot_exceed_current(client):
    response = client.post(
        "/api/v2/predict/scenario",
        json=_payload(current_odometer_km=8_000, last_service_odometer_km=9_000),
    )
    assert response.status_code == 422


def test_future_dates_rejected(client):
    future = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    assert client.post("/api/v2/predict/scenario", json=_payload(snapshot_date=future)).status_code == 422
    assert client.post("/api/v2/predict/scenario", json=_payload(last_service_date=future)).status_code == 422


def test_scenario_unknown_or_leakage_fields_rejected(client):
    assert client.post("/api/v2/predict/scenario",
                       json=_payload(totally_made_up=1)).status_code == 422
    assert client.post("/api/v2/predict/scenario",
                       json=_payload(event_observed=1)).status_code == 422


def test_scenario_probability_contract_and_coverage(client):
    response = client.post("/api/v2/predict/scenario", json=_payload())
    assert response.status_code == 200
    body = response.json()
    risks = [body["v2"][f"risk_{h}d"] for h in (30, 60, 90, 120)]
    assert all(0 <= value <= 1 for value in risks)
    assert risks == sorted(risks)
    assert body["coverage"]["known_or_derived"] < body["coverage"]["total"] == 117
    assert body["coverage"]["verdict"] == "LIMITED_INFORMATION"


def test_low_confidence_model_year_mapping_warns_but_does_not_rewrite(client):
    response = client.post("/api/v2/predict/scenario", json=_payload(production_year=1999))
    assert response.status_code == 200
    body = response.json()
    assert body["selected_motorcycle"]["year_range_confidence"] == "LOW"
    assert any("outside the catalog range" in warning for warning in body["warnings"])
