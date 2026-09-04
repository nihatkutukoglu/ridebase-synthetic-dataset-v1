"""Small evidence-driven refinement around the V2.2 XGB-Cox recipe."""

from __future__ import annotations

import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ridebase_ml.v2_1.survival import _survival_from_score
from ridebase_ml.v2_2.landmarks import FEATURE_COLUMNS
from ridebase_ml.v2_2.train import _survival_y
from ridebase_ml.v2_2_1.search import _calibrators, _fit_candidate, _public, _write


def run(repo_root: Path) -> dict:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    reports = ml / "reports"
    model_dir = ml / "models/v2_2_1_v1_5"
    data = ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet"
    train = pd.read_parquet(data, filters=[("modeling_role", "==", "TRAIN")])
    validation = pd.read_parquet(data, filters=[("modeling_role", "==", "VALIDATION")])
    dates = pd.to_datetime(validation.landmark_at)
    search = validation.loc[dates.between("2025-07-01", "2025-08-31")].copy()
    calibration = validation.loc[dates.between("2025-09-01", "2025-10-31")].copy()
    final = validation.loc[dates.between("2025-11-01", "2025-12-31")].copy()
    train_y = _survival_y(train)

    recipes = [
        ("BC_D4_REFERENCE", {"n_estimators": 360, "max_depth": 4, "learning_rate": .035, "min_child_weight": 24, "subsample": .84, "colsample_bytree": .84, "reg_alpha": .02, "reg_lambda": 2.5, "gamma": 0, "max_delta_step": 0, "constraint_profile": "behavior_core"}),
        ("BC_D4_MILD_REG", {"n_estimators": 340, "max_depth": 4, "learning_rate": .032, "min_child_weight": 36, "subsample": .84, "colsample_bytree": .82, "reg_alpha": .06, "reg_lambda": 4.0, "gamma": .02, "max_delta_step": 0, "constraint_profile": "behavior_core"}),
        ("BC_D4_LONG", {"n_estimators": 480, "max_depth": 4, "learning_rate": .025, "min_child_weight": 32, "subsample": .85, "colsample_bytree": .84, "reg_alpha": .05, "reg_lambda": 3.5, "gamma": .01, "max_delta_step": 0, "constraint_profile": "behavior_core"}),
        ("BC_D3_LONG", {"n_estimators": 480, "max_depth": 3, "learning_rate": .028, "min_child_weight": 32, "subsample": .86, "colsample_bytree": .86, "reg_alpha": .04, "reg_lambda": 3.5, "gamma": .01, "max_delta_step": 0, "constraint_profile": "behavior_core"}),
        ("BC_D5_SHORT", {"n_estimators": 260, "max_depth": 5, "learning_rate": .03, "min_child_weight": 42, "subsample": .82, "colsample_bytree": .80, "reg_alpha": .08, "reg_lambda": 5.0, "gamma": .03, "max_delta_step": 0, "constraint_profile": "behavior_core"}),
        ("BC_D5_REFERENCE", {"n_estimators": 340, "max_depth": 5, "learning_rate": .028, "min_child_weight": 28, "subsample": .84, "colsample_bytree": .82, "reg_alpha": .05, "reg_lambda": 4.0, "gamma": .01, "max_delta_step": 0, "constraint_profile": "behavior_core"}),
    ]
    xgb_report = json.loads((reports / "v2_2_1_xgb_search.json").read_text())
    weights = xgb_report["weights"]
    refined = {}
    objects = {}
    for recipe_id, params in recipes:
        candidate_id = f"EXTENDED60__{recipe_id}"
        result = _fit_candidate(train, train_y, search, calibration, final, FEATURE_COLUMNS, params, candidate_id)
        refined[candidate_id] = _public(result)
        objects[candidate_id] = result
        xgb_report["results"][candidate_id] = refined[candidate_id]
        _write(reports / "v2_2_1_xgb_search.json", {**xgb_report, "status": "REFINING", "refinement_completed": len(refined)})

    def composite(result: dict) -> float:
        metrics = result["final_validation_metrics"]
        return (
            weights["ipcw_c"]*metrics["ipcw_c_index"]
            - weights["ibs"]*metrics["ibs_30_120"]
            - weights["calibration_error"]*result["final_validation_calibration"]["mean_calibration_error"]
            - weights["temporal_stability"]*result["temporal_c_std"]
            + weights["p30_resolution"]*min(math.log10(max(result["resolution"]["p30_unique_8dp"], 1))/4, 1)
        )

    for name, result in refined.items():
        xgb_report["results"][name]["composite_score"] = composite(result) if result["eligible"] else None
    old_id = xgb_report["selected_candidate_id"]
    old_score = xgb_report["results"][old_id]["composite_score"]
    eligible_refined = [name for name, result in objects.items() if result["eligible"]]
    best_refined = max(eligible_refined, key=lambda name: composite(objects[name])) if eligible_refined else None
    if best_refined is not None and composite(objects[best_refined]) > old_score:
        selected_id = best_refined
        selected = objects[selected_id]
        preprocessor, model, baseline, _ = selected["_objects"]
        validation_matrix = preprocessor.transform(validation[selected["features"]]).astype(np.float32)
        validation_score = model.predict(validation_matrix)
        validation_raw = 1-_survival_from_score(validation_score, baseline)
        calibrator = _calibrators()[selected["selected_calibration"]].fit(validation_raw, validation)
        joblib.dump(preprocessor, model_dir / "preprocessor.joblib")
        joblib.dump(model, model_dir / "challenger_model.joblib")
        joblib.dump(baseline, model_dir / "baseline_hazard.joblib")
        joblib.dump(calibrator, model_dir / "calibrator.joblib")
        _write(model_dir / "feature_list.json", selected["features"])
        _write(model_dir / "hyperparameters.json", selected["hyperparameters"])
        _write(model_dir / "validation_metrics.json", _public(selected))
        _write(model_dir / "behavior_audit.json", selected["behavior"])
        _write(model_dir / "calibration_search.json", selected["calibration_search"])
    else:
        selected_id = old_id
        selected = None

    xgb_report.update({
        "status": "PASS", "refinement_design": "behavior-core monotonic constraints only; six controlled recipes",
        "refinement_results": list(refined), "selected_candidate_id": selected_id,
    })
    _write(reports / "v2_2_1_xgb_search.json", xgb_report)
    selection = json.loads((reports / "v2_2_1_recovery_selection.json").read_text())
    if selected is not None:
        old_final = json.loads((reports / "v2_2_1_feature_ablation.json").read_text())["existing_v2_2_same_world"]["final"]
        selection.update({
            "selected_candidate_id": selected_id,
            "selected_feature_set": selected["features"],
            "selected_hyperparameters": selected["hyperparameters"],
            "selected_calibration": selected["selected_calibration"],
            "selected_metrics": _public(selected),
            "validation_recovery_vs_existing_v2_2": {
                "ipcw_c_delta": selected["final_validation_metrics"]["ipcw_c_index"]-old_final["metrics"]["ipcw_c_index"],
                "ibs_delta": selected["final_validation_metrics"]["ibs_30_120"]-old_final["metrics"]["ibs_30_120"],
                "calibration_error_delta": selected["final_validation_calibration"]["mean_calibration_error"]-old_final["calibration"]["mean_calibration_error"],
                "p30_unique_delta": selected["resolution"]["p30_unique_8dp"]-old_final["resolution"]["p30_unique_8dp"],
            },
        })
        _write(reports / "v2_2_1_recovery_selection.json", selection)
        calibration_report = json.loads((reports / "v2_2_1_calibration_search.json").read_text())
        calibration_report.update({"candidate_id": selected_id, "methods": selected["calibration_search"], "selected_method": selected["selected_calibration"]})
        _write(reports / "v2_2_1_calibration_search.json", calibration_report)
    output = {
        "status": "PASS", "old_selected": old_id, "final_selected": selected_id,
        "old_composite": old_score,
        "best_refined_composite": composite(objects[best_refined]) if best_refined else None,
        "recovery": selection["validation_recovery_vs_existing_v2_2"],
    }
    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[3])
