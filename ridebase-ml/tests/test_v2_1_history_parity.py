"""Prompt-3 report gates: frozen feature and prediction parity."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "ridebase-ml/reports/v2_1_history_feature_parity.json"


def load_report():
    return json.loads(REPORT.read_text())


def test_history_feature_parity_is_exact_for_all_54_features():
    report = load_report()
    assert report["status"] == "PASS"
    assert report["golden_landmarks"]["count"] == 300
    assert report["feature_parity"]["feature_classification_counts"] == {"EXACT_PARITY": 54}
    assert report["feature_parity"]["cell_classification_counts"] == {"EXACT_PARITY": 16_200}
    assert report["feature_parity"]["bug_mismatch_examples"] == []


def test_history_prediction_parity_is_zero_delta():
    parity = load_report()["prediction_parity"]
    assert parity["max_absolute_probability_delta"] == 0.0
    assert parity["median_absolute_probability_delta"] == 0.0
    assert parity["p95_absolute_probability_delta"] == 0.0
    assert parity["cells_over_tolerance"] == 0
    assert parity["median_service_days_differences"] == 0


def test_history_future_injection_and_boundary_gates_pass():
    report = load_report()
    assert report["future_injection"]["cases"] == 10
    assert report["future_injection"]["injected_sources"] == [
        "service", "mileage", "service_task", "service_part", "appointment",
    ]
    assert report["future_injection"]["pass"] is True
    assert report["landmark_boundary"]["pass"] is True
    assert report["landmark_boundary"]["day_before_included"] is True
    assert report["landmark_boundary"]["exact_day_included"] is True
    assert report["landmark_boundary"]["day_after_excluded"] is True


def test_test_rows_were_parity_evidence_only_and_freezes_match():
    report = load_report()
    assert "never champion" in report["golden_landmarks"]["test_usage"]
    assert report["checks"]["test_used_for_parity_not_selection"] is True
    assert report["checks"]["source_schema_unchanged"] is True
    assert report["checks"]["frozen_artifacts_unchanged"] is True
    assert report["checks"]["modeling_table_hash_match"] is True
    assert report["checks"]["v1_4_source_hashes_match_freeze"] is True
    assert report["checks"]["current_odometer_never_initial_mileage"] is True
