"""Prompt 1 gates for the V2.1 history pipeline contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ridebase_ml.v2_1.adapters.base import RideBaseSourceAdapter
from ridebase_ml.v2_1.history_features import FEATURE_MAPPING, build_features
from ridebase_ml.v2_1.landmarks import FEATURE_COLUMNS
from ridebase_ml.v2_1.schema_contract import assert_source_schema_compatible
from ridebase_ml.v2_1.source_contract import Provenance, UnknownMotorcycleError

ROOT = Path(__file__).resolve().parents[2]


class MemoryAdapter(RideBaseSourceAdapter):
    def __init__(self, tables=None):
        self.tables = tables or {}

    def read_table(self, table_name):
        return [dict(row) for row in self.tables.get(table_name, [])]


def base_tables():
    return {
        "motorcycles": [{
            "motorcycle_id": "MC1", "customer_id": "C1", "workshop_id": "W1",
            "model_id": "M1", "observation_start_date": "2024-01-01",
            "initial_mileage_km": 98765,
        }],
        "customers": [{"customer_id": "C1", "first_seen_date": "2024-01-01"}],
        "ridebase_motorcycle_models_v1": [{"model_id": "M1", "policy_group": "G1"}],
        "maintenance_policies": [],
        "workshops": [{"workshop_id": "W1"}],
        "usage_profiles": [],
        "services": [],
        "mileage_timeline_monthly": [],
        "service_tasks": [],
        "service_parts": [],
        "appointments": [],
    }


def sha256(path):
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_valid_motorcycle_and_exact_frozen_contract():
    result = build_features("MC1", "2025-02-28", MemoryAdapter(base_tables()))
    assert set(result) == {
        "features", "provenance", "source_evidence", "warnings", "feature_coverage", "landmark",
    }
    assert list(result["features"]) == FEATURE_COLUMNS
    assert list(result["provenance"]) == FEATURE_COLUMNS
    assert set(FEATURE_MAPPING) == set(FEATURE_COLUMNS)
    assert len(FEATURE_MAPPING) == 54
    assert result["landmark"] == {
        "motorcycle_id": "MC1", "landmark_date": "2025-02-28", "inclusive_boundary": True,
    }
    assert result["feature_coverage"]["is_confidence"] is False


def test_unknown_motorcycle_id():
    with pytest.raises(UnknownMotorcycleError):
        build_features("DOES_NOT_EXIST", "2025-02-28", MemoryAdapter(base_tables()))


def test_empty_history_stays_missing():
    result = build_features("MC1", "2025-02-28", MemoryAdapter(base_tables()))
    assert result["source_evidence"]["history_record_counts"] == {
        "services": 0, "mileage": 0, "tasks": 0, "parts": 0, "appointments": 0,
    }
    assert result["features"]["current_odometer_km_at_landmark"] is None
    assert result["provenance"]["current_odometer_km_at_landmark"] == Provenance.MISSING_HISTORY.value
    assert any("No eligible DELIVERED service" in warning for warning in result["warnings"])


def test_one_and_multiple_service_history_are_visible_at_boundary():
    tables = base_tables()
    tables["services"] = [
        {"service_id": "S1", "motorcycle_id": "MC1", "received_at": "2025-02-27 23:59:59"},
        {"service_id": "S2", "motorcycle_id": "MC1", "received_at": "2025-02-28 18:00:00"},
        {"service_id": "S3", "motorcycle_id": "MC1", "received_at": "2025-03-01 00:00:00"},
    ]
    one = build_features("MC1", "2025-02-27", MemoryAdapter(tables))
    multiple = build_features("MC1", "2025-02-28", MemoryAdapter(tables))
    assert one["source_evidence"]["history_record_counts"]["services"] == 1
    assert multiple["source_evidence"]["history_record_counts"]["services"] == 2
    assert multiple["source_evidence"]["max_effective_at"]["services"] == "2025-02-28"


def test_future_records_for_every_event_source_do_not_change_old_landmark():
    baseline_tables = base_tables()
    baseline_tables["services"] = [
        {"service_id": "S1", "motorcycle_id": "MC1", "received_at": "2025-02-01"},
    ]
    baseline_tables["mileage_timeline_monthly"] = [
        {"timeline_id": "L1", "motorcycle_id": "MC1", "period_end_date": "2025-02-28", "closing_odometer_km": 12000},
    ]
    baseline_tables["service_tasks"] = [
        {"service_task_id": "T1", "service_id": "S1", "motorcycle_id": "MC1", "completed_at": "2025-02-01"},
    ]
    baseline_tables["service_parts"] = [
        {"service_part_id": "P1", "service_id": "S1", "service_task_id": "T1", "motorcycle_id": "MC1"},
    ]
    baseline_tables["appointments"] = [
        {"appointment_id": "A1", "motorcycle_id": "MC1", "created_at": "2025-01-15"},
    ]
    injected = {name: [dict(row) for row in rows] for name, rows in baseline_tables.items()}
    injected["services"].append({"service_id": "S9", "motorcycle_id": "MC1", "received_at": "2025-03-01"})
    injected["mileage_timeline_monthly"].append(
        {"timeline_id": "L9", "motorcycle_id": "MC1", "period_end_date": "2025-03-31", "closing_odometer_km": 999999}
    )
    injected["service_tasks"].append(
        {"service_task_id": "T9", "service_id": "S9", "motorcycle_id": "MC1", "completed_at": "2025-03-01"}
    )
    injected["service_parts"].append(
        {"service_part_id": "P9", "service_id": "S9", "service_task_id": "T9", "motorcycle_id": "MC1"}
    )
    injected["appointments"].append(
        {"appointment_id": "A9", "motorcycle_id": "MC1", "created_at": "2025-03-01"}
    )

    baseline = build_features("MC1", "2025-02-28", MemoryAdapter(baseline_tables))
    after = build_features("MC1", "2025-02-28", MemoryAdapter(injected))
    assert baseline["source_evidence"]["max_effective_at"]["parts"] == "2025-02-01"
    assert after == baseline


def test_current_odometer_is_latest_known_mileage_never_initial_mileage():
    tables = base_tables()
    tables["mileage_timeline_monthly"] = [
        {"timeline_id": "L1", "motorcycle_id": "MC1", "period_end_date": "2025-01-31", "closing_odometer_km": 11000},
        {"timeline_id": "L2", "motorcycle_id": "MC1", "period_end_date": "2025-02-28", "closing_odometer_km": 12000},
        {"timeline_id": "L3", "motorcycle_id": "MC1", "period_end_date": "2025-03-31", "closing_odometer_km": 13000},
    ]
    result = build_features("MC1", "2025-02-28", MemoryAdapter(tables))
    assert result["features"]["current_odometer_km_at_landmark"] == 12000
    assert result["features"]["current_odometer_km_at_landmark"] != 98765
    assert "initial_mileage_km" not in result["features"]
    assert result["provenance"]["current_odometer_km_at_landmark"] == Provenance.SOURCE_MILEAGE_HISTORY.value


def test_provenance_vocabulary_and_missingness_are_honest():
    result = build_features("MC1", "2025-02-28", MemoryAdapter(base_tables()))
    allowed = {value.value for value in Provenance}
    assert set(result["provenance"].values()) <= allowed
    assert result["provenance"]["landmark_month_sin"] == Provenance.LANDMARK_DERIVED.value
    assert result["provenance"]["prior_service_count"] == Provenance.MISSING_HISTORY.value
    assert result["features"]["prior_service_count"] is None


def test_v1_4_source_schema_and_frozen_model_artifacts_unchanged():
    schema = assert_source_schema_compatible(
        ROOT / "ridebase_v1_4/source_tables",
        ROOT / "ridebase-ml/config/source_schema_contract_v1_3.json",
    )
    assert schema["status"] == "PASS"
    assert schema["table_count"] == 13
    assert schema["source_columns_changed"] is False

    model_dir = ROOT / "ridebase-ml/models/v2_1_v1_4"
    manifest = json.loads((model_dir / "artifact_manifest.json").read_text())
    for name, expected in manifest.items():
        assert sha256(model_dir / name) == expected, name
