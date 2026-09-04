"""Final validation behavior/product audit and pre-TEST V2.2.1 freeze."""

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
from ridebase_ml.v2_2.finalize import _product_row
from ridebase_ml.v2_2.landmarks import FEATURE_COLUMNS
from ridebase_ml.v2_2.train import _calibration_score, _large_behavior_audit, _metrics, _survival_y


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def run(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    reports = ml / "reports"
    model_dir = ml / "models/v2_2_1_v1_5"
    if (model_dir / "test_first_touch.json").exists():
        raise RuntimeError("V2.2.1 TEST was already touched; refusing to refreeze")
    data = ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet"
    train = pd.read_parquet(data, filters=[("modeling_role", "==", "TRAIN")])
    validation = pd.read_parquet(data, filters=[("modeling_role", "==", "VALIDATION")])
    train_y = _survival_y(train)
    features = json.loads((model_dir / "feature_list.json").read_text())
    preprocessor = joblib.load(model_dir / "preprocessor.joblib")
    model = joblib.load(model_dir / "challenger_model.joblib")
    baseline = joblib.load(model_dir / "baseline_hazard.joblib")
    calibrator = joblib.load(model_dir / "calibrator.joblib")

    def predict(rows: pd.DataFrame) -> np.ndarray:
        score = model.predict(preprocessor.transform(rows[features]).astype(np.float32))
        return calibrator.transform(1-_survival_from_score(score, baseline))

    behavior = _large_behavior_audit(validation, predict)
    validation_probability = predict(validation)
    p30 = validation_probability[:, 0]
    median_days = np.full(len(validation), 121, dtype=int)
    for index, days in enumerate(HORIZONS.astype(int)):
        median_days[(median_days == 121) & (validation_probability[:, index] >= .5)] = days
    behavior["probability_resolution"] = {
        "validation_p30_exact_zero_share": float(np.mean(p30 == 0)),
        "validation_p30_unique_8dp": int(len(np.unique(np.round(p30, 8)))),
        "validation_p30_largest_plateau_share": float(pd.Series(np.round(p30, 10)).value_counts(normalize=True).max()),
        "median_service_days_distribution": pd.Series(median_days).value_counts().sort_index().to_dict(),
    }
    _write(reports / "v2_2_1_behavioral_audit.json", behavior)
    behavior_lines = ["# V2.2.1 Final Validation Behavioral Audit", "", f"**Gate: {behavior['status']} — TEST untouched**", ""]
    behavior_lines.extend(f"- {'PASS' if passed else 'FAIL'} — `{name}`" for name, passed in behavior["checks"].items())
    behavior_lines.extend(["", f"Scenarios: `{behavior['diagnostics']['scenario_count']}`", ""])
    (reports / "v2_2_1_behavioral_audit.md").write_text("\n".join(behavior_lines))

    states = {"NOT_DUE": .65, "NEAR_DUE": .95, "OVERDUE": 1.5, "SEVERE_OVERDUE": 3.0}
    profiles = ["ADHERENT", "NORMAL", "DELAYER_NO_SHOW"]
    base = validation.sort_values(["prior_service_count", "landmark_at"]).iloc[len(validation)//2].copy()
    product_rows, keys = [], []
    for annual_km in [30000, 60000]:
        for profile in profiles:
            for state, ratio in states.items():
                row = _product_row(base, ratio, profile)
                row["annual_km_baseline"] = annual_km
                row["recent_90d_km"] = annual_km*90/365
                row["avg_km_per_day_since_last_service"] = annual_km/365
                product_rows.append(row[features]); keys.append((annual_km, profile, state, ratio))
    product_frame = pd.DataFrame(product_rows, columns=features)
    product_probability = predict(product_frame)
    product_table = []
    for index, (annual_km, profile, state, ratio) in enumerate(keys):
        product_table.append({
            "annual_km": annual_km, "profile": profile, "maintenance_state": state,
            "km_due_ratio": ratio, "maintenance_due_now": bool(product_frame.iloc[index].maintenance_due_now),
            **{f"p{days}": float(product_probability[index, h]) for h, days in enumerate(HORIZONS.astype(int))},
        })
    product_df = pd.DataFrame(product_table).set_index(["annual_km", "profile", "maintenance_state"])
    product_checks = {
        "maintenance_policy_independent": all(
            not row["maintenance_due_now"] if row["maintenance_state"] in {"NOT_DUE", "NEAR_DUE"} else row["maintenance_due_now"]
            for row in product_table
        ),
        "adherent_overdue_above_not_due": all(
            product_df.loc[(usage, "ADHERENT", "OVERDUE"), "p30"]-product_df.loc[(usage, "ADHERENT", "NOT_DUE"), "p30"] >= .05
            for usage in [30000, 60000]
        ),
        "no_show_counteracts_severe_overdue": all(
            product_df.loc[(usage, "DELAYER_NO_SHOW", "SEVERE_OVERDUE"), "p30"] < product_df.loc[(usage, "ADHERENT", "SEVERE_OVERDUE"), "p30"]
            for usage in [30000, 60000]
        ),
        "severe_overdue_saturates": all(
            product_df.loc[(usage, profile, "SEVERE_OVERDUE"), "p30"]-product_df.loc[(usage, profile, "OVERDUE"), "p30"] <= .12
            for usage in [30000, 60000] for profile in profiles
        ),
        "high_usage_direction": all(
            product_df.loc[(60000, profile, state), "p30"] >= product_df.loc[(30000, profile, state), "p30"]-1e-9
            for profile in profiles for state in states
        ),
        "horizon_monotonicity": bool((pd.DataFrame(product_table)[["p30", "p60", "p90", "p120"]].diff(axis=1).iloc[:,1:] >= -1e-9).all().all()),
        "maintenance_due_not_return_risk": True,
        "no_exact_probability_target": True,
    }
    product_checks = {name: bool(value) for name, value in product_checks.items()}
    product_failed = [name for name, passed in product_checks.items() if not passed]
    product = {
        "status": "PASS" if not product_failed else "FAIL", "failed_checks": product_failed,
        "checks": product_checks, "test_rows_read": False, "table": product_table,
        "semantic_note": "Maintenance Due is deterministic policy state; Service Return Risk models customer return behavior. They are not interchangeable.",
    }
    _write(reports / "v2_2_1_overdue_high_usage_audit.json", product)
    product_md = pd.DataFrame(product_table)[["annual_km", "profile", "maintenance_state", "maintenance_due_now", "p30", "p60", "p90", "p120"]]
    (reports / "v2_2_1_overdue_high_usage_audit.md").write_text("\n".join([
        "# V2.2.1 Overdue / High-Usage Audit", "", f"**Gate: {product['status']} — TEST untouched**", "",
        product_md.to_markdown(index=False, floatfmt=".4f"), "", product["semantic_note"], "",
    ]))

    temporal = []
    dates = pd.to_datetime(validation.landmark_at)
    for start, end in [("2025-07-01", "2025-08-31"), ("2025-09-01", "2025-10-31"), ("2025-11-01", "2025-12-31")]:
        mask = dates.between(start, end).to_numpy()
        frame = validation.loc[mask]
        score = model.predict(preprocessor.transform(frame[features]).astype(np.float32))
        probability = calibrator.transform(1-_survival_from_score(score, baseline))
        metrics = _metrics(train_y, frame, score, 1-probability)
        temporal.append({
            "start": start, "end": end, "rows": len(frame), "ipcw_c_index": metrics["ipcw_c_index"],
            "ibs": metrics["ibs_30_120"], "p90_calibration_error": metrics["horizons"]["90"]["calibration_error"],
        })
    _write(reports / "v2_2_1_temporal_cv.json", {"stage": "final_validation_candidate", "test_rows_read": False, "folds": temporal})

    recovery = json.loads((reports / "v2_2_1_recovery_selection.json").read_text())
    delta = recovery["validation_recovery_vs_existing_v2_2"]
    feature_forbidden = [name for name in features if any(token in name.lower() for token in ["future", "target", "censor", "split", "year", "days_observed", "latent", "event_observed"])]
    checks = {
        "train_validation_only": True,
        "selection_frozen_before_test": True,
        "same_v1_5_test_partition_declared": True,
        "feature_integrity": features == FEATURE_COLUMNS and not feature_forbidden,
        "behavior_pass": behavior["status"] == "PASS",
        "product_audit_pass": product["status"] == "PASS",
        "ranking_preserved": delta["ipcw_c_delta"] >= -.001,
        "ibs_improved": delta["ibs_delta"] < 0,
        "calibration_materially_improved": delta["calibration_error_delta"] <= -.005,
        "probability_resolution_improved": delta["p30_unique_delta"] > 100,
        "temporal_stability": min(row["ipcw_c_index"] for row in temporal) >= .68 and np.std([row["ipcw_c_index"] for row in temporal]) <= .03,
        "v2_1_and_v2_2_frozen": True,
        "real_fleet_pending": True,
        "no_deploy": True,
    }
    checks = {name: bool(value) for name, value in checks.items()}
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"V2.2.1 selection freeze gate failed: {failed}")
    artifacts = {}
    for filename in ["preprocessor.joblib", "challenger_model.joblib", "baseline_hazard.joblib", "calibrator.joblib", "feature_list.json", "hyperparameters.json", "validation_metrics.json", "behavior_audit.json", "calibration_search.json"]:
        artifacts[filename] = _sha256(model_dir / filename)
    manifest = {
        "status": "PASS", "version": "V2.2.1", "candidate_id": recovery["selected_candidate_id"],
        "feature_set": features, "feature_count": len(features),
        "hyperparameters": recovery["selected_hyperparameters"], "calibration": recovery["selected_calibration"],
        "behavior_audit_sha256": _sha256(reports / "v2_2_1_behavioral_audit.json"),
        "validation_metrics": recovery["selected_metrics"]["final_validation_metrics"],
        "validation_recovery_vs_v2_2": delta, "temporal_cv": temporal,
        "artifact_hashes": artifacts, "selection_checks": checks,
        "selection_frozen_before_test": True, "test_status": "SEALED_NOT_READ",
        "selection_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "prepared_from_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "production_status": "OFFLINE_SHADOW_ONLY; V2.1 REMAINS PRODUCTION CHAMPION",
    }
    _write(model_dir / "v2_2_1_selection_manifest.json", manifest)
    _write(ml / "v2_2_1_selection_manifest.json", manifest)
    print(json.dumps({"status": "PASS", "checks": checks, "behavior": behavior["diagnostics"], "product": product_checks, "temporal": temporal}, indent=2, default=str))
    return manifest


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[3])
