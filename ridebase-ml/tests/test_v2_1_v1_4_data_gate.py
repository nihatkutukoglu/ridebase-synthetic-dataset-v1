import json
from pathlib import Path

import pandas as pd

from ridebase_ml.v2_1.landmarks import FEATURE_COLUMNS, FORBIDDEN_FEATURE_TOKENS
from ridebase_ml.v2_1.schema_contract import assert_source_schema_compatible


ROOT = Path(__file__).resolve().parents[2]
DERIVED = ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4"
REPORT = json.loads((ROOT / "ridebase-ml/reports/v2_1_v1_4_data_gate.json").read_text())


def test_v1_4_source_matches_frozen_schema():
    result = assert_source_schema_compatible(
        ROOT / "ridebase_v1_4/source_tables",
        ROOT / "ridebase-ml/config/source_schema_contract_v1_3.json",
    )
    assert result["status"] == "PASS"
    assert result["source_columns_changed"] is False


def test_landmark_target_order_and_right_censoring():
    snapshots = pd.read_parquet(DERIVED / "v2_1_landmark_snapshots.parquet")
    targets = pd.read_parquet(DERIVED / "v2_1_survival_targets.parquet")
    joined = snapshots[["landmark_id", "landmark_at"]].merge(targets, on="landmark_id", validate="one_to_one")
    assert joined.landmark_id.is_unique
    assert (joined.duration_days >= 1).all()
    assert joined.loc[joined.event_observed.eq(1), "next_service_id"].notna().all()
    assert joined.loc[joined.event_observed.eq(0), "next_service_id"].isna().all()


def test_odometer_and_due_formulas():
    frame = pd.read_parquet(DERIVED / "v2_1_landmark_snapshots.parquet")
    sample = frame.loc[frame.oem_interval_days.notna() & frame.oem_interval_km.notna()].sample(500, random_state=42)
    assert ((sample.days_since_last_service / sample.oem_interval_days - sample.days_due_ratio).abs() < 1e-9).all()
    assert ((sample.km_since_last_service / sample.oem_interval_km - sample.km_due_ratio).abs() < 1e-9).all()
    assert (sample.days_overdue == (sample.days_since_last_service - sample.oem_interval_days).clip(lower=0)).all()
    assert (sample.km_overdue == (sample.km_since_last_service - sample.oem_interval_km).clip(lower=0)).all()


def test_feature_lineage_has_no_leakage_or_absolute_year():
    assert not [c for c in FEATURE_COLUMNS if any(t in c.lower() for t in FORBIDDEN_FEATURE_TOKENS)]
    assert not any("year" in c.lower() for c in FEATURE_COLUMNS)
    assert "primary_split" not in FEATURE_COLUMNS


def test_temporal_and_unseen_motorcycle_splits():
    manifest = pd.read_csv(DERIVED / "v2_1_landmark_manifest.csv", parse_dates=["landmark_at"])
    assert (manifest.loc[manifest.primary_split.eq("TRAIN"), "landmark_at"] <= "2025-06-30").all()
    assert (manifest.loc[manifest.primary_split.eq("VALIDATION"), "landmark_at"] <= "2025-12-31").all()
    train = set(manifest.loc[manifest.modeling_role.eq("TRAIN"), "motorcycle_id"])
    unseen = set(manifest.loc[manifest.is_unseen_motorcycle_holdout.eq(1), "motorcycle_id"])
    assert train.isdisjoint(unseen)


def test_feature_level_calendar_invariance():
    assert "landmark_month_sin" in FEATURE_COLUMNS and "landmark_month_cos" in FEATURE_COLUMNS
    assert "landmark_year" not in FEATURE_COLUMNS and "production_year" not in FEATURE_COLUMNS


def test_v2_1_v1_4_data_gate_passes():
    assert REPORT["status"] == "PASS"
    assert REPORT["model_training_allowed"] is True
    assert REPORT["failed_checks"] == []
