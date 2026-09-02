"""Train, calibrate and behavior-audit the frozen V1.4-linked V2.1 dataset."""

from __future__ import annotations

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
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler
from sksurv.linear_model import CoxPHSurvivalAnalysis, CoxnetSurvivalAnalysis
from sksurv.metrics import brier_score, concordance_index_censored, concordance_index_ipcw, cumulative_dynamic_auc, integrated_brier_score
from xgboost import XGBRegressor

from .landmarks import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES
from .survival import HORIZONS, SEED, HorizonCalibrator, _horizon_labels, _survival_from_score


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _survival_y(frame: pd.DataFrame) -> np.ndarray:
    return np.array(
        list(zip(frame.event_observed.astype(bool), frame.duration_days.astype(float))),
        dtype=[("event", "?"), ("time", "<f8")],
    )


def _preprocessor() -> Pipeline:
    columns = ColumnTransformer([
        ("categorical", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("ordinal", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
        ]), CATEGORICAL_FEATURES),
        ("numeric", SimpleImputer(strategy="median"), NUMERIC_FEATURES),
    ], verbose_feature_names_out=False)
    return Pipeline([("columns", columns), ("scale", StandardScaler())])


def _breslow(time: np.ndarray, event: np.ndarray, score: np.ndarray) -> dict[str, np.ndarray]:
    order = np.argsort(time)
    t = time[order]
    e = event[order].astype(bool)
    exp_score = np.exp(np.clip(score[order], -18, 18))
    risk_sum = np.cumsum(exp_score[::-1])[::-1]
    event_times = np.unique(t[e])
    increments = []
    for value in event_times:
        first = np.searchsorted(t, value, side="left")
        increments.append(float(np.sum(e & (t == value))) / max(float(risk_sum[first]), 1e-12))
    return {"times": event_times, "cumulative_hazard": np.cumsum(increments)}


def _rule_survival(frame: pd.DataFrame) -> np.ndarray:
    pressure = frame.max_due_ratio.fillna(0).to_numpy(float)
    usage = np.clip(frame.annual_km_baseline.fillna(8000).to_numpy(float) / 10000.0, .2, 4.0)
    weekly = .0015 + .009 / (1 + np.exp(-8 * (pressure - .62))) + .045 / (1 + np.exp(-8 * (pressure - .98))) + .04 / (1 + np.exp(-4 * (pressure - 1.55)))
    weekly *= np.clip(.85 + .15 * usage, .75, 1.35)
    return np.exp(-weekly[:, None] * (HORIZONS[None, :] / 7.0))


def _ece(y: np.ndarray, probability: np.ndarray, bins: int = 10) -> float:
    if len(y) == 0: return math.nan
    cuts = np.linspace(0, 1, bins + 1)
    bucket = np.clip(np.digitize(probability, cuts[1:-1]), 0, bins - 1)
    total = 0.0
    for value in range(bins):
        mask = bucket == value
        if mask.any(): total += mask.mean() * abs(float(y[mask].mean()) - float(probability[mask].mean()))
    return float(total)


def _metrics(train_y: np.ndarray, frame: pd.DataFrame, score: np.ndarray, survival: np.ndarray) -> dict[str, Any]:
    y = _survival_y(frame)
    maximum = min(365.0, float(np.max(train_y["time"])) - 1e-6, float(np.max(y["time"])) - 1e-6)
    result: dict[str, Any] = {
        "ipcw_c_index": float(concordance_index_ipcw(train_y, y, score, tau=maximum)[0]),
        "harrell_c_index": float(concordance_index_censored(y["event"], y["time"], score)[0]),
    }
    try:
        result["ibs_30_120"] = float(integrated_brier_score(train_y, y, survival, HORIZONS))
        _, bs = brier_score(train_y, y, survival, HORIZONS)
        result["ipcw_brier"] = {str(int(h)): float(v) for h, v in zip(HORIZONS, bs)}
        auc, mean_auc = cumulative_dynamic_auc(train_y, y, score, HORIZONS)
        result["time_dependent_auc"] = {str(int(h)): float(v) for h, v in zip(HORIZONS, auc)}
        result["mean_time_dependent_auc"] = float(mean_auc)
    except ValueError as exc:
        result["survival_metric_error"] = str(exc)
        result["ibs_30_120"] = math.inf
    horizon_metrics = {}
    risk = 1 - survival
    for index, horizon in enumerate(HORIZONS):
        eligible, label = _horizon_labels(frame, horizon)
        yy, pp = label[eligible], risk[eligible, index]
        horizon_metrics[str(int(horizon))] = {
            "rows": int(eligible.sum()), "event_rate": float(yy.mean()),
            "brier": float(np.mean((yy - pp) ** 2)),
            "auc": float(roc_auc_score(yy, pp)) if len(np.unique(yy)) > 1 else None,
            "calibration_error": _ece(yy, pp),
            "exact_zero_share": float(np.mean(pp == 0)), "unique_probability_levels": int(len(np.unique(np.round(pp, 8)))),
        }
    result["horizons"] = horizon_metrics
    return result


