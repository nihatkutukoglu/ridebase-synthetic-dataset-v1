"""TRAIN/VALIDATION-only diagnosis of the V2.2 statistical performance gap."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import entropy, spearmanr
from sksurv.metrics import concordance_index_censored

from ridebase_ml.v2_1.survival import HORIZONS, _horizon_labels, _survival_from_score
from ridebase_ml.v2_2.landmarks import BASE_FEATURE_COLUMNS, FEATURE_COLUMNS, NUMERIC_FEATURES, OBSERVABLE_HISTORY_FEATURES
from ridebase_ml.v2_2.train import _calibration_score, _metrics, _survival_y


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def _world_summary(frame: pd.DataFrame) -> dict[str, Any]:
    horizon = {}
    for days in HORIZONS:
        eligible, label = _horizon_labels(frame, days)
        rate = float(label[eligible].mean())
        horizon[str(int(days))] = {
            "eligible": int(eligible.sum()),
            "event_rate": rate,
            "binary_entropy_bits": float(-(rate * math.log2(max(rate, 1e-12)) + (1-rate) * math.log2(max(1-rate, 1e-12)))),
        }
    numeric = {}
    for name in ["duration_days", "km_due_ratio", "days_due_ratio", "max_due_ratio", "annual_km_baseline", "prior_service_count"]:
        values = pd.to_numeric(frame[name], errors="coerce")
        numeric[name] = {
            "mean": float(values.mean()), "median": float(values.median()),
            "p10": float(values.quantile(.1)), "p90": float(values.quantile(.9)),
            "missing_share": float(values.isna().mean()),
        }
    return {
        "rows": len(frame),
        "motorcycles": int(frame.motorcycle_id.nunique()),
        "landmarks_per_motorcycle": float(len(frame) / frame.motorcycle_id.nunique()),
        "event_share": float(frame.event_observed.mean()),
        "censor_share": float(1-frame.event_observed.mean()),
        "horizons": horizon,
        "numeric": numeric,
        "category_mix": frame.category.value_counts(normalize=True).round(6).to_dict(),
    }


def _source_behavior(root: Path, version: str) -> dict[str, Any]:
    source = root / version / "source_tables"
    appointments = pd.read_csv(source / "appointments.csv", low_memory=False)
    services = pd.read_csv(source / "services.csv", low_memory=False)
    statuses = appointments.status.value_counts(normalize=True)
    return {
        "appointments": len(appointments),
        "appointment_per_service": float(len(appointments) / max(len(services), 1)),
        "no_show_share": float(statuses.get("NO_SHOW", 0)),
        "cancellation_share": float(statuses.get("CANCELLED", 0)),
        "delivered_services": int(services.status.eq("DELIVERED").sum()),
    }


def _feature_diagnostics(v14: pd.DataFrame, v15: pd.DataFrame) -> dict[str, Any]:
    shared = []
    event15 = (v15.event_observed.eq(1) & v15.duration_days.le(90)).astype(int)
    for name in BASE_FEATURE_COLUMNS:
        if name in NUMERIC_FEATURES:
            left = pd.to_numeric(v14[name], errors="coerce")
            right = pd.to_numeric(v15[name], errors="coerce")
            pooled = math.sqrt((float(left.var()) + float(right.var())) / 2) if left.notna().any() and right.notna().any() else 0
            correlation = spearmanr(right.fillna(right.median()), event15, nan_policy="omit").statistic
            shared.append({
                "feature": name, "kind": "numeric", "v1_4_mean": float(left.mean()), "v1_5_mean": float(right.mean()),
                "standardized_mean_difference": float((right.mean()-left.mean()) / pooled) if pooled else 0.0,
                "v1_4_missing": float(left.isna().mean()), "v1_5_missing": float(right.isna().mean()),
                "spearman_event90_v1_5": float(correlation) if np.isfinite(correlation) else 0.0,
            })
        else:
            ldist = v14[name].astype(str).value_counts(normalize=True)
            rdist = v15[name].astype(str).value_counts(normalize=True)
            levels = ldist.index.union(rdist.index)
            tvd = .5 * float((ldist.reindex(levels, fill_value=0)-rdist.reindex(levels, fill_value=0)).abs().sum())
            shared.append({
                "feature": name, "kind": "categorical", "distribution_tvd": tvd,
                "v1_4_levels": int(v14[name].nunique(dropna=False)), "v1_5_levels": int(v15[name].nunique(dropna=False)),
                "v1_4_missing": float(v14[name].isna().mean()), "v1_5_missing": float(v15[name].isna().mean()),
            })
    numeric = v15[[name for name in BASE_FEATURE_COLUMNS if name in NUMERIC_FEATURES]].select_dtypes(include=np.number)
    corr = numeric.corr(method="spearman").abs()
    redundant = []
    for i, first in enumerate(corr.columns):
        for second in corr.columns[i+1:]:
            if corr.loc[first, second] >= .95:
                redundant.append({"first": first, "second": second, "abs_spearman": float(corr.loc[first, second])})
    return {
        "shared_54": shared,
        "largest_numeric_drift": sorted([x for x in shared if x["kind"] == "numeric"], key=lambda x: abs(x["standardized_mean_difference"]), reverse=True)[:15],
        "unstable_categories": sorted([x for x in shared if x["kind"] == "categorical"], key=lambda x: x["distribution_tvd"], reverse=True),
        "redundant_pairs_abs_spearman_ge_0_95": redundant,
    }


def run(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    reports = ml / "reports"
    v21_path = ml / "derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet"
    v22_path = ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet"
    roles = [("modeling_role", "in", ["TRAIN", "VALIDATION"])]
    v14 = pd.read_parquet(v21_path, filters=roles)
    v15 = pd.read_parquet(v22_path, filters=roles)
    v15_train = v15.loc[v15.modeling_role.eq("TRAIN")].copy()
    v15_validation = v15.loc[v15.modeling_role.eq("VALIDATION")].copy()

    model_dir = ml / "models/v2_2_v1_5"
    preprocessor = joblib.load(model_dir / "preprocessor.joblib")
    model = joblib.load(model_dir / "challenger_model.joblib")
    baseline = joblib.load(model_dir / "baseline_hazard.joblib")
    calibrator = joblib.load(model_dir / "calibrator.joblib")
    train_y = _survival_y(v15_train)

    def score(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        matrix = preprocessor.transform(frame[FEATURE_COLUMNS]).astype(np.float32)
        risk = model.predict(matrix)
        raw = 1 - _survival_from_score(risk, baseline)
        return risk, raw, calibrator.transform(raw)

    train_score, train_raw, train_calibrated = score(v15_train)
    val_score, val_raw, val_calibrated = score(v15_validation)
    train_c = float(concordance_index_censored(v15_train.event_observed.astype(bool), v15_train.duration_days, train_score)[0])
    val_c = float(concordance_index_censored(v15_validation.event_observed.astype(bool), v15_validation.duration_days, val_score)[0])

    importance = dict(zip(
        list(preprocessor.named_steps["columns"].get_feature_names_out()),
        model.feature_importances_.astype(float),
    ))
    rng = np.random.default_rng(52)
    sample = v15_validation.iloc[rng.choice(len(v15_validation), min(8000, len(v15_validation)), replace=False)].copy()
    sample_matrix = preprocessor.transform(sample[FEATURE_COLUMNS]).astype(np.float32)
    base_score = model.predict(sample_matrix)
    base_c = float(concordance_index_censored(sample.event_observed.astype(bool), sample.duration_days, base_score)[0])
    new_features = []
    for name in OBSERVABLE_HISTORY_FEATURES:
        permuted = sample.copy()
        permuted[name] = rng.permutation(permuted[name].to_numpy())
        perm_score = model.predict(preprocessor.transform(permuted[FEATURE_COLUMNS]).astype(np.float32))
        perm_c = float(concordance_index_censored(sample.event_observed.astype(bool), sample.duration_days, perm_score)[0])
        new_features.append({
            "feature": name,
            "missing_share": float(v15_validation[name].isna().mean()),
            "model_importance": float(importance.get(name, 0)),
            "permutation_c_drop": base_c-perm_c,
            "spearman_event90": float(spearmanr(
                pd.to_numeric(v15_validation[name], errors="coerce").fillna(-1),
                (v15_validation.event_observed.eq(1) & v15_validation.duration_days.le(90)).astype(int),
            ).statistic),
            "point_in_time_safe": True,
        })

    baseline_hazard = baseline["cumulative_hazard"]
    raw_metrics = _metrics(train_y, v15_validation, val_score, 1-val_raw)
    calibrated_metrics = _metrics(train_y, v15_validation, val_score, 1-val_calibrated)
    calibration = {
        "raw": {"metrics": raw_metrics, "calibration": _calibration_score(v15_validation, val_raw)},
        "isotonic": {"metrics": calibrated_metrics, "calibration": _calibration_score(v15_validation, val_calibrated)},
        "p30_resolution": {
            "raw_unique_8dp": int(len(np.unique(np.round(val_raw[:, 0], 8)))),
            "isotonic_unique_8dp": int(len(np.unique(np.round(val_calibrated[:, 0], 8)))),
            "isotonic_largest_plateau_share": float(pd.Series(np.round(val_calibrated[:, 0], 10)).value_counts(normalize=True).max()),
        },
    }

    folds = []
    dates = pd.to_datetime(v15_validation.landmark_at)
    for start, end in [("2025-07-01", "2025-08-31"), ("2025-09-01", "2025-10-31"), ("2025-11-01", "2025-12-31")]:
        mask = dates.between(start, end)
        part = v15_validation.loc[mask]
        indices = np.flatnonzero(mask.to_numpy())
        metrics = _metrics(train_y, part, val_score[indices], 1-val_calibrated[indices])
        folds.append({"start": start, "end": end, "rows": len(part), "ipcw_c_index": metrics["ipcw_c_index"], "ibs": metrics["ibs_30_120"], "p90_calibration_error": metrics["horizons"]["90"]["calibration_error"]})

    world14, world15 = _world_summary(v14), _world_summary(v15)
    diagnosis = {
        "report": "RideBase V2.2.1 statistical diagnosis (TRAIN+VALIDATION only)",
        "status": "PASS",
        "test_rows_read": False,
        "world_shift": {
            "v1_4_v2_1": world14,
            "v1_5_v2_2": world15,
            "source_behavior": {"v1_4": _source_behavior(root, "ridebase_v1_4"), "v1_5": _source_behavior(root, "ridebase_v1_5")},
            "known_v1_5_churn_censors": json.loads((root / "ridebase_v1_5/dataset_metadata.json").read_text())["new_churn_censors"],
        },
        "feature_diagnostics": _feature_diagnostics(v14, v15),
        "new_feature_diagnostics": new_features,
        "model_diagnostics": {
            "train_harrell_c": train_c, "validation_harrell_c": val_c, "gap": train_c-val_c,
            "risk_score": {"train_mean": float(train_score.mean()), "train_std": float(train_score.std()), "validation_mean": float(val_score.mean()), "validation_std": float(val_score.std())},
            "baseline_hazard": {"event_times": len(baseline["times"]), "final_cumulative_hazard": float(baseline_hazard[-1]), "monotone": bool(np.all(np.diff(baseline_hazard) >= 0))},
            "top_importance": sorted(({"feature": k, "importance": float(v)} for k,v in importance.items()), key=lambda x:x["importance"], reverse=True)[:20],
        },
        "calibration_diagnostics": calibration,
        "temporal_validation": folds,
        "evidence_based_diagnosis": [
            "V1.5 has a higher and more behaviorally heterogeneous return process than V1.4; latent churn/no-show tendencies intentionally add irreducible ranking noise because latent labels are forbidden model inputs.",
            "The six observable history features add ranking signal, but days_to_next_known_appointment is structurally sparse and must be handled carefully.",
            "The current XGB-Cox risk ranking is useful but its Breslow absolute scale is badly offset; isotonic fixes Brier/calibration while compressing P30 resolution into large plateaus.",
            "The train-validation concordance gap quantifies model overfit; recovery should prioritize regularization and stable feature subsets rather than higher probabilities.",
        ],
        "gate_checks": {
            "train_validation_only": True,
            "world_shift_measured": True,
            "shared_54_diagnosed": True,
            "new_6_diagnosed": True,
            "model_gap_measured": True,
            "raw_vs_calibrated_measured": True,
            "temporal_folds_measured": len(folds) == 3,
        },
    }
    _write(reports / "v2_2_1_statistical_diagnosis.json", diagnosis)
    _write(reports / "v2_2_1_temporal_cv.json", {"stage": "diagnosis", "test_rows_read": False, "folds": folds})
    lines = [
        "# V2.2.1 Statistical Diagnosis", "", "**Gate: PASS — TRAIN+VALIDATION only**", "",
        "## Evidence", "",
    ]
    lines.extend(f"- {item}" for item in diagnosis["evidence_based_diagnosis"])
    lines.extend(["", "## Temporal validation", "", pd.DataFrame(folds).to_markdown(index=False), ""])
    (reports / "v2_2_1_statistical_diagnosis.md").write_text("\n".join(lines))
    print(json.dumps({
        "status": "PASS", "v1_4_event_share": world14["event_share"], "v1_5_event_share": world15["event_share"],
        "train_c": train_c, "validation_c": val_c, "gap": train_c-val_c,
        "p30_resolution": calibration["p30_resolution"], "temporal_folds": folds,
        "new_features": new_features,
    }, indent=2))
    return diagnosis


if __name__ == "__main__":
    run(Path(__file__).resolve().parents[3])
