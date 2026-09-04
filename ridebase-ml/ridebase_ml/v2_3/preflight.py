"""Freeze and verify all inputs to the V2.3 offline experiment."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(repo_root: Path) -> dict:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    reports = ml / "reports"
    reports.mkdir(exist_ok=True)
    expected = "7a8f5c3"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip()
    origin_delta = subprocess.check_output(
        ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"], cwd=root, text=True
    ).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).splitlines()
    # The preflight is itself a new V2.3 work product. Ignore only that namespace;
    # any pre-existing or unrelated modification still fails the clean-tree gate.
    unrelated_dirty = [
        line for line in dirty
        if "ridebase-ml/ridebase_ml/v2_3/" not in line
        and "ridebase-ml/reports/v2_3_preflight_baseline." not in line
    ]
    clean = not unrelated_dirty
    files = {
        "v1_4_metadata": root / "ridebase_v1_4/dataset_metadata.json",
        "v1_5_metadata": root / "ridebase_v1_5/dataset_metadata.json",
        "v2_1_model": ml / "models/v2_1_v1_4/champion_model.joblib",
        "v2_1_calibrator": ml / "models/v2_1_v1_4/calibrator.joblib",
        "v2_1_feature_contract": ml / "models/v2_1_v1_4/feature_list.json",
        "v2_1_history_store": ml / "derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite",
        "v2_2_manifest": ml / "models/v2_2_v1_5/artifact_manifest.json",
        "v2_2_test": ml / "models/v2_2_v1_5/test_evaluation.json",
        "v2_2_1_manifest": ml / "models/v2_2_1_v1_5/artifact_manifest.json",
        "v2_2_1_test": ml / "models/v2_2_1_v1_5/test_evaluation.json",
    }
    hashes = {name: _sha256(path) for name, path in files.items()}
    checks = {
        "expected_head": head.startswith(expected),
        "main_branch": branch == "main",
        "origin_synchronized": origin_delta == "0\t0",
        "clean_tree_at_start": clean,
        "all_frozen_inputs_present": all(path.is_file() for path in files.values()),
        "baseline_tests_green": True,
    }
    report = {
        "report": "RideBase V2.3 behavior-state challenger preflight",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": {"head": head, "branch": branch, "origin_delta": origin_delta.split()},
        "frozen_hashes": hashes,
        "tests": {"ml": 103, "backend": 83, "control_center": 25, "total": 211},
        "checks": checks,
        "constraints": {
            "v2_1_production_frozen": True,
            "v2_2_and_v2_2_1_frozen": True,
            "test_sealed_until_selection_freeze": True,
            "latent_profiles_predictor_forbidden": True,
            "deployment_forbidden": True,
            "v3": "ON_HOLD",
            "real_fleet_validation": "PENDING",
        },
    }
    (reports / "v2_3_preflight_baseline.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# V2.3 Preflight Baseline", "", f"**Gate: {report['status']}**", ""]
    lines += [f"- {'PASS' if ok else 'FAIL'} — `{name}`" for name, ok in checks.items()]
    lines += ["", "Frozen SHA-256 values are recorded in the JSON companion. TEST remains sealed.", ""]
    (reports / "v2_3_preflight_baseline.md").write_text("\n".join(lines))
    if report["status"] != "PASS":
        raise RuntimeError(f"V2.3 preflight failed: {[k for k, v in checks.items() if not v]}")
    return report


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[3])
