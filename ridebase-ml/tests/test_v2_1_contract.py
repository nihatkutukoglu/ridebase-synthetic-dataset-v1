"""V2.1 source-schema, landmark, leakage, and stop-gate regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ridebase_ml.v2_1.landmarks import FEATURE_COLUMNS, FORBIDDEN_FEATURE_TOKENS
from ridebase_ml.v2_1.schema_contract import assert_source_schema_contract


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ridebase_v1_3" / "source_tables"
CONTRACT = ROOT / "ridebase-ml" / "config" / "source_schema_contract_v1_3.json"
DERIVED = ROOT / "ridebase-ml" / "derived_outputs" / "v2_1"
REPORTS = ROOT / "ridebase-ml" / "reports"


def test_source_schema_and_frozen_files_match_contract():
    result = assert_source_schema_contract(SOURCE, CONTRACT)
    assert result["status"] == "PASS"
    assert result["table_count"] == 13
    assert result["source_columns_changed"] is False


def test_landmark_target_contract_and_censoring():
    snapshots = pd.read_parquet(DERIVED / "v2_1_landmark_snapshots.parquet")
    targets = pd.read_parquet(DERIVED / "v2_1_survival_targets.parquet")
    joined = snapshots[["landmark_id", "landmark_at"]].merge(targets, on="landmark_id", validate="one_to_one")
    assert snapshots["landmark_id"].is_unique
    assert set(snapshots["landmark_id"]) == set(targets["landmark_id"])
    assert (targets["duration_days"] >= 1).all()
    assert targets.loc[targets["event_observed"] == 1, "next_service_id"].notna().all()
    assert targets.loc[targets["event_observed"] == 0, "next_service_id"].isna().all()
    assert (joined.loc[joined["event_observed"] == 1, "duration_days"] > 0).all()


def test_landmarks_stay_inside_observation_window():
    snapshots = pd.read_parquet(DERIVED / "v2_1_landmark_snapshots.parquet")
    targets = pd.read_parquet(DERIVED / "v2_1_survival_targets.parquet")
    joined = snapshots[["landmark_id", "landmark_at", "observation_start_date"]].merge(
        targets[["landmark_id", "administrative_cutoff_at"]], on="landmark_id", validate="one_to_one"
    )
    assert (joined["landmark_at"] >= joined["observation_start_date"]).all()
    assert (joined["landmark_at"] < joined["administrative_cutoff_at"]).all()


def test_no_target_split_censor_or_absolute_year_feature():
    forbidden = [
        column for column in FEATURE_COLUMNS
        if any(token in column.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    ]
    assert forbidden == []
    for exact in ["split", "event_observed", "duration_days", "snapshot_year", "landmark_year", "days_observed"]:
        assert exact not in FEATURE_COLUMNS


def test_current_odometer_and_due_ratios_are_deterministic():
    snapshots = pd.read_parquet(DERIVED / "v2_1_landmark_snapshots.parquet")
    sample = snapshots.loc[
        snapshots["oem_interval_km"].notna() & snapshots["oem_interval_days"].notna()
    ].sample(250, random_state=42)
    timeline = pd.read_csv(SOURCE / "mileage_timeline_monthly.csv", parse_dates=["period_end_date"])
    timeline["period_end_date"] = timeline["period_end_date"].dt.normalize()
    expected = sample.merge(
        timeline[["motorcycle_id", "period_end_date", "closing_odometer_km"]],
        left_on=["motorcycle_id", "landmark_at"],
        right_on=["motorcycle_id", "period_end_date"],
        validate="many_to_one",
    )
    assert (expected["current_odometer_km_at_landmark"] == expected["closing_odometer_km"]).all()
    assert ((sample["km_since_last_service"] / sample["oem_interval_km"] - sample["km_due_ratio"]).abs() < 1e-9).all()
    assert ((sample["days_since_last_service"] / sample["oem_interval_days"] - sample["days_due_ratio"]).abs() < 1e-9).all()


def test_group_temporal_split_keeps_unseen_motorcycles_out_of_training():
    manifest = pd.read_csv(DERIVED / "v2_1_landmark_manifest.csv")
    unseen = set(manifest.loc[manifest["is_unseen_motorcycle_holdout"] == 1, "motorcycle_id"])
    train = set(manifest.loc[manifest["modeling_role"] == "TRAIN", "motorcycle_id"])
    assert unseen
    assert unseen.isdisjoint(train)
    assert (manifest.loc[manifest["modeling_role"] == "UNSEEN_MOTORCYCLE_TEMPORAL_TEST", "primary_split"] == "TEST").all()


def test_synthetic_sanity_stop_gate_blocks_model_training():
    sanity = json.loads((REPORTS / "v2_1_synthetic_sanity.json").read_text())
    assert sanity["status"] == "FAIL"
    assert sanity["model_training_allowed"] is False
    assert "overdue_direction_physically_coherent" in sanity["failed_checks"]
    assert "severely_overdue_not_dead_region" in sanity["failed_checks"]


def test_v2_0_failures_are_regression_requirements():
    audit = json.loads((REPORTS / "v2_1_live_behavior_audit.json").read_text())
    required = {
        "service_event_landmark_mismatch", "exact_zero_30d_collapse",
        "km_since_service_sensitivity", "elapsed_time_direction",
        "absolute_calendar_invariance", "observation_artifact_invariance",
        "overdue_product_contradiction",
    }
    assert required <= set(audit["checks"])
    assert all(audit["checks"][name]["status"] == "FAIL" for name in required)


def test_no_v2_1_model_was_created_after_failed_gate():
    model_dir = ROOT / "ridebase-ml" / "models" / "v2_1"
    assert not model_dir.exists() or not any(model_dir.glob("*"))
