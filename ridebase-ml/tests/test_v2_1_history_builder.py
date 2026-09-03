"""Prompt 2 gates for the cached V1.4 history feature builder."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pandas as pd
import pytest

from ridebase_ml.v2_1.adapters.synthetic import SyntheticRideBaseSourceAdapter
from ridebase_ml.v2_1.history_features import build_features
from ridebase_ml.v2_1.landmarks import FEATURE_COLUMNS, FORBIDDEN_FEATURE_TOKENS
from ridebase_ml.v2_1.source_contract import UnknownMotorcycleError

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ridebase_v1_4/source_tables"
CONTRACT = ROOT / "ridebase-ml/config/source_schema_contract_v1_3.json"
MODELING = ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet"


@pytest.fixture(scope="module")
def adapter():
    return SyntheticRideBaseSourceAdapter(SOURCE, CONTRACT)


@pytest.fixture(scope="module")
def rich_row():
    return pd.read_parquet(
        MODELING, columns=["motorcycle_id", "landmark_at", *FEATURE_COLUMNS]
    ).iloc[0]


def same_value(left, right):
    if left is None and pd.isna(right):
        return True
    if isinstance(left, (int, float)) and not isinstance(left, bool) and pd.notna(right):
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-9)
    return left == right


def test_synthetic_adapter_supports_all_source_tables_and_motorcycles(adapter):
    assert adapter.history_source == "SYNTHETIC_V1_4"
    assert set(adapter.supported_tables) == {
        "appointments", "customers", "maintenance_policies", "maintenance_tasks",
        "mileage_timeline_monthly", "motorcycles", "ridebase_motorcycle_models_v1",
        "service_parts", "service_tasks", "services", "services_enriched",
        "usage_profiles", "workshops",
    }
    assert adapter.supported_motorcycle_count == 10_000


def test_rich_history_reconstructs_exact_frozen_keys_without_forbidden_fields(adapter, rich_row):
    result = build_features(rich_row.motorcycle_id, rich_row.landmark_at.date(), adapter)
    assert list(result["features"]) == FEATURE_COLUMNS
    assert result["feature_coverage"]["resolved_count"] == 54
    assert result["feature_coverage"]["contract_count"] == 54
    assert not [
        name for name in result["features"]
        if any(token in name.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    ]
    assert all(same_value(result["features"][name], rich_row[name]) for name in FEATURE_COLUMNS)


def test_reconstruction_is_deterministic_and_tables_are_not_reloaded(adapter, rich_row):
    first = build_features(rich_row.motorcycle_id, rich_row.landmark_at.date(), adapter)
    reads = adapter.cache_info()["disk_reads_by_table"]
    second = build_features(rich_row.motorcycle_id, rich_row.landmark_at.date(), adapter)
    assert first == second
    assert adapter.cache_info()["disk_reads_by_table"] == reads
    assert all(count == 1 for count in reads.values())


def test_sparse_history_remains_missing_without_initial_odometer_fallback(adapter):
    result = build_features("MC000001", "2024-06-25", adapter)
    features = result["features"]
    assert features["current_odometer_km_at_landmark"] is None
    assert features["days_since_last_service"] is None
    assert features["prior_service_count"] is None
    assert "initial_mileage_km" not in features
    assert result["source_evidence"]["history_record_counts"]["mileage"] == 0
    assert result["source_evidence"]["eligible_service_records"] == 0
    assert result["feature_coverage"]["resolved_count"] < 54
    assert result["feature_coverage"]["is_confidence"] is False


def test_unknown_motorcycle_is_rejected(adapter):
    with pytest.raises(UnknownMotorcycleError):
        build_features("MC_DOES_NOT_EXIST", "2026-01-31", adapter)


def test_current_odometer_uses_latest_mileage_at_or_before_landmark(adapter):
    result = build_features("MC000001", "2024-07-15", adapter)
    evidence = result["source_evidence"]["current_odometer_source"]
    assert evidence["period_end_date"] == "2024-06-30"
    assert result["features"]["current_odometer_km_at_landmark"] == 84451
    assert evidence["closing_odometer_km"] == 84451


def test_source_evidence_never_extends_beyond_landmark(adapter, rich_row):
    landmark = rich_row.landmark_at.date().isoformat()
    result = build_features(rich_row.motorcycle_id, landmark, adapter)
    for effective in result["source_evidence"]["max_effective_at"].values():
        assert effective is None or effective <= landmark
    last_service = result["source_evidence"]["last_eligible_service"]
    assert last_service is None or last_service["received_date"] <= landmark


def test_warm_build_latency_is_bounded(adapter, rich_row):
    build_features(rich_row.motorcycle_id, rich_row.landmark_at.date(), adapter)
    started = time.perf_counter()
    build_features(rich_row.motorcycle_id, rich_row.landmark_at.date(), adapter)
    assert (time.perf_counter() - started) * 1000.0 < 250.0


def test_committed_coverage_audit_passes_and_separates_coverage_from_confidence():
    report = json.loads((ROOT / "ridebase-ml/reports/v2_1_history_feature_coverage.json").read_text())
    assert report["status"] == "PASS"
    assert report["sample"]["landmarks"] == 500
    assert report["feature_contract_count"] == 54
    assert report["checks"]["no_future_source_evidence"] is True
    assert report["checks"]["disk_read_once_per_loaded_table"] is True
    assert report["checks"]["coverage_is_not_confidence"] is True