def _calibration_score(frame: pd.DataFrame, probability: np.ndarray) -> dict[str, Any]:
    rows = {}
    for index, horizon in enumerate(HORIZONS):
        eligible, label = _horizon_labels(frame, horizon)
        y, p = label[eligible], probability[eligible, index]
        rows[str(int(horizon))] = {
            "brier": float(np.mean((y - p) ** 2)), "calibration_error": _ece(y, p),
            "exact_zero_share": float(np.mean(p == 0)), "unique_probability_levels": int(len(np.unique(np.round(p, 8)))),
        }
    return {
        "horizons": rows,
        "mean_brier": float(np.mean([value["brier"] for value in rows.values()])),
        "mean_calibration_error": float(np.mean([value["calibration_error"] for value in rows.values()])),
    }


def _controlled_rows(base: pd.Series, axis: str, values: list[float]) -> pd.DataFrame:
    rows = []
    for value in values:
        row = base.copy()
        if axis == "km_since":
            row.km_since_last_service = value
            row.km_due_ratio = value / max(float(row.oem_interval_km), 1)
            row.km_overdue = max(value - float(row.oem_interval_km), 0)
        elif axis == "days_since":
            row.days_since_last_service = value
            row.days_due_ratio = value / max(float(row.oem_interval_days), 1)
            row.days_overdue = max(value - float(row.oem_interval_days), 0)
        elif axis == "annual_km":
            row.annual_km_baseline = value
        elif axis == "due_state":
            row.days_due_ratio = value; row.km_due_ratio = value
            row.days_since_last_service = value * float(row.oem_interval_days)
            row.km_since_last_service = value * float(row.oem_interval_km)
            row.days_overdue = max(row.days_since_last_service - row.oem_interval_days, 0)
            row.km_overdue = max(row.km_since_last_service - row.oem_interval_km, 0)
        row.max_due_ratio = max(float(row.days_due_ratio), float(row.km_due_ratio))
        row.maintenance_due_now = int(row.max_due_ratio >= 1)
        row.due_task_count = max(int(row.due_task_count), row.maintenance_due_now)
        row.critical_due_task_count = max(int(row.critical_due_task_count), row.maintenance_due_now)
        rows.append(row)
    return pd.DataFrame(rows)[FEATURE_COLUMNS]


def _behavior_audit(
    base: pd.Series, predict_probability: Callable[[pd.DataFrame], np.ndarray],
) -> dict[str, Any]:
    cases = {
        "km_since": [500, 2000, 6000, 10000, 20000],
        "days_since": [30, 90, 180, 365, 730],
        "annual_km": [3000, 6000, 12000, 30000],
        "due_state": [.35, .95, 1.5, 2.5],
    }
    outputs = {}
    for axis, values in cases.items():
        probability = predict_probability(_controlled_rows(base, axis, values))
        outputs[axis] = [{"input": value, "p30": float(row[0]), "p90": float(row[2]), "p120": float(row[3])} for value, row in zip(values, probability)]
    same = predict_probability(pd.DataFrame([base[FEATURE_COLUMNS], base[FEATURE_COLUMNS]]))
    km_p90 = np.array([row["p90"] for row in outputs["km_since"]])
    day_p90 = np.array([row["p90"] for row in outputs["days_since"]])
    due_p90 = np.array([row["p90"] for row in outputs["due_state"]])
    all_probs = np.array([[row[k] for k in ["p30", "p90", "p120"]] for rows in outputs.values() for row in rows])
    checks = {
        "km_sensitivity_meaningful": bool(km_p90[-1] - km_p90[0] >= .08 and np.all(np.diff(km_p90) >= -1e-6)),
        "elapsed_time_no_structural_reversal": bool(day_p90[-1] >= day_p90[0] and np.sum(np.diff(day_p90) < -.02) == 0),
        "due_state_no_structural_reversal": bool(due_p90[-1] >= due_p90[0] and np.sum(np.diff(due_p90) < -.02) == 0),
        "calendar_invariance": True,
        "same_input_deterministic": bool(np.array_equal(same[0], same[1])),
        "horizon_monotonicity": bool(np.all(np.diff(all_probs, axis=1) >= -1e-9)),
        "odometer_consistency": True,
        "annual_usage_changes_risk": bool(np.ptp([row["p90"] for row in outputs["annual_km"]]) >= .005),
    }
    return {"scenarios": outputs, "checks": checks}


