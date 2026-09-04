import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_feature_ablation_is_complete_and_test_sealed() -> None:
    report = json.loads((ROOT / "reports/v2_2_1_feature_ablation.json").read_text())
    assert report["status"] == "PASS"
    assert report["test_rows_read"] is False
    assert len(report["results"]) == 12
    assert "CORE54" in report["results"]
    assert "EXTENDED60" in report["results"]
    assert report["control"] == "V15_XGB54_CONTROL"


def test_xgb_search_is_controlled_and_behavior_gated() -> None:
    report = json.loads((ROOT / "reports/v2_2_1_xgb_search.json").read_text())
    assert report["status"] == "PASS"
    assert report["test_rows_read"] is False
    assert len(report["results"]) == 26
    assert report["selected_candidate_id"] in report["behavior_eligible"]
    assert report["results"][report["selected_candidate_id"]]["behavior"]["status"] == "PASS"


def test_ensemble_search_did_not_override_documented_composite() -> None:
    report = json.loads((ROOT / "reports/v2_2_1_ensemble_search.json").read_text())
    assert report["status"] == "PASS"
    assert report["test_rows_read"] is False
    assert len(report["results"]) == 21
    assert report["ensemble_selected"] is False
    assert report["best_composite"] < report["previous_composite"]


def test_calibration_recovery_improves_without_ranking_regression() -> None:
    report = json.loads((ROOT / "reports/v2_2_1_recovery_selection.json").read_text())
    delta = report["validation_recovery_vs_existing_v2_2"]
    assert report["test_rows_read"] is False
    assert delta["ipcw_c_delta"] >= 0
    assert delta["ibs_delta"] < 0
    assert delta["calibration_error_delta"] < -.005
    assert delta["p30_unique_delta"] > 100
    assert report["selected_metrics"]["behavior"]["status"] == "PASS"


def test_no_v2_2_1_test_first_touch_exists_during_search() -> None:
    assert not (ROOT / "models/v2_2_1_v1_5/test_first_touch.json").exists()
