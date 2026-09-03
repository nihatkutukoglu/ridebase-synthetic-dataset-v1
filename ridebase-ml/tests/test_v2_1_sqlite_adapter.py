"""Tests for the memory-safe SyntheticSQLiteSourceAdapter."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from ridebase_ml.v2_1.adapters.sqlite import SyntheticSQLiteSourceAdapter
from ridebase_ml.v2_1.history_features import build_features
from ridebase_ml.v2_1.landmarks import FEATURE_COLUMNS
from ridebase_ml.v2_1.predictor import V21SurvivalPredictor
from ridebase_ml.v2_1.source_contract import UnknownMotorcycleError

ROOT = Path(__file__).resolve().parents[2]
STORE_PATH = ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite"
MANIFEST_PATH = ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_store_manifest.json"
MODEL_DIR = ROOT / "ridebase-ml/models/v2_1_v1_4"

pytestmark = pytest.mark.skipif(not STORE_PATH.exists(), reason="SQLite store not found")


@pytest.fixture(scope="module")
def sqlite_adapter():
    return SyntheticSQLiteSourceAdapter(STORE_PATH)


@pytest.fixture(scope="module")
def predictor():
    return V21SurvivalPredictor.load(MODEL_DIR)


def test_sqlite_store_manifest_and_determinism():
    assert MANIFEST_PATH.exists()
    manifest = json.loads(MANIFEST_PATH.read_text())
    assert manifest["source_dataset_version"] == "1.4.0"
    assert manifest["sqlite_sha256"]
    assert manifest["sqlite_size_mb"] < 120.0
    assert manifest["row_counts"]["motorcycles"] == 10000
    assert manifest["row_counts"]["services"] == 52700
    assert manifest["row_counts"]["mileage_timeline_monthly"] == 344714
    assert len(manifest["schema_summary"]) == 12


def test_unknown_motorcycle_raises(sqlite_adapter):
    assert sqlite_adapter.motorcycle_exists("MC_NOT_EXIST") is False
    with pytest.raises(UnknownMotorcycleError):
        build_features("MC_NOT_EXIST", "2025-06-01", sqlite_adapter)


def test_pre_observation_landmark_raises(sqlite_adapter):
    # MC000001 observation_start_date is 2024-06-21
    assert sqlite_adapter.motorcycle_exists("MC000001") is True
    with pytest.raises(UnknownMotorcycleError):
        build_features("MC000001", "2024-01-01", sqlite_adapter)


def test_valid_motorcycle_rich_history(sqlite_adapter, predictor):
    built = build_features("MC000001", "2025-06-01", sqlite_adapter)
    features = built["features"]
    assert len(features) == 54
    assert list(features.keys()) == FEATURE_COLUMNS
    assert features["brand"] == "Yamaha"
    assert features["category"] == "SCOOTER"
    assert features["current_odometer_km_at_landmark"] is not None
    assert features["current_odometer_km_at_landmark"] > 0
    # Odometer must never fall back to initial_mileage_km (which is 83780)
    assert features["current_odometer_km_at_landmark"] != 83780

    pred = predictor.predict([features], strict=True)["predictions"][0]
    assert 0.0 <= pred["risk_30d"] <= pred["risk_60d"] <= pred["risk_90d"] <= pred["risk_120d"] <= 1.0
    assert pred["median_service_days"] is not None


def test_sparse_history_preserves_nulls(sqlite_adapter, predictor):
    # Early landmark on day of observation start
    built = build_features("MC000001", "2024-06-21", sqlite_adapter)
    features = built["features"]
    # No services prior to this date
    assert features["days_since_last_service"] is None
    assert features["km_since_last_service"] is None
    # Current odometer should be None if no timeline entry before or at this day
    # and MUST NOT fall back to initial_mileage_km
    assert features["current_odometer_km_at_landmark"] is None
    assert "initial_mileage_km" not in features


def test_point_in_time_boundary_inclusion(sqlite_adapter):
    # Query services before a known service date
    services = sqlite_adapter.get_services_before("MC000001", date(2024, 7, 10))
    for s in services:
        assert s["_effective_at"] <= "2024-07-10"


def test_cache_info_diagnostics(sqlite_adapter):
    info = sqlite_adapter.cache_info()
    assert info["adapter_type"] == "SQLITE"
    assert info["history_source"] == "SYNTHETIC_V1_4"
    assert info["disk_reads"] == 0
    assert info["store_size_bytes"] > 0
