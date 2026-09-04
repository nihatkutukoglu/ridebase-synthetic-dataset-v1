import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v2_2_1_preflight_is_green_and_frozen() -> None:
    report = json.loads((ROOT / "reports/v2_2_1_preflight_baseline.json").read_text())
    assert report["status"] == "PASS"
    assert all(report["checks"].values())
    assert report["constraints"]["v2_1_frozen"] is True
    assert report["constraints"]["v2_2_frozen"] is True


def test_diagnosis_is_train_validation_only() -> None:
    report = json.loads((ROOT / "reports/v2_2_1_statistical_diagnosis.json").read_text())
    assert report["status"] == "PASS"
    assert report["test_rows_read"] is False
    assert all(report["gate_checks"].values())
    assert len(report["temporal_validation"]) == 3


def test_diagnosis_covers_shared_and_new_features() -> None:
    report = json.loads((ROOT / "reports/v2_2_1_statistical_diagnosis.json").read_text())
    assert len(report["feature_diagnostics"]["shared_54"]) == 54
    assert len(report["new_feature_diagnostics"]) == 6
    assert {row["feature"] for row in report["new_feature_diagnostics"]} == {
        "prior_appointment_count", "prior_no_show_count", "prior_cancelled_appointment_count",
        "known_appointment_within_30d", "days_to_next_known_appointment", "recent_breakdown_count_180d",
    }


def test_diagnosis_records_overfit_and_calibration_resolution() -> None:
    report = json.loads((ROOT / "reports/v2_2_1_statistical_diagnosis.json").read_text())
    assert report["model_diagnostics"]["train_harrell_c"] > report["model_diagnostics"]["validation_harrell_c"]
    resolution = report["calibration_diagnostics"]["p30_resolution"]
    assert resolution["raw_unique_8dp"] > resolution["isotonic_unique_8dp"]
