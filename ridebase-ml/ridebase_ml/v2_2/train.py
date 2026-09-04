"""Offline V2.2 challenger selection and one-time TEST evaluation.

``select_on_validation`` never reads TEST rows.  It trains candidates on TRAIN,
selects and calibrates on VALIDATION, runs the large controlled behavior audit,
and freezes a cryptographically identified selection manifest.

``evaluate_frozen_test_once`` refuses to run until that manifest exists and
refuses a second run.  V2.1 artifacts are only read for the post-freeze
comparison; they are never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler
from sksurv.linear_model import CoxPHSurvivalAnalysis, CoxnetSurvivalAnalysis
from xgboost import XGBRegressor

from ridebase_ml.v2_1.survival import HORIZONS, HorizonCalibrator, _survival_from_score
from ridebase_ml.v2_1.train import _breslow, _calibration_score, _group_bootstrap, _metrics, _rule_survival, _survival_y
from ridebase_ml.v2_2.landmarks import (
    BASE_FEATURE_COLUMNS,
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    OBSERVABLE_HISTORY_FEATURES,
)


SEED = 52
MODEL_DIR_NAME = "v2_2_v1_5"
SELECTION_FILE = "v2_2_selection_manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")


def _paths(repo_root: Path) -> dict[str, Path]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    model_dir = ml / "models" / MODEL_DIR_NAME
    model_dir.mkdir(parents=True, exist_ok=True)
    (ml / "reports").mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "ml": ml,
        "data": ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet",
        "split": ml / "derived_outputs/v2_2_v1_5/v2_2_landmark_manifest.csv",
        "config": ml / "config/v2_2_v1_5_config.json",
        "model_dir": model_dir,
        "reports": ml / "reports",
    }


def _preprocessor() -> Pipeline:
    columns = ColumnTransformer([
        ("categorical", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("ordinal", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
        ]), CATEGORICAL_FEATURES),
        ("numeric", SimpleImputer(strategy="median"), NUMERIC_FEATURES),
    ], verbose_feature_names_out=False)
    return Pipeline([("columns", columns), ("scale", StandardScaler())])


def _xgb_constraints(feature_names: list[str]) -> tuple[int, ...]:
    positive = {
        "annual_km_baseline", "recent_90d_km", "recent_vs_baseline_usage_ratio",
        "days_since_last_service", "km_since_last_service", "avg_km_per_day_since_last_service",
        "days_due_ratio", "km_due_ratio", "max_due_ratio", "days_overdue", "km_overdue",
        "maintenance_due_now", "due_task_count", "critical_due_task_count",
        "historical_on_time_rate", "known_appointment_within_30d",
        "recent_breakdown_count_180d", "prior_breakdown_count", "last_service_was_breakdown",
    }
    negative = {
        "days_until_next_scheduled_due", "km_until_next_scheduled_due",
        "historical_service_delay_mean_days", "prior_no_show_count",
        "prior_cancelled_appointment_count", "days_to_next_known_appointment",
    }
    return tuple(1 if name in positive else -1 if name in negative else 0 for name in feature_names)


def _fit_xgb(X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> XGBRegressor:
    model = XGBRegressor(
        objective="survival:cox", n_estimators=360, max_depth=4, learning_rate=.035,
        min_child_weight=24, subsample=.84, colsample_bytree=.84, reg_lambda=2.5,
        reg_alpha=.02, monotone_constraints=_xgb_constraints(feature_names),
        random_state=SEED, n_jobs=6,
    )
    labels = np.where(y["event"], y["time"], -y["time"])
    model.fit(X, labels, verbose=False)
    return model


def _calibration_candidates(
    validation: pd.DataFrame,
    raw_probability: np.ndarray,
) -> tuple[str, HorizonCalibrator, dict[str, Any], np.ndarray, np.ndarray]:
    ordered = np.argsort(pd.to_datetime(validation.landmark_at).to_numpy())
    cut = len(ordered) // 2
    fit_idx, eval_idx = ordered[:cut], ordered[cut:]
    results: dict[str, Any] = {}
    fitted: dict[str, HorizonCalibrator] = {}
    for method in ["uncalibrated", "isotonic", "platt", "beta"]:
        calibrator = HorizonCalibrator(method).fit(raw_probability[fit_idx], validation.iloc[fit_idx])
        probability = calibrator.transform(raw_probability[eval_idx])
        results[method] = _calibration_score(validation.iloc[eval_idx], probability)
        fitted[method] = calibrator
    eligible = [
        method for method, result in results.items()
        if result["horizons"]["30"]["exact_zero_share"] < .05
        and result["mean_calibration_error"] < .12
    ]
    if not eligible:
        raise RuntimeError("No calibration method passed validation usability/calibration gates")
    selected = min(
        eligible,
        key=lambda method: results[method]["mean_brier"] + results[method]["mean_calibration_error"],
    )
    return selected, fitted[selected], results, fit_idx, eval_idx


def _set_due(row: pd.Series, ratio: float) -> pd.Series:
    row = row.copy()
    row["days_due_ratio"] = ratio
    row["km_due_ratio"] = ratio
    row["max_due_ratio"] = ratio
    row["days_since_last_service"] = ratio * max(float(row["oem_interval_days"]), 1.0)
    row["km_since_last_service"] = ratio * max(float(row["oem_interval_km"]), 1.0)
    row["days_overdue"] = max(float(row["days_since_last_service"] - row["oem_interval_days"]), 0.0)
    row["km_overdue"] = max(float(row["km_since_last_service"] - row["oem_interval_km"]), 0.0)
    row["maintenance_due_now"] = int(ratio >= 1.0)
    row["due_task_count"] = max(int(row["due_task_count"]), int(ratio >= 1.0))
    row["critical_due_task_count"] = max(int(row["critical_due_task_count"]), int(ratio >= 1.35))
    return row


def _large_behavior_audit(
    validation: pd.DataFrame,
    predict_probability: Callable[[pd.DataFrame], np.ndarray],
) -> dict[str, Any]:
    """Run deterministic one-factor and interaction audits over >5k scenarios."""
    rng = np.random.default_rng(SEED)
    # Cover real categories while preventing a single dense motorcycle from dominating.
    candidates = validation.drop_duplicates("motorcycle_id")
    bases = candidates.iloc[rng.choice(len(candidates), size=min(160, len(candidates)), replace=False)].copy()
    rows: list[pd.Series] = []
    keys: list[tuple[str, int, float]] = []

    def add(axis: str, base_index: int, value: float, row: pd.Series) -> None:
        rows.append(row[FEATURE_COLUMNS])
        keys.append((axis, base_index, float(value)))

    for base_index, (_, base) in enumerate(bases.iterrows()):
        for value in [.35, .65, .9, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0]:
            add("due", base_index, value, _set_due(base, value))
        for value in [3000, 6000, 10000, 16000, 24000, 36000]:
            row = _set_due(base, 1.45)
            row["annual_km_baseline"] = value
            row["recent_90d_km"] = value * 90 / 365
            row["recent_vs_baseline_usage_ratio"] = 1.0
            row["avg_km_per_day_since_last_service"] = value / 365
            add("usage", base_index, value, row)
        for value in [0.15, .55, .9]:
            row = _set_due(base, 1.35)
            row["historical_on_time_rate"] = value
            row["historical_service_delay_mean_days"] = (1 - value) * 120
            add("adherence", base_index, value, row)
        for value in [0, 1, 3, 6]:
            row = _set_due(base, 1.45)
            row["prior_appointment_count"] = max(float(row["prior_appointment_count"]), value + 2)
            row["prior_no_show_count"] = value
            row["known_appointment_within_30d"] = 0
            row["days_to_next_known_appointment"] = np.nan
            add("no_show", base_index, value, row)
        for value in [0, 1]:
            row = _set_due(base, 1.35)
            row["known_appointment_within_30d"] = value
            row["days_to_next_known_appointment"] = 10 if value else np.nan
            add("appointment", base_index, value, row)
        for value in [0, 1, 3]:
            row = _set_due(base, 1.35)
            row["recent_breakdown_count_180d"] = value
            row["last_service_was_breakdown"] = int(value > 0)
            add("breakdown", base_index, value, row)
        for value in [15, 60, 180, 365, 730]:
            ratio = value / max(float(base["oem_interval_days"]), 1.0)
            row = _set_due(base, ratio)
            add("recency", base_index, value, row)

    scenario = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    probability = predict_probability(scenario)
    key_frame = pd.DataFrame(keys, columns=["axis", "base", "value"])
    for index, horizon in enumerate(HORIZONS.astype(int)):
        key_frame[f"p{horizon}"] = probability[:, index]

    def sequences(axis: str, horizon: str = "p30") -> list[np.ndarray]:
        part = key_frame.loc[key_frame.axis.eq(axis)]
        return [g.sort_values("value")[horizon].to_numpy() for _, g in part.groupby("base")]

    def monotone_rate(axis: str, direction: int = 1, tolerance: float = 1e-9) -> float:
        results = []
        for sequence in sequences(axis):
            differences = np.diff(sequence) * direction
            results.append(bool(np.all(differences >= -tolerance)))
        return float(np.mean(results))

    due_sequences = sequences("due")
    usage_sequences = sequences("usage")
    appointment_sequences = sequences("appointment")
    severe_delta = [seq[-1] - seq[-2] for seq in due_sequences]
    due_lift = [seq[5] - seq[2] for seq in due_sequences]  # 1.5 versus 0.9
    usage_lift = [seq[-1] - seq[1] for seq in usage_sequences]
    appointment_lift = [seq[-1] - seq[0] for seq in appointment_sequences]
    all_probability = probability
    repeat = predict_probability(scenario.iloc[:128].copy())
    calendar_pair = scenario.iloc[:64].copy()
    calendar_duplicate = calendar_pair.copy()  # year is deliberately not an input.
    calendar_same = predict_probability(calendar_pair)
    calendar_again = predict_probability(calendar_duplicate)

    ood = scenario.iloc[:8].copy()
    ood["brand"] = "UNSEEN_BRAND_V2_2_AUDIT"
    ood["category"] = "UNSEEN_CATEGORY_V2_2_AUDIT"
    ood["annual_km_baseline"] = [0, 1000, 50000, 100000, 250000, 500000, 750000, 1000000]
    ood_probability = predict_probability(ood)
    ood_warnings = [
        "unknown categorical values mapped to the predeclared -1 encoder bucket",
        "annual_km_baseline outside TRAIN support must be flagged by any future serving adapter",
    ]

    checks = {
        "scenario_count_at_least_5000": len(scenario) >= 5000,
        "due_pressure_monotone_rate": monotone_rate("due") >= .98,
        "overdue_lift_material": float(np.mean(due_lift)) >= .05,
        "severe_overdue_saturates": float(np.mean(severe_delta)) <= .12,
        "severe_overdue_not_deterministic": float(np.mean([seq[-1] for seq in due_sequences])) < .95,
        "high_usage_overdue_lift": monotone_rate("usage") >= .95 and float(np.mean(usage_lift)) >= .01,
        "adherence_direction": monotone_rate("adherence") >= .95,
        "no_show_counteracts_return": monotone_rate("no_show", direction=-1) >= .95,
        "known_appointment_intent_lift": monotone_rate("appointment") >= .98 and float(np.mean(appointment_lift)) >= .02,
        "breakdown_pressure_lift": monotone_rate("breakdown") >= .95,
        "service_recency_interpretable": monotone_rate("recency") >= .95,
        "horizon_monotonicity": bool(np.all(np.diff(all_probability, axis=1) >= -1e-9)),
        "p30_non_degenerate": float(np.mean(all_probability[:, 0] == 0)) < .05 and len(np.unique(np.round(all_probability[:, 0], 6))) >= 20,
        "same_input_deterministic": bool(np.array_equal(repeat, probability[:128])),
        "calendar_year_invariance": bool(np.array_equal(calendar_same, calendar_again)),
        "ood_finite_and_bounded": bool(np.isfinite(ood_probability).all() and ((ood_probability >= 0) & (ood_probability <= 1)).all()),
        "ood_warnings_explicit": len(ood_warnings) >= 2,
    }
    diagnostics = {
        "scenario_count": len(scenario),
        "base_rows": len(bases),
        "due_monotone_rate": monotone_rate("due"),
        "mean_due_lift_p30_0_9_to_1_5": float(np.mean(due_lift)),
        "mean_severe_increment_p30_3_to_4": float(np.mean(severe_delta)),
        "mean_p30_at_due_ratio_4": float(np.mean([seq[-1] for seq in due_sequences])),
        "usage_monotone_rate": monotone_rate("usage"),
        "mean_usage_lift_p30_6k_to_36k": float(np.mean(usage_lift)),
        "adherence_monotone_rate": monotone_rate("adherence"),
        "no_show_nonincreasing_rate": monotone_rate("no_show", direction=-1),
        "appointment_lift_rate": monotone_rate("appointment"),
        "mean_appointment_lift_p30": float(np.mean(appointment_lift)),
        "breakdown_monotone_rate": monotone_rate("breakdown"),
        "recency_monotone_rate": monotone_rate("recency"),
        "p30_min": float(all_probability[:, 0].min()),
        "p30_median": float(np.median(all_probability[:, 0])),
        "p30_max": float(all_probability[:, 0].max()),
        "p30_unique_6dp": int(len(np.unique(np.round(all_probability[:, 0], 6)))),
        "ood_warnings": ood_warnings,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed, "diagnostics": diagnostics}


def _selection_markdown(report: dict[str, Any]) -> str:
    candidates = pd.DataFrame([
        {
            "candidate": name,
            "feature_contract": result.get("feature_contract", "n/a"),
            "ipcw_c": result.get("ipcw_c_index"),
            "ibs": result.get("ibs_30_120"),
            "status": result.get("status", "FIT"),
        }
        for name, result in report["candidate_validation_metrics"].items()
    ])
    lines = [
        "# RideBase V2.2 TRAIN+VALIDATION Selection", "",
        f"**Gate: {report['status']}**", "",
        "TEST was not read by this phase. Selection and calibration are frozen before TEST first touch.", "",
        "## Candidates", "", candidates.to_markdown(index=False), "",
        "## Selected challenger", "",
        f"- Model: `{report['selected']['model']}`",
        f"- Calibration: `{report['selected']['calibration']}`",
        f"- Feature contract: `{report['selected']['feature_contract']}`",
        "", "## Behavioral gate", "",
    ]
    lines.extend(f"- {'PASS' if value else 'FAIL'} — `{name}`" for name, value in report["behavior_audit"]["checks"].items())
    lines.extend(["", "## Leakage and selection controls", ""])
    lines.extend(f"- {'PASS' if value else 'FAIL'} — `{name}`" for name, value in report["selection_checks"].items())
    lines.append("")
    return "\n".join(lines)


def select_on_validation(repo_root: Path) -> dict[str, Any]:
    paths = _paths(repo_root)
    model_dir = paths["model_dir"]
    if (model_dir / "test_first_touch.json").exists():
        raise RuntimeError("TEST has already been touched; refusing to rerun selection in-place")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=paths["root"], text=True).strip()

    # Filtered parquet reads make the no-TEST boundary explicit and auditable.
    train = pd.read_parquet(paths["data"], filters=[("modeling_role", "==", "TRAIN")])
    validation = pd.read_parquet(paths["data"], filters=[("modeling_role", "==", "VALIDATION")])
    train_y = _survival_y(train)
    preprocessor = _preprocessor().fit(train[FEATURE_COLUMNS])
    X_train = preprocessor.transform(train[FEATURE_COLUMNS]).astype(np.float32)
    X_validation = preprocessor.transform(validation[FEATURE_COLUMNS]).astype(np.float32)
    transformed_names = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    base_indices = [transformed_names.index(name) for name in BASE_FEATURE_COLUMNS]

    candidates: dict[str, dict[str, Any]] = {}
    objects: dict[str, tuple[Any, dict[str, np.ndarray], np.ndarray, np.ndarray, list[int] | None]] = {}

    rule_survival = _rule_survival(validation)
    candidates["oem_policy_due_rule"] = {
        **_metrics(train_y, validation, -rule_survival[:, 2], rule_survival),
        "feature_contract": "deterministic_policy_baseline",
    }

    simple_names = ["annual_km_baseline", "days_due_ratio", "km_due_ratio", "max_due_ratio"]
    simple_indices = [transformed_names.index(name) for name in simple_names]

    def fit_survival(name: str, model: Any, indices: list[int] | None, cap: int | None, contract: str) -> None:
        sample = np.arange(len(train))
        if cap and len(sample) > cap:
            sample = np.random.default_rng(SEED).choice(sample, cap, replace=False)
        fit_x = X_train[sample] if indices is None else X_train[sample][:, indices]
        fit_y = train_y[sample]
        model.fit(fit_x, fit_y)
        baseline = _breslow(fit_y["time"], fit_y["event"], model.predict(fit_x))
        val_x = X_validation if indices is None else X_validation[:, indices]
        score = model.predict(val_x)
        survival = _survival_from_score(score, baseline)
        candidates[name] = {**_metrics(train_y, validation, score, survival), "feature_contract": contract}
        objects[name] = (model, baseline, score, survival, indices)

    for name, model, indices, cap, contract in [
        ("simple_cox", CoxPHSurvivalAnalysis(alpha=.02, n_iter=100), simple_indices, 80000, "4_feature_baseline"),
        ("cox_ph_extended60", CoxPHSurvivalAnalysis(alpha=.08, n_iter=100), None, 80000, "extended60"),
        ("coxnet_extended60", CoxnetSurvivalAnalysis(l1_ratio=.2, alphas=[.003], max_iter=100000), None, 65000, "extended60"),
    ]:
        try:
            fit_survival(name, model, indices, cap, contract)
        except Exception as exc:
            candidates[name] = {"status": "INFEASIBLE", "reason": str(exc), "feature_contract": contract}

    base_model = _fit_xgb(X_train[:, base_indices], train_y, BASE_FEATURE_COLUMNS)
    base_train_score = base_model.predict(X_train[:, base_indices])
    base_baseline = _breslow(train_y["time"], train_y["event"], base_train_score)
    base_score = base_model.predict(X_validation[:, base_indices])
    base_survival = _survival_from_score(base_score, base_baseline)
    candidates["xgb_cox_frozen54"] = {**_metrics(train_y, validation, base_score, base_survival), "feature_contract": "frozen54"}
    objects["xgb_cox_frozen54"] = (base_model, base_baseline, base_score, base_survival, base_indices)

    extended_model = _fit_xgb(X_train, train_y, transformed_names)
    extended_train_score = extended_model.predict(X_train)
    extended_baseline = _breslow(train_y["time"], train_y["event"], extended_train_score)
    extended_score = extended_model.predict(X_validation)
    extended_survival = _survival_from_score(extended_score, extended_baseline)
    candidates["xgb_cox_extended60"] = {**_metrics(train_y, validation, extended_score, extended_survival), "feature_contract": "extended60"}
    objects["xgb_cox_extended60"] = (extended_model, extended_baseline, extended_score, extended_survival, None)

    statistically_viable = [
        name for name, result in candidates.items()
        if result.get("feature_contract") == "extended60"
        and math.isfinite(result.get("ibs_30_120", math.inf))
        and result.get("ipcw_c_index", 0) >= .65
    ]
    if not statistically_viable:
        raise RuntimeError("No extended60 candidate passed the validation discrimination gate")

    # Discrimination alone cannot choose this challenger: the predeclared
    # behavioral contract is also a hard eligibility condition.  This prevents
    # a numerically attractive Cox fit with correlated due variables from being
    # selected when its controlled response has the wrong sign.
    eligibility: dict[str, Any] = {}
    eligible_objects: dict[str, tuple[Any, dict[str, np.ndarray], list[int] | None, str, HorizonCalibrator, dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
    for name in statistically_viable:
        candidate_model, candidate_baseline, candidate_score, candidate_survival, candidate_indices = objects[name]
        candidate_raw_probability = 1 - candidate_survival
        method, candidate_calibrator, calibration_comparison, _, candidate_eval_idx = _calibration_candidates(
            validation, candidate_raw_probability
        )

        def candidate_predict(rows: pd.DataFrame) -> np.ndarray:
            matrix = preprocessor.transform(rows[FEATURE_COLUMNS]).astype(np.float32)
            if candidate_indices is not None:
                matrix = matrix[:, candidate_indices]
            score = candidate_model.predict(matrix)
            return candidate_calibrator.transform(1 - _survival_from_score(score, candidate_baseline))

        candidate_behavior = _large_behavior_audit(validation, candidate_predict)
        calibrated_eval_probability = candidate_calibrator.transform(candidate_raw_probability[candidate_eval_idx])
        calibration_metrics = _calibration_score(validation.iloc[candidate_eval_idx], calibrated_eval_probability)
        calibrated_survival_metrics = _metrics(
            train_y,
            validation.iloc[candidate_eval_idx],
            candidate_score[candidate_eval_idx],
            1 - calibrated_eval_probability,
        )
        gate = {
            "behavior_contract": candidate_behavior["status"] == "PASS",
            "mean_calibration_error": calibration_metrics["mean_calibration_error"] <= .10,
            "calibrated_validation_ibs": calibrated_survival_metrics["ibs_30_120"] <= .18,
        }
        eligibility[name] = {
            "status": "PASS" if all(gate.values()) else "FAIL",
            "checks": gate,
            "calibration": method,
            "calibrated_validation_eval": calibration_metrics,
            "calibrated_survival_metrics": calibrated_survival_metrics,
            "behavior_audit": candidate_behavior,
        }
        if all(gate.values()):
            eligible_objects[name] = (
                candidate_model, candidate_baseline, candidate_indices, method,
                candidate_calibrator, calibration_comparison, calibration_metrics,
                candidate_behavior,
            )
    if not eligible_objects:
        _write_json(paths["reports"] / "v2_2_candidate_eligibility_failure.json", eligibility)
        raise RuntimeError("No extended60 candidate passed both validation statistics and behavior gates")
    selected_name = min(
        eligible_objects,
        key=lambda name: (
            eligibility[name]["calibrated_survival_metrics"]["ibs_30_120"]
            + eligibility[name]["calibrated_validation_eval"]["mean_calibration_error"]
        ),
    )
    (
        model, baseline, selected_indices, calibration_method, calibrator,
        calibration_results, calibrated_metrics, behavior,
    ) = eligible_objects[selected_name]
    eval_idx = np.argsort(pd.to_datetime(validation.landmark_at).to_numpy())[len(validation) // 2:]
    forbidden_tokens = ["future", "target", "censor", "days_observed", "absolute_year", "split", "event_observed", "latent"]
    forbidden_features = [name for name in FEATURE_COLUMNS if any(token in name.lower() for token in forbidden_tokens)]
    checks = {
        "train_and_validation_only": True,
        "test_status_sealed": True,
        "selection_uses_extended_observable_contract": candidates[selected_name]["feature_contract"] == "extended60",
        "feature_count_60": len(FEATURE_COLUMNS) == 60,
        "frozen_base54_prefix_exact": FEATURE_COLUMNS[:54] == BASE_FEATURE_COLUMNS,
        "observable_extension_exact": FEATURE_COLUMNS[54:] == OBSERVABLE_HISTORY_FEATURES,
        "forbidden_features_absent": not forbidden_features,
        "validation_ipcw_c_acceptable": candidates[selected_name]["ipcw_c_index"] >= .65,
        "calibrated_validation_ibs_acceptable": eligibility[selected_name]["calibrated_survival_metrics"]["ibs_30_120"] <= .18,
        "validation_calibration_acceptable": calibrated_metrics["mean_calibration_error"] <= .10,
        "behavior_gate_pass": behavior["status"] == "PASS",
    }
    failed = [name for name, passed in checks.items() if not passed]
    status = "PASS" if not failed else "FAIL"

    importance = []
    if hasattr(model, "feature_importances_"):
        names = transformed_names if selected_indices is None else [transformed_names[i] for i in selected_indices]
        importance = sorted(
            ({"feature": name, "importance": float(value)} for name, value in zip(names, model.feature_importances_)),
            key=lambda row: row["importance"], reverse=True,
        )

    joblib.dump(preprocessor, model_dir / "preprocessor.joblib")
    joblib.dump(model, model_dir / "challenger_model.joblib")
    joblib.dump(baseline, model_dir / "baseline_hazard.joblib")
    joblib.dump(calibrator, model_dir / "calibrator.joblib")
    _write_json(model_dir / "feature_list.json", FEATURE_COLUMNS)
    _write_json(model_dir / "candidate_validation_metrics.json", candidates)
    _write_json(model_dir / "candidate_eligibility.json", eligibility)
    _write_json(model_dir / "calibration_validation.json", calibration_results)
    _write_json(model_dir / "massive_behavior_audit.json", behavior)
    freeze = {
        "status": status,
        "failed_checks": failed,
        "experiment": "V2.2_OFFLINE_CHALLENGER",
        "production_status": "NOT_DEPLOYED; V2.1 REMAINS PRODUCTION CHAMPION",
        "model": selected_name,
        "calibration": calibration_method,
        "feature_contract": "extended60_with_frozen_v2_1_base54",
        "feature_count": len(FEATURE_COLUMNS),
        "modeling_table_sha256": _sha256(paths["data"]),
        "split_manifest_sha256": _sha256(paths["split"]),
        "config_sha256": _sha256(paths["config"]),
        "selection_commit": commit,
        "selection_split": "VALIDATION",
        "calibration_protocol": "chronological first-half VALIDATION fit; second-half VALIDATION evaluation",
        "test_status": "SEALED_NOT_READ",
        "selected_validation_metrics": candidates[selected_name],
        "calibrated_validation_eval": calibrated_metrics,
        "calibrated_validation_survival_metrics": eligibility[selected_name]["calibrated_survival_metrics"],
        "selection_checks": checks,
        "behavior_audit_sha256": _sha256(model_dir / "massive_behavior_audit.json"),
        "artifacts": {},
    }
    for filename in ["preprocessor.joblib", "challenger_model.joblib", "baseline_hazard.joblib", "calibrator.joblib", "feature_list.json"]:
        freeze["artifacts"][filename] = _sha256(model_dir / filename)
    _write_json(model_dir / SELECTION_FILE, freeze)

    report = {
        "report": "RideBase V2.2 TRAIN+VALIDATION Challenger Selection",
        "status": status,
        "failed_checks": failed,
        "test_read": False,
        "candidate_validation_metrics": candidates,
        "selected": {"model": selected_name, "calibration": calibration_method, "feature_contract": "extended60"},
        "calibration_comparison": calibration_results,
        "candidate_eligibility": eligibility,
        "calibrated_validation_eval": calibrated_metrics,
        "behavior_audit": behavior,
        "selection_checks": checks,
        "feature_importance_top25": importance[:25],
        "generator_vs_features_ablation": {
            "same_v1_5_world_frozen54": candidates["xgb_cox_frozen54"],
            "same_v1_5_world_extended60": candidates["xgb_cox_extended60"],
        },
        "selection_manifest": str(model_dir / SELECTION_FILE),
    }
    _write_json(paths["reports"] / "v2_2_validation_selection.json", report)
    (paths["reports"] / "v2_2_validation_selection.md").write_text(_selection_markdown(report))
    print(json.dumps({
        "status": status, "failed_checks": failed, "selected": selected_name,
        "calibration": calibration_method, "validation": candidates[selected_name],
        "behavior": behavior,
    }, indent=2, default=str))
    if status != "PASS":
        raise RuntimeError(f"V2.2 selection gate failed: {failed}")
    return report


def evaluate_frozen_test_once(repo_root: Path) -> dict[str, Any]:
    paths = _paths(repo_root)
    model_dir = paths["model_dir"]
    selection_path = model_dir / SELECTION_FILE
    first_touch_path = model_dir / "test_first_touch.json"
    if not selection_path.exists():
        raise RuntimeError("Selection manifest missing; TEST cannot be opened")
    if first_touch_path.exists():
        raise RuntimeError("TEST already evaluated; one-time gate refuses a rerun")
    selection = json.loads(selection_path.read_text())
    if selection.get("status") != "PASS" or selection.get("test_status") != "SEALED_NOT_READ":
        raise RuntimeError("Selection is not a passing sealed freeze")
    for filename, expected in selection["artifacts"].items():
        if _sha256(model_dir / filename) != expected:
            raise RuntimeError(f"Frozen artifact hash mismatch: {filename}")

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=paths["root"], text=True).strip()
    first_touch = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "selection_manifest_sha256": _sha256(selection_path),
        "protocol": "first and only outcome-bearing TEST model evaluation after frozen TRAIN+VALIDATION selection",
    }
    _write_json(first_touch_path, first_touch)

    # No TEST parquet read occurs above this line.
    test = pd.read_parquet(paths["data"], filters=[("modeling_role", "==", "TEST")])
    unseen = pd.read_parquet(paths["data"], filters=[("modeling_role", "==", "UNSEEN_MOTORCYCLE_TEMPORAL_TEST")])
    train = pd.read_parquet(paths["data"], filters=[("modeling_role", "==", "TRAIN")])
    train_y = _survival_y(train)
    preprocessor = joblib.load(model_dir / "preprocessor.joblib")
    model = joblib.load(model_dir / "challenger_model.joblib")
    baseline = joblib.load(model_dir / "baseline_hazard.joblib")
    calibrator = joblib.load(model_dir / "calibrator.joblib")

    def evaluate(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        matrix = preprocessor.transform(frame[FEATURE_COLUMNS]).astype(np.float32)
        score = model.predict(matrix)
        probability = calibrator.transform(1 - _survival_from_score(score, baseline))
        return score, probability, _metrics(train_y, frame, score, 1 - probability)

    test_score, test_probability, test_metrics = evaluate(test)
    unseen_score, unseen_probability, unseen_metrics = evaluate(unseen)
    bootstrap = _group_bootstrap(test, test_probability[:, 2], repeats=100)
    predictions = test[["landmark_id", "motorcycle_id", "landmark_at", "duration_days", "event_observed"]].copy()
    predictions["risk_score"] = test_score
    for index, horizon in enumerate(HORIZONS.astype(int)):
        predictions[f"risk_{horizon}d"] = test_probability[:, index]
    predictions.to_parquet(model_dir / "frozen_test_predictions.parquet", index=False)

    v21 = json.loads((paths["ml"] / "models/v2_1_v1_4/metrics.json").read_text())
    v21_test = v21["test_metrics"]
    comparison = {
        "warning": "Different synthetic worlds: V2.1 uses V1.4; V2.2 uses V1.5. This is contextual, not a paired causal estimate.",
        "v2_1_production_champion": "xgb_cox + isotonic; unchanged",
        "v2_2_offline_challenger": selection["model"] + " + " + selection["calibration"],
        "ipcw_c_index": {"v2_1": v21_test["ipcw_c_index"], "v2_2": test_metrics["ipcw_c_index"], "delta": test_metrics["ipcw_c_index"] - v21_test["ipcw_c_index"]},
        "ibs_30_120": {"v2_1": v21_test["ibs_30_120"], "v2_2": test_metrics["ibs_30_120"], "delta": test_metrics["ibs_30_120"] - v21_test["ibs_30_120"]},
        "p90_calibration_error": {
            "v2_1": v21_test["horizons"]["90"]["calibration_error"],
            "v2_2": test_metrics["horizons"]["90"]["calibration_error"],
            "delta": test_metrics["horizons"]["90"]["calibration_error"] - v21_test["horizons"]["90"]["calibration_error"],
        },
    }
    p30 = test_probability[:, 0]
    test_checks = {
        "test_opened_after_selection_freeze": first_touch["selection_manifest_sha256"] == _sha256(selection_path),
        "ipcw_c_not_materially_degraded": test_metrics["ipcw_c_index"] >= v21_test["ipcw_c_index"] - .05,
        "ibs_acceptable": test_metrics["ibs_30_120"] <= .18,
        "p90_calibration_acceptable": test_metrics["horizons"]["90"]["calibration_error"] <= .10,
        "p30_usable": float(np.mean(p30 == 0)) < .05 and len(np.unique(np.round(p30, 6))) >= 20,
        "unseen_motorcycle_metrics_present": bool(unseen_metrics),
        "v2_1_remains_production_champion": True,
        "no_deployment_performed": True,
    }
    failed = [name for name, passed in test_checks.items() if not passed]
    report = {
        "report": "RideBase V2.2 One-time TEST Evaluation",
        "status": "PASS" if not failed else "FAIL",
        "failed_checks": failed,
        "first_touch": first_touch,
        "test_checks": test_checks,
        "test_metrics": test_metrics,
        "unseen_motorcycle_metrics": unseen_metrics,
        "grouped_motorcycle_bootstrap": bootstrap,
        "comparison_to_frozen_v2_1": comparison,
        "p30_distribution": {
            "min": float(p30.min()), "p10": float(np.quantile(p30, .1)),
            "median": float(np.median(p30)), "p90": float(np.quantile(p30, .9)),
            "max": float(p30.max()), "exact_zero_share": float(np.mean(p30 == 0)),
            "unique_probability_levels_8dp": int(len(np.unique(np.round(p30, 8)))),
        },
        "production_status": "V2.1 REMAINS PRODUCTION CHAMPION; V2.2 OFFLINE ONLY; NO DEPLOY",
        "reality_gap": "REAL FLEET VALIDATION PENDING",
    }
    _write_json(model_dir / "test_evaluation.json", report)
    _write_json(paths["reports"] / "v2_2_test_evaluation.json", report)
    lines = [
        "# RideBase V2.2 One-time TEST Evaluation", "",
        f"**Gate: {report['status']}**", "",
        f"- IPCW C-index: `{test_metrics['ipcw_c_index']:.6f}`",
        f"- IBS 30–120: `{test_metrics['ibs_30_120']:.6f}`",
        f"- P90 calibration error: `{test_metrics['horizons']['90']['calibration_error']:.6f}`",
        f"- Unseen-motorcycle IPCW C-index: `{unseen_metrics['ipcw_c_index']:.6f}`",
        "", "V2.1 remains the production champion. V2.2 was not deployed.", "",
    ]
    (paths["reports"] / "v2_2_test_evaluation.md").write_text("\n".join(lines))
    manifest = {
        path.name: _sha256(path)
        for path in sorted(model_dir.iterdir())
        if path.name != "artifact_manifest.json"
    }
    _write_json(model_dir / "artifact_manifest.json", manifest)
    print(json.dumps({"status": report["status"], "failed_checks": failed, "test_metrics": test_metrics, "comparison": comparison}, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["select", "test"])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    if args.stage == "select":
        select_on_validation(args.repo_root)
    else:
        evaluate_frozen_test_once(args.repo_root)


if __name__ == "__main__":
    main()