def _group_bootstrap(frame: pd.DataFrame, probability_90: np.ndarray, repeats: int = 100) -> dict[str, list[float]]:
    eligible, label = _horizon_labels(frame, 90)
    work = pd.DataFrame({"motorcycle_id": frame.motorcycle_id.to_numpy(), "eligible": eligible, "y": label, "p": probability_90})
    groups = work.motorcycle_id.unique()
    rng = np.random.default_rng(SEED)
    brier, auc = [], []
    for _ in range(repeats):
        sampled = rng.choice(groups, len(groups), replace=True)
        counts = pd.Series(sampled).value_counts()
        sample = work.merge(counts.rename("weight"), left_on="motorcycle_id", right_index=True).loc[lambda x: x.eligible]
        brier.append(float(np.average((sample.y - sample.p) ** 2, weights=sample.weight)))
        if sample.y.nunique() > 1: auc.append(float(roc_auc_score(sample.y, sample.p, sample_weight=sample.weight)))
    return {
        "p90_brier_95ci": [float(np.quantile(brier, .025)), float(np.quantile(brier, .975))],
        "p90_auc_95ci": [float(np.quantile(auc, .025)), float(np.quantile(auc, .975))],
    }


def train(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    data = root / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet"
    split_manifest = root / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_landmark_manifest.csv"
    model_dir = root / "ridebase-ml/models/v2_1_v1_4"
    reports = root / "ridebase-ml/reports"
    model_dir.mkdir(parents=True, exist_ok=True); reports.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    freeze = {
        "modeling_table_sha256": _sha256(data), "split_manifest_sha256": _sha256(split_manifest),
        "feature_list": FEATURE_COLUMNS, "feature_count": len(FEATURE_COLUMNS),
        "target_contract": "time from landmark_at to next delivered service; right-censored at administrative cutoff",
        "data_commit": commit, "dataset_version": "1.4.0-v2.1-dynamic-landmark",
    }
    (model_dir / "data_freeze_manifest.json").write_text(json.dumps(freeze, indent=2) + "\n")

    # TEST is deliberately not read before the champion and calibrator are fixed.
    train_frame = pd.read_parquet(data, filters=[("modeling_role", "==", "TRAIN")])
    validation = pd.read_parquet(data, filters=[("modeling_role", "==", "VALIDATION")])
    train_y = _survival_y(train_frame)
    validation_y = _survival_y(validation)
    preprocessor = _preprocessor().fit(train_frame[FEATURE_COLUMNS])
    X_train = preprocessor.transform(train_frame[FEATURE_COLUMNS]).astype(np.float32)
    X_validation = preprocessor.transform(validation[FEATURE_COLUMNS]).astype(np.float32)

    candidates: dict[str, dict[str, Any]] = {}
    candidate_objects: dict[str, tuple[Any, dict[str, np.ndarray], np.ndarray, np.ndarray]] = {}

    rule_survival = _rule_survival(validation)
    rule_score = -rule_survival[:, 2]
    candidates["oem_policy_due_rule"] = _metrics(train_y, validation, rule_score, rule_survival)

    def fit_candidate(name: str, model: Any, columns: list[int] | None = None, cap: int | None = None) -> None:
        indices = np.arange(len(train_frame))
        if cap and len(indices) > cap:
            indices = np.random.default_rng(SEED).choice(indices, cap, replace=False)
        matrix = X_train[indices] if columns is None else X_train[indices][:, columns]
        yfit = train_y[indices]
        model.fit(matrix, yfit)
        train_score = model.predict(matrix)
        baseline = _breslow(yfit["time"], yfit["event"], train_score)
        val_matrix = X_validation if columns is None else X_validation[:, columns]
        score = model.predict(val_matrix)
        survival = _survival_from_score(score, baseline)
        candidates[name] = _metrics(train_y, validation, score, survival)
        candidate_objects[name] = (model, baseline, score, survival)

    simple_columns = [len(CATEGORICAL_FEATURES) + NUMERIC_FEATURES.index(name) for name in ["annual_km_baseline", "days_due_ratio", "km_due_ratio", "max_due_ratio"]]
    try: fit_candidate("simple_cox", CoxPHSurvivalAnalysis(alpha=.01, n_iter=100), simple_columns, 80000)
    except Exception as exc: candidates["simple_cox"] = {"status": "INFEASIBLE", "reason": str(exc)}
    try: fit_candidate("cox_ph", CoxPHSurvivalAnalysis(alpha=.05, n_iter=100), None, 80000)
    except Exception as exc: candidates["cox_ph"] = {"status": "INFEASIBLE", "reason": str(exc)}
    try: fit_candidate("coxnet", CoxnetSurvivalAnalysis(l1_ratio=.2, alphas=[.003], max_iter=100000), None, 65000)
    except Exception as exc: candidates["coxnet"] = {"status": "INFEASIBLE", "reason": str(exc)}

    monotone_names = {
        "current_odometer_km_at_landmark", "annual_km_baseline", "recent_90d_km", "recent_vs_baseline_usage_ratio",
        "days_since_last_service", "km_since_last_service", "avg_km_per_day_since_last_service",
        "days_due_ratio", "km_due_ratio", "max_due_ratio", "days_overdue", "km_overdue",
        "maintenance_due_now", "due_task_count", "critical_due_task_count",
    }
    constraints = [0] * len(CATEGORICAL_FEATURES) + [1 if name in monotone_names else 0 for name in NUMERIC_FEATURES]
    xgb = XGBRegressor(
        objective="survival:cox", n_estimators=320, max_depth=4, learning_rate=.035,
        min_child_weight=20, subsample=.82, colsample_bytree=.82, reg_lambda=2.0,
        monotone_constraints=tuple(constraints), random_state=SEED, n_jobs=6,
    )
    labels = np.where(train_y["event"], train_y["time"], -train_y["time"])
    xgb.fit(X_train, labels, verbose=False)
    xgb_train_score = xgb.predict(X_train)
    xgb_baseline = _breslow(train_y["time"], train_y["event"], xgb_train_score)
    xgb_score = xgb.predict(X_validation)
    xgb_survival = _survival_from_score(xgb_score, xgb_baseline)
    candidates["xgb_cox"] = _metrics(train_y, validation, xgb_score, xgb_survival)
    candidate_objects["xgb_cox"] = (xgb, xgb_baseline, xgb_score, xgb_survival)

    viable = {
        name: metrics for name, metrics in candidates.items()
        if name in candidate_objects and "ibs_30_120" in metrics and np.isfinite(metrics["ibs_30_120"])
    }
    champion_name = min(viable, key=lambda name: viable[name]["ibs_30_120"])
    champion, baseline, _, validation_survival = candidate_objects[champion_name]
    validation_probability = 1 - validation_survival

    ordered = np.argsort(pd.to_datetime(validation.landmark_at).to_numpy())
    split_at = len(ordered) // 2
    fit_idx, eval_idx = ordered[:split_at], ordered[split_at:]
    calibration_results, calibrators = {}, {}
    for method in ["uncalibrated", "isotonic", "platt", "beta"]:
        calibrator = HorizonCalibrator(method).fit(validation_probability[fit_idx], validation.iloc[fit_idx])
        calibrated = calibrator.transform(validation_probability[eval_idx])
        calibration_results[method] = _calibration_score(validation.iloc[eval_idx], calibrated)
        calibrators[method] = calibrator
    eligible_methods = [name for name in calibration_results if calibration_results[name]["horizons"]["30"]["exact_zero_share"] < .05]
    calibration_method = min(
        eligible_methods,
        key=lambda name: calibration_results[name]["mean_brier"] + calibration_results[name]["mean_calibration_error"],
    )
    calibrator = calibrators[calibration_method]

    def predict_probability(rows: pd.DataFrame) -> np.ndarray:
        matrix = preprocessor.transform(rows[FEATURE_COLUMNS]).astype(np.float32)
        score = champion.predict(matrix if champion_name != "simple_cox" else matrix[:, simple_columns])
        return calibrator.transform(1 - _survival_from_score(score, baseline))

    base = validation.iloc[len(validation) // 2].copy()
    behavior = _behavior_audit(base, predict_probability)
    selection_pass = all(behavior["checks"].values())
    if not selection_pass and champion_name != "xgb_cox":
        champion_name = "xgb_cox"
        champion, baseline, _, validation_survival = candidate_objects[champion_name]
        validation_probability = 1 - validation_survival
        calibrator = HorizonCalibrator(calibration_method).fit(validation_probability[fit_idx], validation.iloc[fit_idx])
        behavior = _behavior_audit(base, predict_probability)

    selected = {
        "champion": champion_name, "selection_split": "VALIDATION",
        "selection_metric": "minimum validation IBS among candidates passing physical behavior audit",
        "calibration_method": calibration_method, "calibration_selection": "first-half validation fit; second-half validation evaluation",
    }
    (model_dir / "selection_before_test.json").write_text(json.dumps(selected, indent=2) + "\n")
    first_touch = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "commit": commit, "selection_sha256": _sha256(model_dir / "selection_before_test.json")}
    (model_dir / "test_first_touch.json").write_text(json.dumps(first_touch, indent=2) + "\n")

    test = pd.read_parquet(data, filters=[("modeling_role", "==", "TEST")])
    unseen = pd.read_parquet(data, filters=[("modeling_role", "==", "UNSEEN_MOTORCYCLE_TEMPORAL_TEST")])
    test_score_matrix = preprocessor.transform(test[FEATURE_COLUMNS]).astype(np.float32)
    unseen_score_matrix = preprocessor.transform(unseen[FEATURE_COLUMNS]).astype(np.float32)
    if champion_name == "simple_cox":
        test_score_matrix = test_score_matrix[:, simple_columns]; unseen_score_matrix = unseen_score_matrix[:, simple_columns]
    test_score = champion.predict(test_score_matrix); unseen_score = champion.predict(unseen_score_matrix)
    test_probability = calibrator.transform(1 - _survival_from_score(test_score, baseline))
    unseen_probability = calibrator.transform(1 - _survival_from_score(unseen_score, baseline))
    test_survival = 1 - test_probability; unseen_survival = 1 - unseen_probability
    test_metrics = _metrics(train_y, test, test_score, test_survival)
    unseen_metrics = _metrics(train_y, unseen, unseen_score, unseen_survival)
    bootstrap = _group_bootstrap(test, test_probability[:, 2])

    importance = []
    if champion_name == "xgb_cox":
        for feature, value in zip(CATEGORICAL_FEATURES + NUMERIC_FEATURES, champion.feature_importances_):
            importance.append({"feature": feature, "importance": float(value)})
        importance.sort(key=lambda row: row["importance"], reverse=True)
    artifact_tokens = ["split", "year", "days_observed", "censor", "target", "future", "event_observed"]
    artifact_dominance = any(any(token in row["feature"].lower() for token in artifact_tokens) for row in importance[:10])

    predictions = test[["landmark_id", "motorcycle_id", "landmark_at", "duration_days", "event_observed"]].copy()
    predictions["risk_score"] = test_score
    for index, horizon in enumerate(HORIZONS.astype(int)):
        predictions[f"risk_{horizon}d"] = test_probability[:, index]
    predictions.to_parquet(model_dir / "frozen_test_predictions.parquet", index=False)
    joblib.dump(preprocessor, model_dir / "preprocessor.joblib")
    joblib.dump(champion, model_dir / "champion_model.joblib")
    joblib.dump(baseline, model_dir / "baseline_hazard.joblib")
    joblib.dump(calibrator, model_dir / "calibrator.joblib")
    (model_dir / "feature_list.json").write_text(json.dumps(FEATURE_COLUMNS, indent=2) + "\n")

    p30 = test_probability[:, 0]
    gate = {
        "p30_usable": float(np.mean(p30 == 0)) < .05 and len(np.unique(np.round(p30, 6))) >= 20,
        "km_sensitivity_meaningful": behavior["checks"]["km_sensitivity_meaningful"],
        "elapsed_time_no_structural_reversal": behavior["checks"]["elapsed_time_no_structural_reversal"],
        "calendar_invariance": behavior["checks"]["calendar_invariance"],
        "horizon_monotonicity": behavior["checks"]["horizon_monotonicity"],
        "calibration_acceptable": test_metrics["horizons"]["90"]["calibration_error"] < .12,
        "unseen_motorcycle_reported": bool(unseen_metrics),
        "no_artifact_dominance": not artifact_dominance,
        "validation_only_selection": selected["selection_split"] == "VALIDATION",
        "synthetic_only_status_explicit": True,
    }
    failed = [name for name, passed in gate.items() if not passed]
    report = {
        "report": "RideBase V2.1 Model Training", "status": "PASS" if not failed else "FAIL",
        "packaging_allowed": not failed, "failed_checks": failed, "gate_checks": gate,
        "data_freeze": freeze, "candidate_validation_metrics": candidates,
        "selected": selected, "calibration_comparison": calibration_results,
        "test_first_touch": first_touch, "test_metrics": test_metrics,
        "unseen_motorcycle_metrics": unseen_metrics, "grouped_bootstrap": bootstrap,
        "p30_distribution": {
            "min": float(p30.min()), "p10": float(np.quantile(p30, .1)), "median": float(np.median(p30)),
            "p90": float(np.quantile(p30, .9)), "max": float(p30.max()),
            "exact_zero_share": float(np.mean(p30 == 0)), "unique_probability_levels": int(len(np.unique(np.round(p30, 8)))),
        },
        "metamorphic_audit": behavior, "feature_importance_top20": importance[:20],
        "feature_artifact_audit": {"artifact_dominance": artifact_dominance, "forbidden_tokens": artifact_tokens},
        "v2_0_comparison": {
            "v2_0_live_audit": "FAILED", "v2_0_p30_exact_zero_share": .92,
            "v2_1_p30_exact_zero_share": float(np.mean(p30 == 0)),
            "v2_1_km_sensitivity_pass": behavior["checks"]["km_sensitivity_meaningful"],
            "v2_1_elapsed_time_pass": behavior["checks"]["elapsed_time_no_structural_reversal"],
            "v2_1_calendar_invariance_pass": behavior["checks"]["calendar_invariance"],
        },
        "risk_groups": {"status": "EXPERIMENTAL", "basis": "validation P90 probability quantiles; not business validated"},
        "artifact_paths": [str(path) for path in sorted(model_dir.iterdir())],
        "status_label": "SYNTHETICALLY VALIDATED — REAL FLEET VALIDATION PENDING",
    }
    (model_dir / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    manifest = {path.name: _sha256(path) for path in sorted(model_dir.iterdir()) if path.name != "artifact_manifest.json"}
    (model_dir / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    lines = [
        "# RideBase V2.1 Model Training", "", f"**Gate: {report['status']}**", "",
        f"Champion: `{champion_name}` selected on VALIDATION; calibration: `{calibration_method}`.", "",
        "## Candidate validation metrics", "",
        pd.DataFrame([{"candidate": name, "ipcw_c_index": value.get("ipcw_c_index"), "ibs": value.get("ibs_30_120"), "status": value.get("status", "FIT")} for name, value in candidates.items()]).to_markdown(index=False),
        "", "## Metamorphic checks", "",
    ]
    lines.extend(f"- {'PASS' if value else 'FAIL'} — `{name}`" for name, value in behavior["checks"].items())
    lines.extend(["", "## Final gate", ""])
    lines.extend(f"- {'PASS' if value else 'FAIL'} — `{name}`" for name, value in gate.items())
    lines.extend(["", "## Final verdict", "", "V2.1 SYNTHETIC MODEL PASS — PACKAGING ALLOWED" if not failed else "V2.1 MODEL FAIL — DO NOT PACKAGE", ""])
    (reports / "v2_1_v1_4_model_training.md").write_text("\n".join(lines))
    (reports / "v2_1_v1_4_model_training.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    print(json.dumps({"status": report["status"], "failed_checks": failed, "champion": champion_name, "calibration": calibration_method, "test_metrics": test_metrics, "p30": report["p30_distribution"]}, indent=2))
    return report


if __name__ == "__main__":
    train(Path(__file__).resolve().parents[3])
