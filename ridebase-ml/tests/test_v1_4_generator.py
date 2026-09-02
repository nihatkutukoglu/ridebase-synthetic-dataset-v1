import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "ridebase-ml/config/source_schema_contract_v1_3.json").read_text())
METADATA = json.loads((ROOT / "ridebase_v1_4/dataset_metadata.json").read_text())
SANITY = json.loads((ROOT / "ridebase_v1_4/reports/v1_4_generator_sanity.json").read_text())


def test_v1_4_source_schema_equals_frozen_v1_3_contract():
    for filename, spec in CONTRACT["tables"].items():
        actual = pd.read_csv(ROOT / "ridebase_v1_4/source_tables" / filename, nrows=0)
        assert list(actual.columns) == spec["ordered_columns"]


def test_v1_3_parent_hashes_are_unchanged():
    import hashlib
    for filename, expected in METADATA["parent_hashes"].items():
        assert hashlib.sha256((ROOT / "ridebase_v1_3/source_tables" / filename).read_bytes()).hexdigest() == expected


def test_seed_reproducibility_was_verified():
    assert METADATA["reproducibility_verified"] is True
    assert METADATA["qa"]["checks"]["reproducibility:source_hashes"] is True


def test_overdue_dead_region_regression_gate():
    assert SANITY["gate_checks"]["severely_overdue_dead_region_resolved"] is True
    states = {row["due_state"]: row for row in SANITY["due_pressure_vs_return"]}
    assert states["SEVERELY_OVERDUE"]["event_90d_rate"] >= 0.15


def test_due_pressure_and_km_time_sensitivity():
    checks = SANITY["gate_checks"]
    assert checks["due_pressure_direction"] is True
    assert checks["km_usage_sensitivity"] is True
    assert checks["time_usage_sensitivity"] is True


def test_source_qa_and_no_future_history():
    assert SANITY["source_qa"]["status"] == "PASS"
    assert SANITY["source_qa"]["checks"]["window:no_future_history"] is True


def test_behavior_overlap_and_nondeterminism():
    assert SANITY["gate_checks"]["behavior_group_overlap"] is True
    assert SANITY["gate_checks"]["service_outcome_not_deterministic"] is True
