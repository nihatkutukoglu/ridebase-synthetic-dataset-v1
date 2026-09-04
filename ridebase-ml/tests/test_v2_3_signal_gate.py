import json
from pathlib import Path


ML = Path(__file__).resolve().parents[1]


def test_signal_gate_failed_without_test_access():
    report = json.loads((ML / "reports/v2_3_signal_audit.json").read_text())
    assert report["status"] == "FAIL"
    assert report["test_rows_read"] is False
    assert report["checks"]["full_ibs_stable"]
    assert not report["checks"]["full_improves_discrimination"]


def test_failure_stops_model_family_and_freeze_phases():
    search = json.loads((ML / "reports/v2_3_model_search.json").read_text())
    assert search == {"status": "NOT_RUN_SIGNAL_GATE_FAILED", "test_rows_read": False}
    assert not (ML / "v2_3_selection_manifest.json").exists()
    assert not (ML / "models/v2_3_v1_5/test_first_touch.json").exists()
