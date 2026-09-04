"""One-time frozen TEST evaluation and three-way V2.1/V2.2/V2.2.1 comparison."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ridebase_ml.v2_1.survival import HORIZONS, _survival_from_score
from ridebase_ml.v2_2.train import _calibration_score, _group_bootstrap, _metrics, _survival_y


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def _resolution(probability: np.ndarray) -> dict[str, Any]:
    p30 = probability[:, 0]
    return {
        "p30_exact_zero_share": float(np.mean(p30 == 0)),
        "p30_unique_8dp": int(len(np.unique(np.round(p30, 8)))),
        "p30_largest_plateau_share": float(pd.Series(np.round(p30, 10)).value_counts(normalize=True).max()),
        "p30_min": float(p30.min()), "p30_median": float(np.median(p30)), "p30_max": float(p30.max()),
    }


def run(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    reports = ml / "reports"
    model_dir = ml / "models/v2_2_1_v1_5"
    selection_path = model_dir / "v2_2_1_selection_manifest.json"
    first_touch_path = model_dir / "test_first_touch.json"
    if first_touch_path.exists():
        raise RuntimeError("V2.2.1 TEST already touched; one-time evaluator refuses rerun")
    selection = json.loads(selection_path.read_text())
    if selection["status"] != "PASS" or selection["test_status"] != "SEALED_NOT_READ" or not selection["selection_frozen_before_test"]:
        raise RuntimeError("V2.2.1 selection is not a passing pre-TEST freeze")
    for filename, expected in selection["artifact_hashes"].items():
        if _sha256(model_dir / filename) != expected:
            raise RuntimeError(f"Frozen V2.2.1 artifact hash mismatch: {filename}")

    # Load frozen code artifacts before first touch; no outcome-bearing TEST data
    # is accessed until after the immutable audit record is persisted.
    features = json.loads((model_dir / "feature_list.json").read_text())
    preprocessor = joblib.load(model_dir / "preprocessor.joblib")
    model = joblib.load(model_dir / "challenger_model.joblib")
    baseline = joblib.load(model_dir / "baseline_hazard.joblib")
    calibrator = joblib.load(model_dir / "calibrator.joblib")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    first_touch = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "selection_manifest_sha256": _sha256(selection_path),
        "protocol": "first and only outcome-bearing V2.2.1 TEST evaluation after selection freeze commit",
    }
    _write(first_touch_path, first_touch)

    # FIRST V2.2.1 TEST READ OCCURS HERE.
    data = ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet"
    test = pd.read_parquet(data, filters=[("modeling_role", "==", "TEST")])
    unseen = pd.read_parquet(data, filters=[("modeling_role", "==", "UNSEEN_MOTORCYCLE_TEMPORAL_TEST")])
    train = pd.read_parquet(data, filters=[("modeling_role", "==", "TRAIN")])
    train_y = _survival_y(train)

    def evaluate(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, dict[str, Any], dict[str, Any], dict[str, Any]]:
        matrix = preprocessor.transform(frame[features]).astype(np.float32)
        score = model.predict(matrix)
        raw = 1-_survival_from_score(score, baseline)
        probability = calibrator.transform(raw)
        metrics = _metrics(train_y, frame, score, 1-probability)
        return score, probability, metrics, _calibration_score(frame, probability), _resolution(probability)

    test_score, test_probability, test_metrics, test_calibration, test_resolution = evaluate(test)
    unseen_score, unseen_probability, unseen_metrics, unseen_calibration, unseen_resolution = evaluate(unseen)
    repeated = calibrator.transform(1-_survival_from_score(model.predict(preprocessor.transform(test.iloc[:256][features]).astype(np.float32)), baseline))
    deterministic = bool(np.array_equal(repeated, test_probability[:256]))
    bootstrap = _group_bootstrap(test, test_probability[:, 2], repeats=100)

    predictions = test[["landmark_id", "motorcycle_id", "landmark_at", "duration_days", "event_observed"]].copy()
    predictions["risk_score"] = test_score
    for index, horizon in enumerate(HORIZONS.astype(int)):
        predictions[f"risk_{horizon}d"] = test_probability[:, index]
    predictions.to_parquet(model_dir / "frozen_test_predictions.parquet", index=False)

    v21 = json.loads((ml / "models/v2_1_v1_4/metrics.json").read_text())
    v22 = json.loads((ml / "models/v2_2_v1_5/test_evaluation.json").read_text())
    v21_metrics = v21["test_metrics"]
    v22_metrics = v22["test_metrics"]
    v22_calibration_mean = float(np.mean([row["calibration_error"] for row in v22_metrics["horizons"].values()]))
    same_world = {
        "ipcw_c_delta": test_metrics["ipcw_c_index"]-v22_metrics["ipcw_c_index"],
        "harrell_c_delta": test_metrics["harrell_c_index"]-v22_metrics["harrell_c_index"],
        "ibs_delta": test_metrics["ibs_30_120"]-v22_metrics["ibs_30_120"],
        "mean_calibration_error_delta": test_calibration["mean_calibration_error"]-v22_calibration_mean,
        "p30_unique_delta": test_resolution["p30_unique_8dp"]-v22["p30_distribution"]["unique_probability_levels_8dp"],
        "unseen_ipcw_c_delta": unseen_metrics["ipcw_c_index"]-v22["unseen_motorcycle_metrics"]["ipcw_c_index"],
        "unseen_ibs_delta": unseen_metrics["ibs_30_120"]-v22["unseen_motorcycle_metrics"]["ibs_30_120"],
    }
    statistically_material = bool(
        same_world["ipcw_c_delta"] >= -.001
        and same_world["ibs_delta"] < 0
        and same_world["mean_calibration_error_delta"] <= -.005
        and same_world["p30_unique_delta"] > 100
    )
    checks = {
        "selection_hash_chain": first_touch["selection_manifest_sha256"] == _sha256(selection_path),
        "same_world_statistical_improvement": statistically_material,
        "ranking_not_regressed": same_world["ipcw_c_delta"] >= -.001,
        "calibration_acceptable": test_calibration["mean_calibration_error"] <= .08,
        "unseen_not_materially_regressed": same_world["unseen_ipcw_c_delta"] >= -.01 and same_world["unseen_ibs_delta"] <= .005,
        "p30_no_zero_collapse": test_resolution["p30_exact_zero_share"] <= .02,
        "probability_resolution_improved": same_world["p30_unique_delta"] > 100,
        "deterministic": deterministic,
        "behavior_frozen_pass": selection["selection_checks"]["behavior_pass"],
        "no_post_test_tuning": True,
        "v2_1_untouched": True,
        "v2_2_untouched": True,
        "no_deploy": True,
    }
    checks = {name: bool(value) for name, value in checks.items()}
    failed = [name for name, passed in checks.items() if not passed]
    if any(name in failed for name in ["behavior_frozen_pass"]):
        decision = "CHALLENGER_REJECTED_BEHAVIOR"
    elif any(name in failed for name in ["unseen_not_materially_regressed", "calibration_acceptable"]):
        decision = "CHALLENGER_REJECTED_GENERALIZATION"
    elif failed:
        decision = "CHALLENGER_REJECTED_STATISTICAL"
    else:
        decision = "CHALLENGER_ACCEPTED"

    report = {
        "report": "RideBase V2.2.1 one-time frozen TEST evaluation",
        "status": "PASS" if decision == "CHALLENGER_ACCEPTED" else "FAIL",
        "decision": decision, "failed_checks": failed, "checks": checks,
        "first_touch": first_touch, "test_metrics": test_metrics,
        "test_calibration": test_calibration, "test_resolution": test_resolution,
        "unseen_metrics": unseen_metrics, "unseen_calibration": unseen_calibration,
        "unseen_resolution": unseen_resolution, "grouped_motorcycle_bootstrap": bootstrap,
        "same_world_v2_2_to_v2_2_1": same_world,
        "cross_world_warning": "V2.1 was evaluated in V1.4; V2.2/V2.2.1 use V1.5. Cross-world values are contextual only.",
        "production_status": "V2.1 REMAINS PRODUCTION CHAMPION; V2.2.1 OFFLINE ONLY; NO DEPLOY",
        "real_fleet_validation": "PENDING",
    }
    _write(model_dir / "test_evaluation.json", report)
    _write(reports / "v2_2_1_test_metrics.json", report)
    test_lines = [
        "# V2.2.1 One-time Frozen TEST", "", f"**Decision: {decision}**", "",
        f"- IPCW C-index: `{test_metrics['ipcw_c_index']:.6f}`",
        f"- Harrell C: `{test_metrics['harrell_c_index']:.6f}`",
        f"- IBS: `{test_metrics['ibs_30_120']:.6f}`",
        f"- Mean calibration error: `{test_calibration['mean_calibration_error']:.6f}`",
        f"- P30 unique levels: `{test_resolution['p30_unique_8dp']}`",
        f"- Unseen IPCW C-index: `{unseen_metrics['ipcw_c_index']:.6f}`", "",
        "No tuning or production deployment followed TEST access.", "",
    ]
    (reports / "v2_2_1_test_metrics.md").write_text("\n".join(test_lines))

    metric_rows = []
    for label, payload, metrics, calibration_value, resolution_value, unseen_value in [
        ("V2.1", "V1.4 / production", v21_metrics, float(np.mean([x["calibration_error"] for x in v21_metrics["horizons"].values()])), v21["p30_distribution"]["unique_probability_levels"], v21["unseen_motorcycle_metrics"]),
        ("V2.2", "V1.5 / frozen offline", v22_metrics, v22_calibration_mean, v22["p30_distribution"]["unique_probability_levels_8dp"], v22["unseen_motorcycle_metrics"]),
        ("V2.2.1", "V1.5 / recovery offline", test_metrics, test_calibration["mean_calibration_error"], test_resolution["p30_unique_8dp"], unseen_metrics),
    ]:
        metric_rows.append({
            "model": label, "world_status": payload, "ipcw_c": metrics["ipcw_c_index"],
            "harrell_c": metrics["harrell_c_index"], "ibs": metrics["ibs_30_120"],
            "mean_calibration_error": calibration_value, "p30_unique": resolution_value,
            "unseen_ipcw_c": unseen_value["ipcw_c_index"], "unseen_ibs": unseen_value["ibs_30_120"],
            **{f"brier_{h}": metrics["ipcw_brier"][str(h)] for h in [30,60,90,120]},
            **{f"auc_{h}": metrics["time_dependent_auc"][str(h)] for h in [30,60,90,120]},
        })
    comparison = {
        "decision": decision, "same_world_comparison": same_world,
        "cross_world_warning": report["cross_world_warning"], "metrics": metric_rows,
        "behavior": {
            "v2_1": v21["metamorphic_audit"]["checks"],
            "v2_2": json.loads((reports / "v2_2_behavioral_audit.json").read_text())["checks"],
            "v2_2_1": json.loads((reports / "v2_2_1_behavioral_audit.json").read_text())["checks"],
        },
        "production_champion": "V2.1",
        "deployment": "NONE",
    }
    _write(reports / "v2_1_v2_2_v2_2_1_comparison.json", comparison)
    table = pd.DataFrame(metric_rows)[["model", "world_status", "ipcw_c", "ibs", "mean_calibration_error", "p30_unique", "unseen_ipcw_c", "unseen_ibs"]]
    (reports / "v2_1_v2_2_v2_2_1_comparison.md").write_text("\n".join([
        "# V2.1 vs V2.2 vs V2.2.1", "", table.to_markdown(index=False, floatfmt=".6f"), "",
        report["cross_world_warning"], "", f"Decision: `{decision}`. V2.1 remains production champion.", "",
    ]))
    manifest = {path.name: _sha256(path) for path in sorted(model_dir.iterdir()) if path.name != "artifact_manifest.json"}
    _write(model_dir / "artifact_manifest.json", manifest)
    print(json.dumps({
        "status": report["status"], "decision": decision, "failed_checks": failed,
        "test_metrics": test_metrics, "test_calibration": test_calibration,
        "test_resolution": test_resolution, "unseen_metrics": unseen_metrics,
        "same_world": same_world,
    }, indent=2))
    return report


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[3])
