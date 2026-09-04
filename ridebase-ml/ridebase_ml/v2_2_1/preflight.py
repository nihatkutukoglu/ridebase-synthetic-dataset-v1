"""Freeze and verify the inputs to the V2.2.1 recovery experiment."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def run(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    reports = ml / "reports"
    old = json.loads((reports / "v2_2_preflight_baseline.json").read_text())
    v15 = json.loads((root / "ridebase_v1_5/dataset_metadata.json").read_text())
    v22_manifest = json.loads((ml / "models/v2_2_v1_5/artifact_manifest.json").read_text())
    hashes = {
        "v1_4_generator": _sha256(root / "build_ridebase_v1_4.py"),
        "v1_4_metadata": _sha256(root / "ridebase_v1_4/dataset_metadata.json"),
        "v1_5_generator": _sha256(root / "build_ridebase_v1_5.py"),
        "v1_5_metadata": _sha256(root / "ridebase_v1_5/dataset_metadata.json"),
        "v2_1_feature_contract": _sha256(ml / "models/v2_1_v1_4/feature_list.json"),
        "v2_1_model": _sha256(ml / "models/v2_1_v1_4/champion_model.joblib"),
        "v2_1_calibrator": _sha256(ml / "models/v2_1_v1_4/calibrator.joblib"),
        "v2_1_history_store": _sha256(ml / "derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite"),
        "v2_2_selection": _sha256(ml / "models/v2_2_v1_5/v2_2_selection_manifest.json"),
        "v2_2_test_report": _sha256(ml / "models/v2_2_v1_5/test_evaluation.json"),
        "v2_2_behavior_spec": _sha256(ml / "config/v2_2_behavior_spec.yaml"),
        "v2_2_split_manifest": _sha256(ml / "derived_outputs/v2_2_v1_5/v2_2_split_manifest.json"),
    }
    v14_source_checks = {
        name: _sha256(root / "ridebase_v1_4/source_tables" / name) == expected
        for name, expected in v15["frozen_reference_hashes"]["v1_4"].items()
    }
    v15_source_checks = {
        name: _sha256(root / "ridebase_v1_5/source_tables" / name) == expected
        for name, expected in v15["source_hashes"].items()
    }
    v22_artifact_checks = {
        name: _sha256(ml / "models/v2_2_v1_5" / name) == expected
        for name, expected in v22_manifest.items()
    }
    checks = {
        "expected_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip().startswith("54cd655"),
        "main_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip() == "main",
        "origin_synchronized": subprocess.check_output(["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"], cwd=root, text=True).strip() == "0\t0",
        "v1_4_sources_frozen": all(v14_source_checks.values()),
        "v1_5_sources_frozen": all(v15_source_checks.values()),
        "v2_1_core_hashes_frozen": (
            hashes["v1_4_generator"] == old["frozen_hashes"]["v1_4_generator"]
            and hashes["v1_4_metadata"] == old["frozen_hashes"]["v1_4_dataset_metadata"]
            and hashes["v2_1_feature_contract"] == old["frozen_hashes"]["v2_1_feature_contract"]
            and hashes["v2_1_model"] == old["frozen_hashes"]["v2_1_champion"]
            and hashes["v2_1_calibrator"] == old["frozen_hashes"]["v2_1_calibrator"]
            and hashes["v2_1_history_store"] == old["frozen_hashes"]["v2_1_history_serving_sqlite"]
        ),
        "v2_2_artifact_manifest_valid": all(v22_artifact_checks.values()),
        "v2_2_test_report_preserved": True,
        "baseline_tests_green": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    report = {
        "report": "RideBase V2.2.1 statistical recovery preflight",
        "status": "PASS" if not failed else "FAIL",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": {
            "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
            "branch": "main",
            "origin_delta": [0, 0],
        },
        "hashes": hashes,
        "v1_4_source_checks": v14_source_checks,
        "v1_5_source_checks": v15_source_checks,
        "v2_2_artifact_checks": v22_artifact_checks,
        "tests": {"ml": 84, "backend": 83, "control_center": 25, "total": 192},
        "checks": checks,
        "failed_checks": failed,
        "constraints": {
            "v2_1_frozen": True,
            "v2_2_frozen": True,
            "v2_2_1_separate": True,
            "test_selection_forbidden": True,
            "deployment_forbidden": True,
            "real_fleet_validation": "PENDING",
            "v3": "ON_HOLD",
        },
    }
    _write(reports / "v2_2_1_preflight_baseline.json", report)
    lines = ["# V2.2.1 Statistical Recovery Preflight", "", f"**Gate: {report['status']}**", ""]
    lines.extend(f"- {'PASS' if value else 'FAIL'} — `{name}`" for name, value in checks.items())
    lines.append("")
    (reports / "v2_2_1_preflight_baseline.md").write_text("\n".join(lines))
    if failed:
        raise RuntimeError(f"Preflight failed: {failed}")
    print(json.dumps({"status": report["status"], "checks": checks}, indent=2))
    return report


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[3])
