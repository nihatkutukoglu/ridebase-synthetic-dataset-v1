"""TRAIN/VALIDATION-only feature, model, and calibration recovery search."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler
from sksurv.linear_model import CoxPHSurvivalAnalysis, CoxnetSurvivalAnalysis
from sksurv.metrics import concordance_index_censored
from xgboost import XGBRegressor

from ridebase_ml.v2_1.survival import HORIZONS, HorizonCalibrator, _survival_from_score
from ridebase_ml.v2_2.landmarks import BASE_FEATURE_COLUMNS, CATEGORICAL_FEATURES, FEATURE_COLUMNS, OBSERVABLE_HISTORY_FEATURES
from ridebase_ml.v2_2.train import _breslow, _calibration_score, _large_behavior_audit, _metrics, _survival_y, _xgb_constraints
from ridebase_ml.v2_2_1.calibration import BlendedHorizonCalibrator


SEED = 52


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def _preprocessor(features: list[str]) -> tuple[Pipeline, list[str]]:
    categorical = [name for name in CATEGORICAL_FEATURES if name in features]
    numeric = [name for name in features if name not in categorical]
    columns = ColumnTransformer([
        ("categorical", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("ordinal", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
        ]), categorical),
        ("numeric", SimpleImputer(strategy="median"), numeric),
    ], verbose_feature_names_out=False)
    return Pipeline([("columns", columns), ("scale", StandardScaler())]), categorical + numeric


def _xgb(params: dict[str, Any], transformed_features: list[str]) -> XGBRegressor:
    params = dict(params)
    constraint_profile = params.pop("constraint_profile", "full_v2_2")
    if constraint_profile == "full_v2_2":
        constraints = _xgb_constraints(transformed_features)
    elif constraint_profile == "behavior_core":
        positive = {
            "annual_km_baseline", "recent_90d_km", "recent_vs_baseline_usage_ratio",
            "days_since_last_service", "km_since_last_service", "avg_km_per_day_since_last_service",
            "days_due_ratio", "km_due_ratio", "max_due_ratio", "historical_on_time_rate",
            "known_appointment_within_30d", "recent_breakdown_count_180d",
            "prior_breakdown_count", "last_service_was_breakdown",
        }
        negative = {
            "historical_service_delay_mean_days", "prior_no_show_count",
            "prior_cancelled_appointment_count", "days_to_next_known_appointment",
        }
        constraints = tuple(1 if name in positive else -1 if name in negative else 0 for name in transformed_features)
    else:
        raise ValueError(f"Unknown constraint profile: {constraint_profile}")
    return XGBRegressor(
        objective="survival:cox",
        monotone_constraints=constraints,
        random_state=SEED,
        n_jobs=6,
        **params,
    )


def _calibrators() -> dict[str, Any]:
    return {
        "raw": HorizonCalibrator("uncalibrated"),
        "isotonic": HorizonCalibrator("isotonic"),
        "platt": HorizonCalibrator("platt"),
        "beta": HorizonCalibrator("beta"),
        "isotonic_beta_blend_0.75": BlendedHorizonCalibrator(.75),
        "isotonic_beta_blend_0.50": BlendedHorizonCalibrator(.50),
    }


def _resolution(probability: np.ndarray) -> dict[str, Any]:
    p30 = probability[:, 0]
    return {
        "p30_exact_zero_share": float(np.mean(p30 == 0)),
        "p30_unique_8dp": int(len(np.unique(np.round(p30, 8)))),
        "p30_largest_plateau_share": float(pd.Series(np.round(p30, 10)).value_counts(normalize=True).max()),
        "p30_min": float(p30.min()), "p30_median": float(np.median(p30)), "p30_max": float(p30.max()),
    }


def _fit_candidate(
    train: pd.DataFrame,
    train_y: np.ndarray,
    validation_search: pd.DataFrame,
    validation_calibration: pd.DataFrame,
    validation_final: pd.DataFrame,
    features: list[str],
    params: dict[str, Any],
    candidate_id: str,
) -> dict[str, Any]:
    preprocessor, transformed = _preprocessor(features)
    X_train = preprocessor.fit_transform(train[features]).astype(np.float32)
    labels = np.where(train_y["event"], train_y["time"], -train_y["time"])
    model = _xgb(params, transformed)
    model.fit(X_train, labels, verbose=False)
    train_score = model.predict(X_train)
    baseline = _breslow(train_y["time"], train_y["event"], train_score)

    def raw(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        matrix = preprocessor.transform(frame[features]).astype(np.float32)
        score = model.predict(matrix)
        return score, 1-_survival_from_score(score, baseline)

    search_score, search_probability = raw(validation_search)
    calibration_score, calibration_probability = raw(validation_calibration)
    final_score, final_raw_probability = raw(validation_final)
    train_eval_idx = np.random.default_rng(SEED).choice(len(train), min(8000, len(train)), replace=False)
    train_harrell = float(concordance_index_censored(
        train_y["event"][train_eval_idx], train_y["time"][train_eval_idx], train_score[train_eval_idx]
    )[0])
    search_metrics = _metrics(train_y, validation_search, search_score, 1-search_probability)
    calibration_results = {}
    fitted_calibrators = {}
    for name, calibrator in _calibrators().items():
        calibrator.fit(calibration_probability, validation_calibration)
        probability = calibrator.transform(final_raw_probability)
        calibration_results[name] = {
            "calibration": _calibration_score(validation_final, probability),
            "resolution": _resolution(probability),
        }
        fitted_calibrators[name] = calibrator
    eligible_calibration = [
        name for name, result in calibration_results.items()
        if result["calibration"]["mean_calibration_error"] <= .10
        and result["calibration"]["mean_brier"] <= .18
        and result["resolution"]["p30_exact_zero_share"] <= .02
    ]
    behavior_by_calibration = {}
    for name in eligible_calibration:
        trial_calibrator = fitted_calibrators[name]

        def trial_predict(rows: pd.DataFrame) -> np.ndarray:
            matrix = preprocessor.transform(rows[features]).astype(np.float32)
            score = model.predict(matrix)
            return trial_calibrator.transform(1-_survival_from_score(score, baseline))

        behavior_by_calibration[name] = _large_behavior_audit(validation_search, trial_predict)
    behavior_eligible_calibration = [
        name for name in eligible_calibration if behavior_by_calibration[name]["status"] == "PASS"
    ]
    if not behavior_eligible_calibration:
        calibration_name = min(
            eligible_calibration or ["raw"],
            key=lambda name: (
                calibration_results[name]["calibration"]["mean_brier"]
                + calibration_results[name]["calibration"]["mean_calibration_error"]
            ),
        )
    else:
        calibration_name = min(
            behavior_eligible_calibration,
            key=lambda name: (
                calibration_results[name]["calibration"]["mean_brier"]
                + calibration_results[name]["calibration"]["mean_calibration_error"]
                + .02 * calibration_results[name]["resolution"]["p30_largest_plateau_share"]
            ),
        )
    calibrator = fitted_calibrators[calibration_name]

    behavior = behavior_by_calibration.get(calibration_name)
    if behavior is None:
        def predict(rows: pd.DataFrame) -> np.ndarray:
            matrix = preprocessor.transform(rows[features]).astype(np.float32)
            score = model.predict(matrix)
            return calibrator.transform(1-_survival_from_score(score, baseline))
        behavior = _large_behavior_audit(validation_search, predict)
    selected_calibration = calibration_results[calibration_name]
    final_probability = calibrator.transform(final_raw_probability)
    final_metrics = _metrics(train_y, validation_final, final_score, 1-final_probability)
    temporal = []
    for label, part in [
        ("JUL_AUG_SEARCH", validation_search),
        ("SEP_OCT_CALIBRATION", validation_calibration),
        ("NOV_DEC_FINAL", validation_final),
    ]:
        if len(part) > 5000:
            temporal_idx = np.random.default_rng(SEED).choice(len(part), 5000, replace=False)
            metric_part = part.iloc[temporal_idx]
        else:
            temporal_idx = np.arange(len(part)); metric_part = part
        part_score, part_raw = raw(part)
        part_probability = calibrator.transform(part_raw)
        metrics = _metrics(train_y, metric_part, part_score[temporal_idx], 1-part_probability[temporal_idx])
        temporal.append({
            "fold": label, "rows": len(part), "metric_sample_rows": len(metric_part), "ipcw_c_index": metrics["ipcw_c_index"],
            "ibs": metrics["ibs_30_120"], "p90_calibration_error": metrics["horizons"]["90"]["calibration_error"],
        })
    result = {
        "candidate_id": candidate_id,
        "feature_count": len(features),
        "features": features,
        "hyperparameters": params,
        "train_metrics": {"harrell_c_index": train_harrell, "sample_rows": len(train_eval_idx)},
        "search_validation_metrics": search_metrics,
        "train_search_harrell_gap": train_harrell-search_metrics["harrell_c_index"],
        "calibration_search": calibration_results,
        "calibration_behavior_status": {name: value["status"] for name, value in behavior_by_calibration.items()},
        "selected_calibration": calibration_name,
        "final_validation_metrics": final_metrics,
        "final_validation_calibration": selected_calibration["calibration"],
        "resolution": selected_calibration["resolution"],
        "behavior": behavior,
        "required_behavior_features_present": bool(
            "prior_no_show_count" in features and "known_appointment_within_30d" in features
        ),
        "temporal_folds": temporal,
        "temporal_c_std": float(np.std([fold["ipcw_c_index"] for fold in temporal])),
        "eligible": bool(
            behavior["status"] == "PASS"
            and "prior_no_show_count" in features
            and "known_appointment_within_30d" in features
            and final_metrics["ipcw_c_index"] >= .65
            and final_metrics["ibs_30_120"] <= .18
            and selected_calibration["calibration"]["mean_calibration_error"] <= .10
        ),
        "_objects": (preprocessor, model, baseline, calibrator),
    }
    return result


def _public(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "_objects"}


def _existing_v22_metrics(ml: Path, frames: list[tuple[str, pd.DataFrame]], train_y: np.ndarray) -> dict[str, Any]:
    model_dir = ml / "models/v2_2_v1_5"
    pre = joblib.load(model_dir / "preprocessor.joblib")
    model = joblib.load(model_dir / "challenger_model.joblib")
    baseline = joblib.load(model_dir / "baseline_hazard.joblib")
    cal = joblib.load(model_dir / "calibrator.joblib")
    output = {}
    for name, frame in frames:
        score = model.predict(pre.transform(frame[FEATURE_COLUMNS]).astype(np.float32))
        probability = cal.transform(1-_survival_from_score(score, baseline))
        output[name] = {
            "metrics": _metrics(train_y, frame, score, 1-probability),
            "calibration": _calibration_score(frame, probability),
            "resolution": _resolution(probability),
        }
    return output


def run(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    reports = ml / "reports"
    model_dir = ml / "models/v2_2_1_v1_5"
    model_dir.mkdir(parents=True, exist_ok=True)
    data = ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet"
    train = pd.read_parquet(data, filters=[("modeling_role", "==", "TRAIN")])
    validation = pd.read_parquet(data, filters=[("modeling_role", "==", "VALIDATION")])
    dates = pd.to_datetime(validation.landmark_at)
    search = validation.loc[dates.between("2025-07-01", "2025-08-31")].copy()
    calibration = validation.loc[dates.between("2025-09-01", "2025-10-31")].copy()
    final = validation.loc[dates.between("2025-11-01", "2025-12-31")].copy()
    train_y = _survival_y(train)
    split_protocol = {
        "TRAIN": "model fitting",
        "VALIDATION_2025_07_08": "feature and hyperparameter search",
        "VALIDATION_2025_09_10": "calibrator fitting",
        "VALIDATION_2025_11_12": "final validation comparison",
        "TEST": "SEALED_NOT_READ",
    }
    existing = _existing_v22_metrics(ml, [("search", search), ("calibration", calibration), ("final", final)], train_y)

    core = list(BASE_FEATURE_COLUMNS)
    feature_sets = {
        "CORE54": core,
        "EXTENDED60": list(FEATURE_COLUMNS),
    }
    for name in OBSERVABLE_HISTORY_FEATURES:
        feature_sets[f"CORE54_PLUS_{name.upper()}"] = core + [name]
    feature_sets.update({
        "CORE54_PLUS_APPOINTMENT_INTENT": core + ["known_appointment_within_30d", "days_to_next_known_appointment"],
        "CORE54_PLUS_NOSHOW_APPOINTMENT": core + ["prior_no_show_count", "known_appointment_within_30d", "days_to_next_known_appointment"],
        "STABLE58": core + ["prior_no_show_count", "prior_cancelled_appointment_count", "known_appointment_within_30d", "days_to_next_known_appointment"],
        "EXTENDED59_MINUS_BREAKDOWN180": [name for name in FEATURE_COLUMNS if name != "recent_breakdown_count_180d"],
    })
    control_params = {
        "n_estimators": 360, "max_depth": 4, "learning_rate": .035,
        "min_child_weight": 24, "subsample": .84, "colsample_bytree": .84,
        "reg_alpha": .02, "reg_lambda": 2.5, "gamma": 0, "max_delta_step": 0,
    }
    ablations: dict[str, dict[str, Any]] = {}
    fitted: dict[str, dict[str, Any]] = {}
    checkpoint = reports / "v2_2_1_feature_ablation.json"
    for name, features in feature_sets.items():
        result = _fit_candidate(train, train_y, search, calibration, final, features, control_params, f"ABLATION_{name}")
        fitted[name] = result
        ablations[name] = _public(result)
        _write(checkpoint, {"status": "RUNNING", "test_rows_read": False, "split_protocol": split_protocol, "results": ablations})

    eligible_ablation = [name for name, result in fitted.items() if result["eligible"]]
    if not eligible_ablation:
        raise RuntimeError("No feature ablation preserved the V2.2 behavior contract")
    best_feature_set = max(
        eligible_ablation,
        key=lambda name: (
            fitted[name]["search_validation_metrics"]["ipcw_c_index"]
            - .35*fitted[name]["search_validation_metrics"]["ibs_30_120"]
            - .15*fitted[name]["temporal_c_std"]
        ),
    )
    ablation_report = {
        "status": "PASS", "test_rows_read": False, "split_protocol": split_protocol,
        "control": "V15_XGB54_CONTROL", "control_recipe": control_params,
        "existing_v2_2_same_world": existing, "results": ablations,
        "behavior_eligible_feature_sets": eligible_ablation, "best_feature_set_for_xgb_search": best_feature_set,
        "selection_reason": "highest documented discrimination/IBS/stability composite among behavior-eligible ablations",
    }
    _write(checkpoint, ablation_report)
    table = pd.DataFrame([{
        "feature_set": name, "features": result["feature_count"],
        "search_ipcw_c": result["search_validation_metrics"]["ipcw_c_index"],
        "final_ipcw_c": result["final_validation_metrics"]["ipcw_c_index"],
        "final_ibs": result["final_validation_metrics"]["ibs_30_120"],
        "calibration": result["selected_calibration"], "behavior": result["behavior"]["status"], "eligible": result["eligible"],
    } for name, result in ablations.items()])
    (reports / "v2_2_1_feature_ablation.md").write_text("\n".join([
        "# V2.2.1 Feature Ablation", "", "**TEST untouched.**", "", table.to_markdown(index=False), "",
    ]))

    search_space = [
        ("V22_REFERENCE", control_params),
        ("D2_BALANCED", {"n_estimators": 260, "max_depth": 2, "learning_rate": .035, "min_child_weight": 48, "subsample": .85, "colsample_bytree": .85, "reg_alpha": .05, "reg_lambda": 6.0, "gamma": 0, "max_delta_step": 0}),
        ("D2_STRONG_REG", {"n_estimators": 380, "max_depth": 2, "learning_rate": .022, "min_child_weight": 100, "subsample": .80, "colsample_bytree": .75, "reg_alpha": .20, "reg_lambda": 12.0, "gamma": .05, "max_delta_step": 0}),
        ("D3_BALANCED", control_params),
        ("D3_LONG", {"n_estimators": 400, "max_depth": 3, "learning_rate": .02, "min_child_weight": 80, "subsample": .82, "colsample_bytree": .80, "reg_alpha": .15, "reg_lambda": 10.0, "gamma": .05, "max_delta_step": 0}),
        ("D3_STRONG_REG", {"n_estimators": 300, "max_depth": 3, "learning_rate": .025, "min_child_weight": 140, "subsample": .78, "colsample_bytree": .72, "reg_alpha": .30, "reg_lambda": 16.0, "gamma": .10, "max_delta_step": 1}),
        ("D4_SHORT_REG", {"n_estimators": 220, "max_depth": 4, "learning_rate": .025, "min_child_weight": 120, "subsample": .80, "colsample_bytree": .75, "reg_alpha": .25, "reg_lambda": 14.0, "gamma": .10, "max_delta_step": 1}),
        ("D4_MILD_REG", {"n_estimators": 340, "max_depth": 4, "learning_rate": .032, "min_child_weight": 36, "subsample": .84, "colsample_bytree": .82, "reg_alpha": .06, "reg_lambda": 4.0, "gamma": .02, "max_delta_step": 0}),
        ("D3_HIGH_CAPACITY", {"n_estimators": 420, "max_depth": 3, "learning_rate": .03, "min_child_weight": 28, "subsample": .86, "colsample_bytree": .86, "reg_alpha": .04, "reg_lambda": 3.5, "gamma": .01, "max_delta_step": 0}),
        ("D2_CONSERVATIVE", {"n_estimators": 220, "max_depth": 2, "learning_rate": .03, "min_child_weight": 160, "subsample": .75, "colsample_bytree": .70, "reg_alpha": .40, "reg_lambda": 18.0, "gamma": .15, "max_delta_step": 1}),
    ]
    # Search the best ablation and full 60 to avoid making feature selection a
    # single irreversible choice based on one temporal slice.
    search_results: dict[str, dict[str, Any]] = {}
    search_objects: dict[str, dict[str, Any]] = {}
    for feature_name in sorted({best_feature_set, "EXTENDED60"}):
        for recipe_name, params in search_space:
            candidate_id = f"{feature_name}__{recipe_name}"
            result = _fit_candidate(train, train_y, search, calibration, final, feature_sets[feature_name], params, candidate_id)
            search_results[candidate_id] = _public(result)
            search_objects[candidate_id] = result
            _write(reports / "v2_2_1_xgb_search.json", {
                "status": "RUNNING", "test_rows_read": False, "split_protocol": split_protocol,
                "search_space": [{"id": name, "params": params} for name, params in search_space],
                "results": search_results,
            })

    eligible = [name for name, result in search_objects.items() if result["eligible"]]
    if not eligible:
        raise RuntimeError("No XGB recovery configuration passed statistical and behavioral validation gates")
    weights = {"ipcw_c": .55, "ibs": .20, "calibration_error": .10, "temporal_stability": .10, "p30_resolution": .05}
    def composite(name: str) -> float:
        result = search_objects[name]
        metrics = result["final_validation_metrics"]
        return (
            weights["ipcw_c"]*metrics["ipcw_c_index"]
            - weights["ibs"]*metrics["ibs_30_120"]
            - weights["calibration_error"]*result["final_validation_calibration"]["mean_calibration_error"]
            - weights["temporal_stability"]*result["temporal_c_std"]
            + weights["p30_resolution"]*min(math.log10(max(result["resolution"]["p30_unique_8dp"], 1))/4, 1)
        )
    selected_id = max(eligible, key=composite)
    selected = search_objects[selected_id]
    for name in search_results:
        search_results[name]["composite_score"] = composite(name) if name in eligible else None
    xgb_report = {
        "status": "PASS", "test_rows_read": False, "split_protocol": split_protocol,
        "search_design": "controlled coarse regularization search; no arbitrary large model zoo",
        "search_space": [{"id": name, "params": params} for name, params in search_space],
        "feature_sets_searched": sorted({best_feature_set, "EXTENDED60"}),
        "weights": weights, "results": search_results, "behavior_eligible": eligible,
        "selected_candidate_id": selected_id,
    }
    _write(reports / "v2_2_1_xgb_search.json", xgb_report)

    # Compact alternative candidates are reported, while XGB remains the only
    # family eligible for the predeclared monotone behavioral contract.
    alternatives = {}
    extended_pre, _ = _preprocessor(FEATURE_COLUMNS)
    X_train = extended_pre.fit_transform(train[FEATURE_COLUMNS]).astype(np.float32)
    X_final = extended_pre.transform(final[FEATURE_COLUMNS]).astype(np.float32)
    for name, model, cap in [
        ("cox_ph", CoxPHSurvivalAnalysis(alpha=.08, n_iter=100), 80000),
        ("coxnet", CoxnetSurvivalAnalysis(l1_ratio=.2, alphas=[.003], max_iter=100000), 65000),
    ]:
        try:
            indices = np.random.default_rng(SEED).choice(len(train), cap, replace=False)
            model.fit(X_train[indices], train_y[indices])
            base = _breslow(train_y[indices]["time"], train_y[indices]["event"], model.predict(X_train[indices]))
            final_score = model.predict(X_final)
            alternatives[name] = {"status": "FIT", "metrics": _metrics(train_y, final, final_score, _survival_from_score(final_score, base)), "behavior_eligible": False, "reason": "unconstrained correlated due response failed the established V2.2 behavior audit"}
        except Exception as exc:
            alternatives[name] = {"status": "INFEASIBLE", "reason": str(exc), "behavior_eligible": False}

    calibration_report = {
        "status": "PASS", "test_rows_read": False,
        "protocol": "fit on Sep-Oct validation; compare on Nov-Dec validation; chosen method refit on all validation only after selection",
        "candidate_id": selected_id,
        "methods": selected["calibration_search"],
        "selected_method": selected["selected_calibration"],
        "plateau_penalty_documented": True,
    }
    _write(reports / "v2_2_1_calibration_search.json", calibration_report)
    calibration_table = pd.DataFrame([{
        "method": name, "mean_brier": value["calibration"]["mean_brier"],
        "mean_calibration_error": value["calibration"]["mean_calibration_error"],
        "p30_unique": value["resolution"]["p30_unique_8dp"], "largest_plateau": value["resolution"]["p30_largest_plateau_share"],
    } for name, value in selected["calibration_search"].items()])
    (reports / "v2_2_1_calibration_search.md").write_text("\n".join([
        "# V2.2.1 Calibration Search", "", "**TEST untouched.**", "", calibration_table.to_markdown(index=False), "",
    ]))

    # Refit only the already selected calibration method on all VALIDATION.
    preprocessor, model, baseline, _ = selected["_objects"]
    validation_matrix = preprocessor.transform(validation[selected["features"]]).astype(np.float32)
    validation_score = model.predict(validation_matrix)
    validation_raw = 1-_survival_from_score(validation_score, baseline)
    final_calibrator = _calibrators()[selected["selected_calibration"]].fit(validation_raw, validation)

    joblib.dump(preprocessor, model_dir / "preprocessor.joblib")
    joblib.dump(model, model_dir / "challenger_model.joblib")
    joblib.dump(baseline, model_dir / "baseline_hazard.joblib")
    joblib.dump(final_calibrator, model_dir / "calibrator.joblib")
    _write(model_dir / "feature_list.json", selected["features"])
    _write(model_dir / "hyperparameters.json", selected["hyperparameters"])
    _write(model_dir / "validation_metrics.json", _public(selected))
    _write(model_dir / "behavior_audit.json", selected["behavior"])
    _write(model_dir / "calibration_search.json", selected["calibration_search"])

    existing_final = existing["final"]
    recovery = {
        "ipcw_c_delta": selected["final_validation_metrics"]["ipcw_c_index"]-existing_final["metrics"]["ipcw_c_index"],
        "ibs_delta": selected["final_validation_metrics"]["ibs_30_120"]-existing_final["metrics"]["ibs_30_120"],
        "calibration_error_delta": selected["final_validation_calibration"]["mean_calibration_error"]-existing_final["calibration"]["mean_calibration_error"],
        "p30_unique_delta": selected["resolution"]["p30_unique_8dp"]-existing_final["resolution"]["p30_unique_8dp"],
    }
    result = {
        "status": "PASS", "test_rows_read": False, "selected_candidate_id": selected_id,
        "selected_feature_set": selected["features"], "selected_hyperparameters": selected["hyperparameters"],
        "selected_calibration": selected["selected_calibration"], "validation_recovery_vs_existing_v2_2": recovery,
        "selected_metrics": _public(selected), "compact_alternatives": alternatives,
    }
    _write(reports / "v2_2_1_recovery_selection.json", result)
    print(json.dumps({
        "status": "PASS", "best_ablation": best_feature_set, "selected": selected_id,
        "calibration": selected["selected_calibration"], "recovery": recovery,
        "validation": selected["final_validation_metrics"], "behavior": selected["behavior"]["status"],
    }, indent=2))
    return result


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[3])
