import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models/v2_2_1_v1_5"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_one_time_test_hash_chain_and_no_post_test_tuning() -> None:
    selection = MODEL_DIR / "v2_2_1_selection_manifest.json"
    first = json.loads((MODEL_DIR / "test_first_touch.json").read_text())
    report = json.loads((MODEL_DIR / "test_evaluation.json").read_text())
    assert first["selection_manifest_sha256"] == _sha256(selection)
    assert report["checks"]["no_post_test_tuning"] is True
    assert report["first_touch"] == first


def test_statistical_recovery_is_honestly_rejected() -> None:
    report = json.loads((MODEL_DIR / "test_evaluation.json").read_text())
    assert report["status"] == "FAIL"
    assert report["decision"] == "CHALLENGER_REJECTED_STATISTICAL"
    assert report["failed_checks"] == ["same_world_statistical_improvement"]
    delta = report["same_world_v2_2_to_v2_2_1"]
    assert delta["ipcw_c_delta"] == 0
    assert delta["mean_calibration_error_delta"] > 0


def test_behavior_was_preserved_but_did_not_override_statistics() -> None:
    report = json.loads((MODEL_DIR / "test_evaluation.json").read_text())
    assert report["checks"]["behavior_frozen_pass"] is True
    assert report["checks"]["same_world_statistical_improvement"] is False
    assert report["checks"]["v2_1_untouched"] is True
    assert report["checks"]["v2_2_untouched"] is True
    assert report["checks"]["no_deploy"] is True


def test_three_way_comparison_keeps_v2_1_production_champion() -> None:
    report = json.loads((ROOT / "reports/v2_1_v2_2_v2_2_1_comparison.json").read_text())
    assert report["decision"] == "CHALLENGER_REJECTED_STATISTICAL"
    assert report["production_champion"] == "V2.1"
    assert report["deployment"] == "NONE"
    assert [row["model"] for row in report["metrics"]] == ["V2.1", "V2.2", "V2.2.1"]


def test_rejected_research_artifact_manifest_is_internally_consistent() -> None:
    manifest = json.loads((MODEL_DIR / "artifact_manifest.json").read_text())
    for filename, expected in manifest.items():
        assert _sha256(MODEL_DIR / filename) == expected
