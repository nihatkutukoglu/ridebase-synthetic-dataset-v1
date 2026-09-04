"""Prompt-4 API gates for POST /api/v2_1/predict/by-motorcycle."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from app.config import settings
from app.v2_1_service import _STATE, get_history_adapter, predict_by_motorcycle

ROOT = Path(__file__).resolve().parents[3]
_READY = (
    (settings.MODEL_DIR / "v2_1_v1_4/champion_model.joblib").exists()
    and settings.V2_1_HISTORY_SOURCE_DIR.exists()
)
pytestmark = pytest.mark.skipif(not _READY, reason="V2.1 model/history source not present")

RICH = {"motorcycle_id": "MC000001", "landmark_date": "2024-07-31"}
SPARSE = {"motorcycle_id": "MC000001", "landmark_date": "2024-06-25"}


def prediction_sequence(body):
    return [body["prediction"][f"risk_{h}d"] for h in (30, 60, 90, 120)]


def without_latency(body):
    return {key: value for key, value in body.items() if key != "latency_ms"}


def all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_keys(child)


def test_by_motorcycle_rich_history_response_contract(client):
    response = client.post("/api/v2_1/predict/by-motorcycle", json=RICH)
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "HISTORY_PIPELINE"
    assert body["history_source"] == "SYNTHETIC_V1_4"
    assert body["context"]["motorcycle_id"] == RICH["motorcycle_id"]
    assert body["context"]["landmark_date"] == RICH["landmark_date"]
    assert body["context"]["current_odometer_km"] == 86194
    assert body["context"]["last_eligible_service_date"] <= RICH["landmark_date"]
    assert body["feature_metadata"]["resolved_count"] == 54
    assert body["feature_metadata"]["contract_count"] == 54
    assert body["feature_metadata"]["missing_features"] == []
    assert body["feature_metadata"]["coverage_is_confidence"] is False
    assert prediction_sequence(body) == sorted(prediction_sequence(body))


def test_by_motorcycle_unknown_is_404(client):
    response = client.post("/api/v2_1/predict/by-motorcycle", json={
        "motorcycle_id": "MC_DOES_NOT_EXIST", "landmark_date": "2026-01-31",
    })
    assert response.status_code == 404
    assert "unknown motorcycle_id" in response.json()["detail"]


def test_by_motorcycle_before_observation_is_422(client):
    response = client.post("/api/v2_1/predict/by-motorcycle", json={
        "motorcycle_id": "MC000001", "landmark_date": "2020-01-01",
    })
    assert response.status_code == 422


def test_by_motorcycle_sparse_history_is_honestly_missing(client):
    response = client.post("/api/v2_1/predict/by-motorcycle", json=SPARSE)
    assert response.status_code == 200
    body = response.json()
    assert body["context"]["current_odometer_km"] is None
    assert body["context"]["last_eligible_service_date"] is None
    assert body["feature_metadata"]["resolved_count"] < 54
    assert "current_odometer_km_at_landmark" in body["feature_metadata"]["missing_features"]
    assert any("No mileage history" in warning for warning in body["warnings"])
    assert prediction_sequence(body) == sorted(prediction_sequence(body))


@pytest.mark.parametrize("payload", [
    RICH,
    {"motorcycle_id": "MC000001", "landmark_date": "2025-12-31"},
    {"motorcycle_id": "MC000002", "landmark_date": "2026-06-30"},
])
def test_by_motorcycle_old_and_recent_landmarks_are_deterministic(client, payload):
    first = client.post("/api/v2_1/predict/by-motorcycle", json=payload)
    second = client.post("/api/v2_1/predict/by-motorcycle", json=payload)
    assert first.status_code == second.status_code == 200
    assert without_latency(first.json()) == without_latency(second.json())


def test_by_motorcycle_existing_future_history_does_not_leak(client):
    adapter = get_history_adapter()
    future_services = adapter.get_services_before("MC000001", dt.date(2026, 7, 31))
    assert any(row["_effective_at"] > RICH["landmark_date"] for row in future_services)
    body = client.post("/api/v2_1/predict/by-motorcycle", json=RICH).json()
    assert body["context"]["last_eligible_service_date"] <= RICH["landmark_date"]
    assert body["context"]["current_odometer_source_date"] <= RICH["landmark_date"]


def test_by_motorcycle_golden_direct_api_probability_parity(client):
    report = json.loads((ROOT / "ridebase-ml/reports/v2_1_history_feature_parity.json").read_text())
    import pandas as pd

    ids = report["golden_landmarks"]["ids"][:5]
    table = pd.read_parquet(
        ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet",
        filters=[("landmark_id", "in", ids)], columns=["landmark_id", "motorcycle_id", "landmark_at"],
    ).set_index("landmark_id")
    for landmark_id in ids:
        row = table.loc[landmark_id]
        payload = {
            "motorcycle_id": row["motorcycle_id"],
            "landmark_date": row["landmark_at"].date().isoformat(),
        }
        direct = predict_by_motorcycle(**payload)["prediction"]
        api = client.post("/api/v2_1/predict/by-motorcycle", json=payload).json()["prediction"]
        assert api == {key: direct[key] for key in api}


def test_by_motorcycle_source_status_and_risk_meaning_are_explicit(client):
    body = client.post("/api/v2_1/predict/by-motorcycle", json=RICH).json()
    assert body["model_status"] == "V2.1 EXPERIMENTAL LIVE"
    assert body["model_validation"] == "SYNTHETICALLY_VALIDATED"
    assert body["real_fleet_validation"] == "PENDING"
    assert "NOT maintenance-needed" in body["risk_meaning"]
    assert "not production-validated" in body["warning"]


def test_by_motorcycle_response_contains_no_raw_customer_personal_data(client):
    body = client.post("/api/v2_1/predict/by-motorcycle", json=RICH).json()
    forbidden = {"customer_id", "city", "preferred_contact", "synthetic_alias", "plate_synthetic", "vin_synthetic"}
    assert forbidden.isdisjoint(set(all_keys(body)))


def test_by_motorcycle_warm_route_does_not_reload_tables(client):
    adapter = get_history_adapter()
    client.post("/api/v2_1/predict/by-motorcycle", json=RICH)
    reads = adapter.cache_info()["disk_reads_by_table"]
    response = client.post("/api/v2_1/predict/by-motorcycle", json=RICH)
    assert response.status_code == 200
    assert adapter.cache_info()["disk_reads_by_table"] == reads
    assert response.json()["latency_ms"]["total_service"] < 500.0


def test_by_motorcycle_adapter_failure_returns_503_without_prediction(client, monkeypatch):
    monkeypatch.setitem(_STATE, "history_adapter", None)
    monkeypatch.setitem(_STATE, "history_error", "forced adapter failure")
    response = client.post("/api/v2_1/predict/by-motorcycle", json=RICH)
    assert response.status_code == 503
    assert "prediction" not in response.json()


def test_by_motorcycle_rejects_manual_feature_overlay(client):
    response = client.post("/api/v2_1/predict/by-motorcycle", json={
        **RICH, "features": {"max_due_ratio": 999},
    })
    assert response.status_code == 422


def test_scenario_route_remains_separate(client):
    response = client.post("/api/v2_1/predict/scenario", json={
        "brand": "Honda", "model_id": "HONDA_PCX125", "production_year": 2022,
        "landmark_date": "2026-03-15", "current_odometer_km": 18000,
        "last_service_date": "2025-06-01", "last_service_odometer_km": 9000,
    })
    assert response.status_code == 200
    assert response.json()["mode"] == "KISMİ BİLGİYLE SENARYO TAHMİNİ"


def test_sqlite_adapter_serving_mode_health(client):
    health = client.get("/health").json()
    assert health["v2_1_history_status"] == "ok"
    assert health["v2_1_history_source"] == "SYNTHETIC_V1_4"
    assert health["v2_1_history_adapter"] == "SQLITE"
    assert health["v2_1_history_store_loaded"] is True
    assert health["v2_1_history_store_version"] == "1.4.0"
    assert health["v2_1_history_store_hash"]


def test_sqlite_serving_does_not_read_csv_source_tables(client):
    adapter = get_history_adapter()
    assert adapter.adapter_type == "SQLITE"
    response = client.post("/api/v2_1/predict/by-motorcycle", json=RICH)
    assert response.status_code == 200
    info = adapter.cache_info()
    assert info["disk_reads"] == 0
    assert info["disk_reads_by_table"] == {}


def test_sample_motorcycle_id_works_end_to_end_with_by_motorcycle(client):
    """FAZ2/K2: GET /api/v2_1/sample's motorcycle_id must be a real, usable
    History Pipeline input -- this is what the 'Rastgele geçerli ID getir'
    button in the Control Center wires to."""
    sample = client.get("/api/v2_1/sample").json()
    assert sample["motorcycle_id"]
    response = client.post("/api/v2_1/predict/by-motorcycle", json={
        "motorcycle_id": sample["motorcycle_id"],
        "landmark_date": sample["landmark_at"],
    })
    assert response.status_code == 200, response.json()
    assert 0.0 <= response.json()["prediction"]["risk_90d"] <= 1.0
