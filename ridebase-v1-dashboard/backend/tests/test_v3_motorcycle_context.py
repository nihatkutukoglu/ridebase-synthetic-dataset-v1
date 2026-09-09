"""PIT, leakage and probability-parity gates for V3 response-only context."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import pytest

from app.config import settings

_READY = (settings.MODEL_DIR / "v3_research/champion_model.joblib").exists()
pytestmark = pytest.mark.skipif(not _READY, reason="V3 frozen artifacts not present")


@pytest.fixture(scope="module")
def known_pair(client):
    frame = pd.read_parquet(
        settings.MODEL_DIR.parent / "derived_outputs/v3/v3_sample_landmarks.parquet"
    ).sort_values(["motorcycle_id", "landmark_at"])
    row = frame.iloc[0]
    return str(row["motorcycle_id"]), pd.Timestamp(row["landmark_at"]).date()


def _context(client, motorcycle_id, landmark):
    response = client.post(
        "/api/v3/predict/by-motorcycle",
        json={"motorcycle_id": motorcycle_id, "landmark_date": landmark.isoformat()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_identity_maps_to_actual_v1_4_source(client, known_pair):
    motorcycle_id, landmark = known_pair
    payload = _context(client, motorcycle_id, landmark)
    context = payload["motorcycle_context"]
    source = pd.read_csv(
        settings.V2_1_HISTORY_SOURCE_DIR / "motorcycles.csv", low_memory=False
    )
    source.columns = [str(c).lstrip("\ufeff") for c in source.columns]
    expected = source.loc[source["motorcycle_id"] == motorcycle_id].iloc[0]
    assert context["brand"] == expected["brand"]
    assert context["model"] == expected["model_name"]
    assert context["model_year"] == int(expected["production_year"])
    assert context["category"] == expected["category"]


def test_odometer_and_last_service_are_exactly_pit_safe(client, known_pair):
    from app.v3_service import get_history_adapter

    motorcycle_id, landmark = known_pair
    payload = _context(client, motorcycle_id, landmark)
    context = payload["motorcycle_context"]
    provenance = payload["motorcycle_context_provenance"]
    adapter = get_history_adapter()

    mileage = [
        row for row in adapter.get_mileage_before(motorcycle_id, landmark)
        if row.get("closing_odometer_km") is not None
    ]
    latest_mileage = max(
        mileage, key=lambda row: (str(row["_effective_at"]), str(row.get("timeline_id", "")))
    )
    assert context["current_odometer_km"] == float(latest_mileage["closing_odometer_km"])
    assert date.fromisoformat(provenance["odometer_source"]["period_end_date"]) <= landmark

    services = [
        row for row in adapter.get_services_before(motorcycle_id, landmark)
        if str(row.get("status", "")).upper() == "DELIVERED"
    ]
    latest_service = max(
        services, key=lambda row: (str(row["_effective_at"]), str(row.get("service_id", "")))
    )
    assert context["last_service_date"] == latest_service["_effective_at"]
    assert context["last_service_odometer_km"] == float(latest_service["odometer_km"])
    assert date.fromisoformat(context["last_service_date"]) <= landmark
    assert context["days_since_last_service"] == (
        landmark - date.fromisoformat(context["last_service_date"])
    ).days
    assert context["km_since_last_service"] == (
        context["current_odometer_km"] - context["last_service_odometer_km"]
    )


def test_annual_usage_is_the_active_profile_value(client, known_pair):
    from app.v3_service import get_history_adapter

    motorcycle_id, landmark = known_pair
    context = _context(client, motorcycle_id, landmark)["motorcycle_context"]
    profile = get_history_adapter().get_usage_profile(motorcycle_id, landmark)
    assert profile is not None
    assert context["annual_usage_km"] == float(profile["annual_km_baseline"])
    assert pd.Timestamp(profile["profile_start_date"]).date() <= landmark


def test_future_injection_cannot_change_odometer_or_last_service(monkeypatch, known_pair):
    from app import v3_context
    from app.v3_service import get_history_adapter

    motorcycle_id, landmark = known_pair
    adapter = get_history_adapter()
    original, _, _ = v3_context.build_motorcycle_context(motorcycle_id, landmark, adapter)

    class FutureInjectedAdapter:
        def __getattr__(self, name):
            return getattr(adapter, name)

        def get_mileage_before(self, mid, as_of):
            return adapter.get_mileage_before(mid, as_of) + [{
                "timeline_id": "FUTURE",
                "_effective_at": (landmark + timedelta(days=30)).isoformat(),
                "closing_odometer_km": 9_999_999,
            }]

        def get_services_before(self, mid, as_of):
            return adapter.get_services_before(mid, as_of) + [{
                "service_id": "FUTURE",
                "_effective_at": (landmark + timedelta(days=30)).isoformat(),
                "received_at": (landmark + timedelta(days=30)).isoformat(),
                "odometer_km": 9_999_999,
                "status": "DELIVERED",
            }]

    injected, provenance, _ = v3_context.build_motorcycle_context(
        motorcycle_id, landmark, FutureInjectedAdapter()
    )
    for field in (
        "current_odometer_km", "last_service_date", "last_service_odometer_km",
        "km_since_last_service", "days_since_last_service",
    ):
        assert injected.get(field) == original.get(field)
    assert provenance["future_records_used"] is False


def test_t_minus_1_t_t_plus_1_context_boundaries(client, known_pair):
    motorcycle_id, landmark = known_pair
    for offset in (-1, 0, 1):
        at = landmark + timedelta(days=offset)
        response = client.post(
            "/api/v3/predict/by-motorcycle",
            json={"motorcycle_id": motorcycle_id, "landmark_date": at.isoformat()},
        )
        if response.status_code == 422:
            continue
        assert response.status_code == 200
        payload = response.json()
        context = payload["motorcycle_context"]
        provenance = payload["motorcycle_context_provenance"]
        assert context["landmark_date"] == at.isoformat()
        if provenance.get("odometer_source"):
            assert date.fromisoformat(provenance["odometer_source"]["period_end_date"]) <= at
        if context.get("last_service_date"):
            assert date.fromisoformat(context["last_service_date"]) <= at


def test_same_day_services_use_a_deterministic_id_tie_break(monkeypatch):
    from app import v3_context

    class SameDayAdapter:
        def get_motorcycle(self, *_):
            return {"motorcycle_id": "MCX", "observation_start_date": "2026-01-01"}

        def get_mileage_before(self, *_):
            return [{
                "timeline_id": "MTL1", "_effective_at": "2026-03-31",
                "closing_odometer_km": 1200,
            }]

        def get_services_before(self, *_):
            return [
                {"service_id": "SVC2", "_effective_at": "2026-03-31",
                 "status": "DELIVERED", "odometer_km": 1100},
                {"service_id": "SVC1", "_effective_at": "2026-03-31",
                 "status": "DELIVERED", "odometer_km": 1000},
            ]

        def get_usage_profile(self, *_):
            return None

    monkeypatch.setattr(v3_context, "_reference_identity", lambda _mid: ({}, {}))
    context, provenance, _ = v3_context.build_motorcycle_context(
        "MCX", date(2026, 3, 31), SameDayAdapter()
    )
    assert provenance["last_service_source"]["service_id"] == "SVC2"
    assert context["last_service_odometer_km"] == 1100
    assert context["days_since_last_service"] == 0
    assert context["km_since_last_service"] == 100


@pytest.mark.parametrize(
    "reference, expected",
    [
        ({"brand": "Bajaj", "model_name": "NS200", "production_year": 2022}, "Bajaj NS200 (2022) · MCX"),
        ({"brand": "Honda", "model_name": "PCX125"}, "Honda PCX125 · MCX"),
        ({"model_name": "NMAX 125"}, "NMAX 125 · MCX"),
        ({}, "MCX"),
    ],
)
def test_partial_identity_has_no_fabricated_fallback(monkeypatch, reference, expected):
    from app import v3_context

    class MinimalAdapter:
        def get_motorcycle(self, *_):
            return {"motorcycle_id": "MCX", "observation_start_date": "2026-01-01"}

        def get_mileage_before(self, *_):
            return []

        def get_services_before(self, *_):
            return []

        def get_usage_profile(self, *_):
            return None

    monkeypatch.setattr(v3_context, "_reference_identity", lambda _mid: (reference, {}))
    context, _, warnings = v3_context.build_motorcycle_context(
        "MCX", date(2026, 3, 31), MinimalAdapter()
    )
    assert v3_context.friendly_motorcycle_label(context) == expected
    for absent in (
        "current_odometer_km", "last_service_date", "last_service_odometer_km",
        "km_since_last_service", "annual_usage_km",
    ):
        assert absent not in context
    assert warnings
    assert "0 km" not in json.dumps(context)


def test_context_contains_no_future_target_or_task_metadata(client, known_pair):
    motorcycle_id, landmark = known_pair
    payload = _context(client, motorcycle_id, landmark)
    blob = json.dumps({
        "context": payload["motorcycle_context"],
        "provenance": payload["motorcycle_context_provenance"],
    }).lower()
    for forbidden in ("next_service", "target_service", "task_code", "probability"):
        assert forbidden not in blob


def test_all_44_probabilities_match_direct_frozen_predictor_exactly(client, known_pair):
    from app.v3_service import get_history_adapter, get_predictor
    from ridebase_ml.v3.serving import build_v3_features

    motorcycle_id, landmark = known_pair
    predictor = get_predictor()
    adapter = get_history_adapter()
    vector = build_v3_features(
        motorcycle_id, landmark, adapter, predictor.labels, predictor.feature_cols
    )
    direct = predictor.predict_product(
        vector.to_frame(predictor.feature_cols), [motorcycle_id],
        landmark_dates=[landmark.isoformat()], feature_coverage=[vector.coverage],
    )[0]
    enriched = _context(client, motorcycle_id, landmark)
    assert len(enriched["all_task_probabilities"]) == 44
    assert enriched["all_task_probabilities"] == direct["all_task_probabilities"]
    assert enriched["binary_predictions"] == direct["binary_predictions"]
    assert enriched["top_tasks"] == direct["top_tasks"]


def test_context_failure_never_blocks_or_changes_prediction(client, known_pair, monkeypatch):
    from app import v3_context

    motorcycle_id, landmark = known_pair
    before = _context(client, motorcycle_id, landmark)

    def unavailable(*_args, **_kwargs):
        raise FileNotFoundError("identity source unavailable")

    monkeypatch.setattr(v3_context, "build_motorcycle_context", unavailable)
    after = _context(client, motorcycle_id, landmark)
    assert after["motorcycle_context"] == {
        "motorcycle_id": motorcycle_id,
        "landmark_date": landmark.isoformat(),
        "source": "SYNTHETIC_HISTORY_V1_4",
    }
    assert after["all_task_probabilities"] == before["all_task_probabilities"]
    assert after["top_tasks"] == before["top_tasks"]
