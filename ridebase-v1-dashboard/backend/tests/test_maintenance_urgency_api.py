"""Test maintenance urgency integration in backend scenario endpoint."""
from datetime import date
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_scenario_returns_deterministic_urgency():
    payload = {
        "brand": "Bajaj",
        "model_id": "BAJAJ_NS200",
        "production_year": 2020,
        "snapshot_date": "2024-08-01",
        "current_odometer_km": 42000,
        "annual_km_baseline": 10000,
        "usage_type": "COMMUTER",
        "riding_intensity": "MEDIUM",
        "last_service_date": "2024-06-28",
        "last_service_odometer_km": 12000,
    }
    response = client.post("/api/v2/predict/scenario", json=payload)
    assert response.status_code == 200
    data = response.json()
    m = data["maintenance"]
    assert "urgency" in m
    assert m["maintenance_urgency_score"] == 100
    assert m["maintenance_urgency_level"] == "KRİTİK"
    assert "27.000 km gecikmiş" in m["maintenance_urgency_reason"]
    assert m["determining_dimension"] == "KM"
    assert m["status"] == "OVERDUE"
    assert m["action_label"] == "SERVİS ŞİMDİ GEREKLİ"


def test_scenario_urgency_approaching():
    # 2500 km on 3000 km interval -> progress ratio 2500/3000 ~ 0.833 -> DUE_SOON / YAKLAŞIYOR
    payload = {
        "brand": "Bajaj",
        "model_id": "BAJAJ_NS200",
        "production_year": 2020,
        "snapshot_date": "2024-08-01",
        "current_odometer_km": 14500,
        "annual_km_baseline": 10000,
        "last_service_date": "2024-06-01",
        "last_service_odometer_km": 12000,
    }
    response = client.post("/api/v2/predict/scenario", json=payload)
    assert response.status_code == 200
    m = response.json()["maintenance"]
    assert m["status"] == "DUE_SOON"
    assert m["maintenance_urgency_level"] == "YAKLAŞIYOR"
    assert 25 <= m["maintenance_urgency_score"] < 50
