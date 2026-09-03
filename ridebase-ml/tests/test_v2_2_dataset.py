import hashlib
import json
from pathlib import Path

import pandas as pd

from ridebase_ml.v2_2.landmarks import (
    BASE_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    _add_observable_history_features,
)


ROOT = Path(__file__).resolve().parents[2]
DERIVED = ROOT / "ridebase-ml/derived_outputs/v2_2_v1_5"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_v1_5_structural_gate_and_all_latent_profiles_are_audit_only():
    metadata = json.loads((ROOT / "ridebase_v1_5/dataset_metadata.json").read_text())
    assert metadata["qa"]["status"] == "PASS"
    assert metadata["reproducibility_verified"] is True
    assert set(metadata["latent_profile_counts_audit_only"]) == {
        "ON_TIME", "NORMAL", "DELAYER", "HEAVY_USER", "PRICE_SENSITIVE",
        "CHURN_RISK", "WORKSHOP_LOYAL", "NO_SHOW_PRONE",
    }
    assert metadata["source_schema_changed"] is False


def test_v2_2_feature_contract_reuses_base54_and_has_no_forbidden_shortcuts():
    assert len(BASE_FEATURE_COLUMNS) == 54
    assert len(FEATURE_COLUMNS) == 60
    assert FEATURE_COLUMNS[:54] == BASE_FEATURE_COLUMNS
    forbidden = ("split", "target", "censor", "future_", "year", "days_observed", "latent", "event_observed")
    assert not [name for name in FEATURE_COLUMNS if any(token in name.lower() for token in forbidden)]


def test_known_appointment_uses_creation_time_not_future_outcome():
    snapshots = pd.DataFrame({
        "motorcycle_id": ["MCX", "MCX"],
        "landmark_at": pd.to_datetime(["2026-01-10", "2026-01-25"]),
    })
    appointments = pd.DataFrame({
        "motorcycle_id": ["MCX"], "created_at": ["2026-01-05"],
        "scheduled_at": ["2026-01-20"], "status": ["CANCELLED"],
    })
    services = pd.DataFrame({
        "motorcycle_id": [], "received_at": [], "status": [], "service_type_code": [],
    })
    result = _add_observable_history_features(snapshots, appointments, services)
    assert result.loc[0, "known_appointment_within_30d"] == 1
    assert result.loc[0, "prior_cancelled_appointment_count"] == 0
    assert result.loc[1, "known_appointment_within_30d"] == 0
    assert result.loc[1, "prior_cancelled_appointment_count"] == 1


def test_dataset_and_generator_behavior_gates_pass():
    quality = json.loads((DERIVED / "v2_2_data_quality_report.json").read_text())
    audit = json.loads((ROOT / "ridebase-ml/reports/v1_5_behavior_audit.json").read_text())
    assert quality["status"] == "PASS"
    assert quality["rows"] == 259804
    assert quality["features"] == 60
    assert audit["status"] == "PASS"
    assert all(audit["checks"].values())


def test_temporal_and_unseen_split_integrity():
    modeling = pd.read_parquet(
        DERIVED / "v2_2_modeling_table.parquet",
        columns=["motorcycle_id", "landmark_at", "primary_split", "modeling_role", "is_unseen_motorcycle_holdout"],
    )
    assert modeling.loc[modeling.primary_split.eq("TRAIN"), "landmark_at"].max() <= pd.Timestamp("2025-06-30")
    assert modeling.loc[modeling.primary_split.eq("VALIDATION"), "landmark_at"].max() <= pd.Timestamp("2025-12-31")
    assert modeling.loc[modeling.primary_split.eq("TEST"), "landmark_at"].min() >= pd.Timestamp("2026-01-01")
    seen_train_val = set(modeling.loc[modeling.modeling_role.isin(["TRAIN", "VALIDATION"]), "motorcycle_id"])
    unseen = set(modeling.loc[modeling.modeling_role.eq("UNSEEN_MOTORCYCLE_TEMPORAL_TEST"), "motorcycle_id"])
    assert seen_train_val.isdisjoint(unseen)


def test_v2_1_and_v1_4_frozen_hashes_still_match_preflight():
    baseline = json.loads((ROOT / "ridebase-ml/reports/v2_2_preflight_baseline.json").read_text())["frozen_hashes"]
    assert sha256(ROOT / "ridebase-ml/models/v2_1_v1_4/feature_list.json") == baseline["v2_1_feature_contract"]
    assert sha256(ROOT / "ridebase-ml/models/v2_1_v1_4/champion_model.joblib") == baseline["v2_1_champion"]
    assert sha256(ROOT / "ridebase-ml/models/v2_1_v1_4/calibrator.joblib") == baseline["v2_1_calibrator"]
    assert sha256(ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite") == baseline["v2_1_history_serving_sqlite"]
