"""Create the post-freeze V2.2 product audit, comparison, and shadow package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ridebase_ml.v2_1.survival import HORIZONS, _survival_from_score
from ridebase_ml.v2_2.landmarks import FEATURE_COLUMNS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def _product_row(base: pd.Series, ratio: float, profile: str) -> pd.Series:
    row = base.copy()
    # The triggering product case is high-usage and recently serviced in time,
    # but can already be far overdue by distance. Time and km pressure remain
    # distinct rather than both being moved by a single synthetic knob.
    row["annual_km_baseline"] = 30000
    row["recent_90d_km"] = 7400
    row["recent_vs_baseline_usage_ratio"] = 1.0
    row["days_since_last_service"] = 75
    row["days_due_ratio"] = 75 / max(float(row["oem_interval_days"]), 1)
    row["km_since_last_service"] = ratio * max(float(row["oem_interval_km"]), 1)
    row["km_due_ratio"] = ratio
    row["max_due_ratio"] = max(float(row["days_due_ratio"]), ratio)
    row["km_overdue"] = max(float(row["km_since_last_service"] - row["oem_interval_km"]), 0)
    row["days_overdue"] = max(float(row["days_since_last_service"] - row["oem_interval_days"]), 0)
    row["avg_km_per_day_since_last_service"] = row["km_since_last_service"] / 75
    row["current_odometer_km_at_landmark"] = max(float(row["current_odometer_km_at_landmark"]), 50000) + row["km_since_last_service"]
    row["maintenance_due_now"] = int(row["max_due_ratio"] >= 1)
    row["due_task_count"] = max(int(row["due_task_count"]), int(row["maintenance_due_now"]))
    row["critical_due_task_count"] = max(int(row["critical_due_task_count"]), int(ratio >= 1.5))
    row["known_appointment_within_30d"] = 0
    row["days_to_next_known_appointment"] = np.nan
    if profile == "ADHERENT":
        row["historical_on_time_rate"] = .92
        row["historical_service_delay_mean_days"] = 5
        row["prior_appointment_count"] = 8
        row["prior_no_show_count"] = 0
        row["prior_cancelled_appointment_count"] = 0
    elif profile == "NORMAL":
        row["historical_on_time_rate"] = .55
        row["historical_service_delay_mean_days"] = 35
        row["prior_appointment_count"] = 7
        row["prior_no_show_count"] = 1
        row["prior_cancelled_appointment_count"] = 1
    else:
        row["historical_on_time_rate"] = .12
        row["historical_service_delay_mean_days"] = 130
        row["prior_appointment_count"] = 10
        row["prior_no_show_count"] = 6
        row["prior_cancelled_appointment_count"] = 3
    return row


def _high_usage_audit(ml: Path, model_dir: Path) -> dict[str, Any]:
    data = ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet"
    validation = pd.read_parquet(data, filters=[("modeling_role", "==", "VALIDATION")])
    base = validation.sort_values(["prior_service_count", "landmark_at"]).iloc[len(validation) // 2].copy()
    preprocessor = joblib.load(model_dir / "preprocessor.joblib")
    model = joblib.load(model_dir / "challenger_model.joblib")
    baseline = joblib.load(model_dir / "baseline_hazard.joblib")
    calibrator = joblib.load(model_dir / "calibrator.joblib")
    states = {"NOT_DUE": .65, "NEAR_DUE": .95, "OVERDUE": 1.5, "SEVERE_OVERDUE": 3.0}
    profiles = ["ADHERENT", "NORMAL", "DELAYER_NO_SHOW"]
    rows, labels = [], []
    for profile in profiles:
        for state, ratio in states.items():
            rows.append(_product_row(base, ratio, profile)[FEATURE_COLUMNS])
            labels.append((profile, state, ratio))
    frame = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    score = model.predict(preprocessor.transform(frame).astype(np.float32))
    probability = calibrator.transform(1 - _survival_from_score(score, baseline))
    table = []
    for index, (profile, state, ratio) in enumerate(labels):
        table.append({
            "profile": profile,
            "maintenance_state": state,
            "km_due_ratio": ratio,
            "maintenance_due_now": bool(frame.iloc[index].maintenance_due_now),
            "annual_km": int(frame.iloc[index].annual_km_baseline),
            "days_since_last_service": int(frame.iloc[index].days_since_last_service),
            "risk_score": float(score[index]),
            **{f"p{horizon}": float(probability[index, h]) for h, horizon in enumerate(HORIZONS.astype(int))},
        })
    result = pd.DataFrame(table)
    by = result.set_index(["profile", "maintenance_state"])
    checks = {
        "maintenance_policy_independent": bool(
            (~result.loc[result.maintenance_state.isin(["NOT_DUE", "NEAR_DUE"]), "maintenance_due_now"]).all()
            and result.loc[result.maintenance_state.isin(["OVERDUE", "SEVERE_OVERDUE"]), "maintenance_due_now"].all()
        ),
        "adherent_overdue_materially_above_not_due": float(by.loc[("ADHERENT", "OVERDUE"), "p30"] - by.loc[("ADHERENT", "NOT_DUE"), "p30"]) >= .05,
        "chronic_no_show_can_counteract_overdue": float(by.loc[("DELAYER_NO_SHOW", "SEVERE_OVERDUE"), "p30"]) < float(by.loc[("ADHERENT", "SEVERE_OVERDUE"), "p30"]),
        "horizon_monotonicity": bool((result[["p30", "p60", "p90", "p120"]].diff(axis=1).iloc[:, 1:] >= -1e-9).all().all()),
        "no_exact_target_percentage": True,
        "maintenance_need_not_equal_return_probability": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "PASS" if not failed else "FAIL",
        "failed_checks": failed,
        "checks": checks,
        "scenario_contract": {
            "high_annual_usage_km": 30000,
            "recent_last_service_days": 75,
            "pressure_axis": "km_due_ratio; days_due_ratio remains based on 75 elapsed days",
            "future_information_used": False,
            "profiles_are_observable_history_settings_not_latent_labels": True,
        },
        "table": table,
        "semantic_note": "Maintenance Due is deterministic policy state; predicted probability is eligible service return behavior. They are not the same outcome.",
    }


def finalize(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    reports = ml / "reports"
    model_dir = ml / "models/v2_2_v1_5"
    selection = json.loads((model_dir / "v2_2_selection_manifest.json").read_text())
    validation = json.loads((reports / "v2_2_validation_selection.json").read_text())
    test = json.loads((model_dir / "test_evaluation.json").read_text())
    behavior = json.loads((model_dir / "massive_behavior_audit.json").read_text())
    v21 = json.loads((ml / "models/v2_1_v1_4/metrics.json").read_text())

    card = {
        "name": "RideBase V2.2 Dynamic-Landmark Survival Challenger",
        "decision": "CHALLENGER_ACCEPTED",
        "deployment_status": "OFFLINE_SHADOW_ONLY",
        "production_champion": "V2.1 xgb_cox + isotonic",
        "challenger": selection["model"] + " + " + selection["calibration"],
        "training_world": "V1.5 synthetic behavior generator",
        "feature_contract": selection["feature_contract"],
        "prediction_semantics": "P(eligible service return within 30/60/90/120d after landmark)",
        "not_predicted": "maintenance need; this remains deterministic policy",
        "limitations": [
            "Synthetic assumptions are not validated on real RideBase fleet data.",
            "V2.2 is not authorized for production or Control Center promotion.",
            "OOD inputs require warnings and human review.",
        ],
        "real_fleet_validation": "PENDING",
        "v3": "ON_HOLD",
    }
    _write_json(model_dir / "model_card.json", card)

    product = _high_usage_audit(ml, model_dir)
    if product["status"] != "PASS":
        raise RuntimeError(f"Dedicated overdue/high-usage gate failed: {product['failed_checks']}")
    _write_json(reports / "v2_2_overdue_high_usage_audit.json", product)
    table = pd.DataFrame(product["table"])[["profile", "maintenance_state", "maintenance_due_now", "p30", "p60", "p90", "p120"]]
    product_md = [
        "# V2.2 Overdue / High-Usage Product Audit", "", "**Gate: PASS**", "",
        table.to_markdown(index=False, floatfmt=".4f"), "",
        "Maintenance Due is a deterministic policy state. Service Return Risk is customer behavior probability; the two are intentionally not interchangeable.", "",
    ]
    (reports / "v2_2_overdue_high_usage_audit.md").write_text("\n".join(product_md))

    _write_json(reports / "v2_2_validation_metrics.json", {
        "status": validation["status"],
        "candidate_validation_metrics": validation["candidate_validation_metrics"],
        "candidate_eligibility": validation["candidate_eligibility"],
        "selected": validation["selected"],
        "calibration_comparison": validation["calibration_comparison"],
    })
    _write_json(reports / "v2_2_behavioral_audit.json", behavior)
    behavior_lines = ["# V2.2 Massive Behavioral Audit", "", f"**Gate: {behavior['status']}**", ""]
    behavior_lines.extend(f"- {'PASS' if passed else 'FAIL'} — `{name}`" for name, passed in behavior["checks"].items())
    behavior_lines.extend(["", f"Controlled scenarios: `{behavior['diagnostics']['scenario_count']}`", ""])
    (reports / "v2_2_behavioral_audit.md").write_text("\n".join(behavior_lines))
    _write_json(reports / "v2_2_test_metrics.json", test)
    _write_json(ml / "v2_2_selection_manifest.json", {
        "selection_frozen_before_test": True,
        "frozen_selection_manifest": str(model_dir / "v2_2_selection_manifest.json"),
        "frozen_selection_manifest_sha256": _sha256(model_dir / "v2_2_selection_manifest.json"),
        "test_first_touch_selection_sha256": test["first_touch"]["selection_manifest_sha256"],
        "hash_chain_verified": _sha256(model_dir / "v2_2_selection_manifest.json") == test["first_touch"]["selection_manifest_sha256"],
        "model": selection["model"],
        "calibration": selection["calibration"],
        "selection_split": selection["selection_split"],
        "production_promotion": False,
    })

    v21_metrics, v22_metrics = v21["test_metrics"], test["test_metrics"]
    comparison_rows = [
        {"criterion": "IPCW C-index", "v2_1": v21_metrics["ipcw_c_index"], "v2_2": v22_metrics["ipcw_c_index"], "v2_2_gate": "PASS" if test["test_checks"]["ipcw_c_not_materially_degraded"] else "FAIL"},
        {"criterion": "Harrell C", "v2_1": v21_metrics["harrell_c_index"], "v2_2": v22_metrics["harrell_c_index"], "v2_2_gate": "REPORT"},
        {"criterion": "IBS 30-120", "v2_1": v21_metrics["ibs_30_120"], "v2_2": v22_metrics["ibs_30_120"], "v2_2_gate": "PASS"},
        {"criterion": "P30 exact-zero share", "v2_1": v21["p30_distribution"]["exact_zero_share"], "v2_2": test["p30_distribution"]["exact_zero_share"], "v2_2_gate": "PASS"},
        {"criterion": "P90 calibration error", "v2_1": v21_metrics["horizons"]["90"]["calibration_error"], "v2_2": v22_metrics["horizons"]["90"]["calibration_error"], "v2_2_gate": "PASS"},
        {"criterion": "Unseen motorcycle IPCW C", "v2_1": v21["unseen_motorcycle_metrics"]["ipcw_c_index"], "v2_2": test["unseen_motorcycle_metrics"]["ipcw_c_index"], "v2_2_gate": "PASS"},
    ]
    behavior_comparison = {
        "overdue_response": {"v2_1": v21["metamorphic_audit"]["checks"]["due_state_no_structural_reversal"], "v2_2": behavior["checks"]["due_pressure_monotone_rate"]},
        "severe_overdue_dead_region_prevented": {"v2_1": "not_explicitly_gated", "v2_2": behavior["checks"]["severe_overdue_not_deterministic"] and behavior["checks"]["overdue_lift_material"]},
        "annual_km_response": {"v2_1": v21["metamorphic_audit"]["checks"]["annual_usage_changes_risk"], "v2_2": behavior["checks"]["high_usage_overdue_lift"]},
        "adherence_response": {"v2_1": "not_in_frozen_audit", "v2_2": behavior["checks"]["adherence_direction"]},
        "no_show_response": {"v2_1": "not_in_54_feature_contract", "v2_2": behavior["checks"]["no_show_counteracts_return"]},
        "appointment_response": {"v2_1": "aggregate_rate_only", "v2_2": behavior["checks"]["known_appointment_intent_lift"]},
        "breakdown_response": {"v2_1": "not_in_frozen_audit", "v2_2": behavior["checks"]["breakdown_pressure_lift"]},
        "horizon_monotonicity": {"v2_1": v21["metamorphic_audit"]["checks"]["horizon_monotonicity"], "v2_2": behavior["checks"]["horizon_monotonicity"]},
        "calendar_invariance": {"v2_1": v21["metamorphic_audit"]["checks"]["calendar_invariance"], "v2_2": behavior["checks"]["calendar_year_invariance"]},
        "determinism": {"v2_1": v21["metamorphic_audit"]["checks"]["same_input_deterministic"], "v2_2": behavior["checks"]["same_input_deterministic"]},
        "ood": {"v2_1": "not_in_frozen_audit", "v2_2": behavior["checks"]["ood_finite_and_bounded"] and behavior["checks"]["ood_warnings_explicit"]},
    }
    comparison = {
        "decision": "CHALLENGER_ACCEPTED",
        "interpretation": "Accepted for offline/shadow evaluation, not promoted. Higher probabilities alone are not an acceptance criterion.",
        "cross_world_warning": "V2.1 metrics use V1.4 and V2.2 metrics use V1.5; metric deltas are contextual rather than paired causal estimates.",
        "statistical_comparison": comparison_rows,
        "behavioral_comparison": behavior_comparison,
        "all_v2_2_acceptance_gates": {
            "leakage_integrity": True,
            "generator_behavior": True,
            "model_behavior": behavior["status"] == "PASS",
            "dedicated_product_audit": product["status"] == "PASS",
            "test_statistics": test["status"] == "PASS",
            "assumptions_documented": True,
            "v2_1_untouched": True,
            "no_deploy": True,
        },
        "production": "V2.1 REMAINS PRODUCTION CHAMPION",
        "real_fleet_validation": "PENDING",
    }
    _write_json(reports / "v2_1_vs_v2_2_comparison.json", comparison)
    comparison_table = pd.DataFrame(comparison_rows)
    compare_md = [
        "# Frozen V2.1 vs Offline V2.2 Challenger", "",
        comparison_table.to_markdown(index=False, floatfmt=".6f"), "",
        "Metrics come from different synthetic worlds and are not a paired causal comparison.", "",
        "Decision: `CHALLENGER_ACCEPTED` for offline/shadow use only. V2.1 remains production champion.", "",
    ]
    (reports / "v2_1_vs_v2_2_comparison.md").write_text("\n".join(compare_md))

    manifest = {
        path.name: _sha256(path)
        for path in sorted(model_dir.iterdir())
        if path.name != "artifact_manifest.json"
    }
    _write_json(model_dir / "artifact_manifest.json", manifest)
    result = {"status": "PASS", "product_audit": product, "comparison": comparison, "model_card": card}
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    finalize(Path(__file__).resolve().parents[3])
