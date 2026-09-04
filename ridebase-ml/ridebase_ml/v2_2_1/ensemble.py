"""Behavior-gated constrained/free XGB-Cox risk ensemble recovery."""

from __future__ import annotations

import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from ridebase_ml.v2_1.survival import _survival_from_score
from ridebase_ml.v2_2.landmarks import FEATURE_COLUMNS
from ridebase_ml.v2_2.train import _breslow, _calibration_score, _large_behavior_audit, _metrics, _survival_y
from ridebase_ml.v2_2_1.models import StandardizedRiskBlendModel
from ridebase_ml.v2_2_1.search import _calibrators, _resolution, _write


SEED = 52


def run(repo_root: Path) -> dict:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    reports = ml / "reports"
    target_dir = ml / "models/v2_2_1_v1_5"
    source_dir = ml / "models/v2_2_v1_5"
    data = ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet"
    train = pd.read_parquet(data, filters=[("modeling_role", "==", "TRAIN")])
    validation = pd.read_parquet(data, filters=[("modeling_role", "==", "VALIDATION")])
    dates = pd.to_datetime(validation.landmark_at)
    search = validation.loc[dates.between("2025-07-01", "2025-08-31")].copy()
    calibration = validation.loc[dates.between("2025-09-01", "2025-10-31")].copy()
    final = validation.loc[dates.between("2025-11-01", "2025-12-31")].copy()
    train_y = _survival_y(train)
    preprocessor = joblib.load(source_dir / "preprocessor.joblib")
    constrained = joblib.load(source_dir / "challenger_model.joblib")
    X_train = preprocessor.transform(train[FEATURE_COLUMNS]).astype(np.float32)
    matrices = {name: preprocessor.transform(frame[FEATURE_COLUMNS]).astype(np.float32) for name, frame in [("search", search), ("calibration", calibration), ("final", final)]}
    constrained_train = constrained.predict(X_train)
    recipes = [
        ("FREE_D3", {"n_estimators": 420, "max_depth": 3, "learning_rate": .03, "min_child_weight": 40, "subsample": .84, "colsample_bytree": .82, "reg_alpha": .08, "reg_lambda": 5.0, "gamma": .02}),
        ("FREE_D4", {"n_estimators": 340, "max_depth": 4, "learning_rate": .03, "min_child_weight": 56, "subsample": .82, "colsample_bytree": .80, "reg_alpha": .10, "reg_lambda": 7.0, "gamma": .03}),
        ("FREE_D5", {"n_estimators": 260, "max_depth": 5, "learning_rate": .028, "min_child_weight": 72, "subsample": .80, "colsample_bytree": .78, "reg_alpha": .15, "reg_lambda": 9.0, "gamma": .05}),
    ]
    labels = np.where(train_y["event"], train_y["time"], -train_y["time"])
    results = {}
    objects = {}
    for recipe_id, params in recipes:
        free = XGBRegressor(objective="survival:cox", monotone_constraints=tuple([0]*X_train.shape[1]), random_state=SEED, n_jobs=6, **params)
        free.fit(X_train, labels, verbose=False)
        free_train = free.predict(X_train)
        for weight in [.02, .05, .08, .10, .20, .30, .40]:
            candidate_id = f"BLEND_{recipe_id}_W{int(weight*100)}"
            model = StandardizedRiskBlendModel(
                constrained, free, float(constrained_train.mean()), float(constrained_train.std()),
                float(free_train.mean()), float(free_train.std()), weight,
            )
            train_score = model.predict(X_train)
            baseline = _breslow(train_y["time"], train_y["event"], train_score)
            score = {name: model.predict(matrix) for name, matrix in matrices.items()}
            raw = {name: 1-_survival_from_score(value, baseline) for name, value in score.items()}
            search_metrics = _metrics(train_y, search, score["search"], 1-raw["search"])
            calibration_results = {}
            fitted = {}
            behavior_by_method = {}
            for method, calibrator in _calibrators().items():
                calibrator.fit(raw["calibration"], calibration)
                probability = calibrator.transform(raw["final"])
                calibration_results[method] = {
                    "calibration": _calibration_score(final, probability),
                    "resolution": _resolution(probability),
                }
                fitted[method] = calibrator
                if (
                    calibration_results[method]["calibration"]["mean_brier"] <= .18
                    and calibration_results[method]["calibration"]["mean_calibration_error"] <= .10
                    and calibration_results[method]["resolution"]["p30_exact_zero_share"] <= .02
                ):
                    def predict(rows: pd.DataFrame, chosen=calibrator) -> np.ndarray:
                        matrix = preprocessor.transform(rows[FEATURE_COLUMNS]).astype(np.float32)
                        risk = model.predict(matrix)
                        return chosen.transform(1-_survival_from_score(risk, baseline))
                    behavior_by_method[method] = _large_behavior_audit(search, predict)
            behavior_methods = [name for name, audit in behavior_by_method.items() if audit["status"] == "PASS"]
            if behavior_methods:
                selected_calibration = min(
                    behavior_methods,
                    key=lambda name: (
                        calibration_results[name]["calibration"]["mean_brier"]
                        + calibration_results[name]["calibration"]["mean_calibration_error"]
                        + .02*calibration_results[name]["resolution"]["p30_largest_plateau_share"]
                    ),
                )
                calibrator = fitted[selected_calibration]
                final_probability = calibrator.transform(raw["final"])
                final_metrics = _metrics(train_y, final, score["final"], 1-final_probability)
                behavior = behavior_by_method[selected_calibration]
                eligible = final_metrics["ipcw_c_index"] >= .65 and final_metrics["ibs_30_120"] <= .18
            else:
                selected_calibration = None; calibrator = None; final_metrics = {}; behavior = {"status": "FAIL", "failed_checks": ["no_calibration_preserved_behavior"]}; eligible = False
            result = {
                "candidate_id": candidate_id, "recipe": recipe_id, "hyperparameters": params,
                "free_risk_weight": weight, "feature_count": 60,
                "search_validation_metrics": search_metrics,
                "calibration_search": calibration_results,
                "calibration_behavior_status": {name: audit["status"] for name, audit in behavior_by_method.items()},
                "selected_calibration": selected_calibration,
                "final_validation_metrics": final_metrics,
                "final_validation_calibration": calibration_results[selected_calibration]["calibration"] if selected_calibration else {},
                "resolution": calibration_results[selected_calibration]["resolution"] if selected_calibration else {},
                "behavior": behavior,
                "eligible": eligible,
            }
            results[candidate_id] = result
            objects[candidate_id] = (model, baseline, calibrator)
            _write(reports / "v2_2_1_ensemble_search.json", {"status": "RUNNING", "test_rows_read": False, "results": results})

    old_search = json.loads((reports / "v2_2_1_xgb_search.json").read_text())
    weights = old_search["weights"]
    old_id = old_search["selected_candidate_id"]
    old_score = old_search["results"][old_id]["composite_score"]
    def composite(result: dict) -> float:
        metrics = result["final_validation_metrics"]
        return (
            weights["ipcw_c"]*metrics["ipcw_c_index"]
            - weights["ibs"]*metrics["ibs_30_120"]
            - weights["calibration_error"]*result["final_validation_calibration"]["mean_calibration_error"]
            + weights["p30_resolution"]*min(math.log10(max(result["resolution"]["p30_unique_8dp"], 1))/4, 1)
        )
    eligible = [name for name, result in results.items() if result["eligible"]]
    for name in results:
        results[name]["composite_score"] = composite(results[name]) if name in eligible else None
    best = max(eligible, key=lambda name: composite(results[name])) if eligible else None
    selected_new = bool(best and composite(results[best]) > old_score and results[best]["final_validation_metrics"]["ipcw_c_index"] > old_search["results"][old_id]["final_validation_metrics"]["ipcw_c_index"])
    if selected_new:
        model, baseline, _ = objects[best]
        validation_score = model.predict(preprocessor.transform(validation[FEATURE_COLUMNS]).astype(np.float32))
        validation_raw = 1-_survival_from_score(validation_score, baseline)
        calibrator = _calibrators()[results[best]["selected_calibration"]].fit(validation_raw, validation)
        joblib.dump(preprocessor, target_dir / "preprocessor.joblib")
        joblib.dump(model, target_dir / "challenger_model.joblib")
        joblib.dump(baseline, target_dir / "baseline_hazard.joblib")
        joblib.dump(calibrator, target_dir / "calibrator.joblib")
        _write(target_dir / "feature_list.json", FEATURE_COLUMNS)
        _write(target_dir / "hyperparameters.json", {"ensemble": results[best]["hyperparameters"], "free_risk_weight": results[best]["free_risk_weight"]})
        _write(target_dir / "validation_metrics.json", results[best])
        _write(target_dir / "behavior_audit.json", results[best]["behavior"])
        _write(target_dir / "calibration_search.json", results[best]["calibration_search"])
        selection = json.loads((reports / "v2_2_1_recovery_selection.json").read_text())
        existing_final = json.loads((reports / "v2_2_1_feature_ablation.json").read_text())["existing_v2_2_same_world"]["final"]
        selection.update({
            "selected_candidate_id": best, "selected_feature_set": FEATURE_COLUMNS,
            "selected_hyperparameters": {"ensemble": results[best]["hyperparameters"], "free_risk_weight": results[best]["free_risk_weight"]},
            "selected_calibration": results[best]["selected_calibration"], "selected_metrics": results[best],
            "validation_recovery_vs_existing_v2_2": {
                "ipcw_c_delta": results[best]["final_validation_metrics"]["ipcw_c_index"]-existing_final["metrics"]["ipcw_c_index"],
                "ibs_delta": results[best]["final_validation_metrics"]["ibs_30_120"]-existing_final["metrics"]["ibs_30_120"],
                "calibration_error_delta": results[best]["final_validation_calibration"]["mean_calibration_error"]-existing_final["calibration"]["mean_calibration_error"],
                "p30_unique_delta": results[best]["resolution"]["p30_unique_8dp"]-existing_final["resolution"]["p30_unique_8dp"],
            },
        })
        _write(reports / "v2_2_1_recovery_selection.json", selection)
    report = {
        "status": "PASS", "test_rows_read": False, "design": "TRAIN-standardized constrained/free risk blend",
        "recipes": [{"id": name, "params": params} for name, params in recipes],
        "weights": [.02, .05, .08, .10, .20, .30, .40], "results": results, "behavior_eligible": eligible,
        "previous_selected": old_id, "previous_composite": old_score,
        "best_ensemble": best, "best_composite": composite(results[best]) if best else None,
        "ensemble_selected": selected_new,
    }
    _write(reports / "v2_2_1_ensemble_search.json", report)
    print(json.dumps({
        "status": "PASS", "eligible": eligible, "best": best, "selected": selected_new,
        "old_score": old_score, "best_score": report["best_composite"],
        "best_metrics": results[best]["final_validation_metrics"] if best else None,
        "best_behavior": results[best]["behavior"]["status"] if best else None,
    }, indent=2))
    return report


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[3])
