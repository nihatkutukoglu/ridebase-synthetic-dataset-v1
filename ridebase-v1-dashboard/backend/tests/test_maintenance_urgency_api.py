"""Test maintenance urgency integration in backend scenario endpoint."""
from datetime import date
import math

from fastapi.testclient import TestClient
import pytest

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
    assert m["progress_ratio"] == 10.0
    assert m["km_progress_ratio"] == 10.0
    assert m["time_progress_ratio"] == pytest.approx(34 / 182.62, abs=1e-4)
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


@pytest.mark.parametrize(
    ("case_name", "progress_ratio", "expected_level"),
    [
        ("normal", 0.30, "NORMAL"),
        ("near_due", 0.90, "YAKLAŞIYOR"),
        ("due", 1.00, "GECİKMİŞ"),
        ("overdue", 1.50, "ÇOK GECİKMİŞ"),
        ("severe_overdue", 5.00, "KRİTİK"),
    ],
)
def test_scenario_urgency_api_contract(case_name, progress_ratio, expected_level):
    payload = {
        "brand": "Bajaj",
        "model_id": "BAJAJ_NS200",
        "production_year": 2020,
        "snapshot_date": "2024-08-01",
        "current_odometer_km": 12000 + progress_ratio * 3000,
        "annual_km_baseline": 10000,
        "last_service_date": "2024-07-31",
        "last_service_odometer_km": 12000,
    }
    response = client.post("/api/v2/predict/scenario", json=payload)
    assert response.status_code == 200, case_name
    maintenance = response.json()["maintenance"]

    score = maintenance["maintenance_urgency_score"]
    assert isinstance(score, (int, float)) and not isinstance(score, bool)
    assert 0 <= score <= 100
    assert maintenance["maintenance_urgency_level"] == expected_level
    assert maintenance["maintenance_urgency_level"] in {
        "NORMAL", "YAKLAŞIYOR", "GECİKMİŞ", "ÇOK GECİKMİŞ", "KRİTİK"
    }
    assert isinstance(maintenance["maintenance_urgency_reason"], str)
    assert maintenance["maintenance_urgency_reason"].strip()
    assert maintenance["determining_dimension"] in {"KM", "TIME", "BOTH"}
    assert math.isfinite(maintenance["progress_ratio"])
    assert maintenance["progress_ratio"] >= 0
    assert maintenance["km_progress_ratio"] == pytest.approx(progress_ratio, abs=1e-4)
    assert math.isfinite(maintenance["time_progress_ratio"])
