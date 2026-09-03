from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "ridebase-ml/config/v2_2_behavior_spec.yaml"


def spec():
    return yaml.safe_load(SPEC_PATH.read_text())


def test_behavior_spec_is_explicitly_synthetic_and_preserves_production():
    value = spec()
    assert value["status"] == "SYNTHETIC_ASSUMPTIONS_NOT_REAL_FLEET_FACTS"
    assert value["semantics"]["real_fleet_validation"] == "PENDING"
    assert value["semantics"]["v2_1_production_status"] == "FROZEN"
    assert value["semantics"]["v3_status"] == "ON_HOLD"
    assert "not validated on real RideBase fleet data" in value["disclaimer"]


def test_behavior_spec_is_directional_and_saturating_not_percentage_targeted():
    value = spec()
    relationships = value["relationships"]
    assert relationships["maintenance_pressure"]["direction"] == "generally_increasing_return_hazard"
    assert relationships["maintenance_pressure"]["deterministic_return_forbidden"] is True
    assert relationships["saturation"]["unbounded_growth_forbidden"] is True
    assert value["selection"]["exact_probability_targeting_forbidden"] is True


def test_behavior_spec_encodes_point_in_time_safety():
    value = spec()
    forbidden = set(value["point_in_time"]["forbidden"])
    assert {
        "future_service", "future_appointment_outcome", "post_landmark_mileage",
        "future_task", "future_part", "target_or_censor_field", "absolute_calendar_year",
        "split_marker", "days_observed", "latent_profile_feature",
    } <= forbidden
    assert value["point_in_time"]["known_appointment_rule"] == (
        "created_at <= landmark_date and scheduled_at >= landmark_date"
    )


def test_behavior_spec_has_machine_readable_gates_and_test_freeze():
    value = spec()
    checks = value["machine_checks"]
    assert checks["horizon_monotonicity_rate_min"] == 1.0
    assert checks["overdue_pairwise_trend_rate_min"] >= 0.7
    assert checks["calendar_invariance_max_delta"] <= 1e-6
    assert checks["latent_profile_feature_allowed"] is False
    assert value["selection"]["decision_data"] == "TRAIN_AND_VALIDATION_ONLY"
    assert value["selection"]["test_access"] == "ONCE_AFTER_SELECTION_FREEZE"
