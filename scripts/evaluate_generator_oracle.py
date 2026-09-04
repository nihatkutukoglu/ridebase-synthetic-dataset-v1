"""Phase 5: True Hazard / Bayes-Ceiling Proxy (GENERATOR_ORACLE).

Evaluates how well the synthetic generator's own true conditional hazard / propensity
at landmark date (Tier H) ranks and predicts realized future service returns on out-of-sample VALIDATION.
Answers: 'Even with perfect access to the synthetic world's true hidden hazard, how predictable are realized events?'
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, brier_score_loss
from sksurv.metrics import (
    concordance_index_censored,
    concordance_index_ipcw,
)

ROOT = Path(__file__).resolve().parents[1]
ORACLE_DATASET_PATH = ROOT / "ridebase-ml/derived_outputs/signal_ceiling/oracle_study_dataset.parquet"
REPORT_JSON = ROOT / "ridebase-ml/reports/signal_ceiling_generator_oracle.json"
REPORT_MD = ROOT / "ridebase-ml/reports/signal_ceiling_generator_oracle.md"

HORIZONS = [30, 60, 90, 120]


def _survival_y(frame: pd.DataFrame) -> np.ndarray:
    return np.array(
        list(zip(frame["event_observed"].astype(bool), frame["duration_days"].astype(float))),
        dtype=[("event", "?"), ("time", "<f8")],
    )


def run_generator_oracle_evaluation() -> dict[str, Any]:
    print("Loading oracle dataset for generator oracle evaluation...")
    df = pd.read_parquet(ORACLE_DATASET_PATH)

    train_df = df[df["modeling_role"] == "TRAIN"].copy()
    val_df = df[df["modeling_role"] == "VALIDATION"].copy()

    train_y = _survival_y(train_df)
    val_y = _survival_y(val_df)

    # True hazard score: higher hazard = higher risk of early return
    true_hazard = val_df["oracle_true_hazard_instantaneous"].to_numpy(dtype=float)
    true_p30 = val_df["oracle_true_propensity_proxy"].to_numpy(dtype=float)

    # 1. Concordance indices of the Generator Oracle
    tau = min(365.0, float(np.max(train_y["time"])) - 1e-6, float(np.max(val_y["time"])) - 1e-6)
    ipcw_c = float(concordance_index_ipcw(train_y, val_y, true_hazard, tau=tau)[0])
    harrell_c = float(concordance_index_censored(val_y["event"], val_y["time"], true_hazard)[0])

    print(f"GENERATOR_ORACLE IPCW C-Index: {ipcw_c:.6f}")
    print(f"GENERATOR_ORACLE Harrell C-Index: {harrell_c:.6f}")

    # 2. Binary horizon AUCs and Briers
    horizon_metrics = {}
    for h in HORIZONS:
        eligible = (val_df["duration_days"] >= h) | (val_df["event_observed"] == 1)
        y_h = ((val_df["duration_days"] <= h) & (val_df["event_observed"] == 1)).to_numpy(int)[eligible]
        score_h = true_hazard[eligible]
        prob_h = 1.0 - np.exp(-(h / 3.0) * score_h)

        auc = float(roc_auc_score(y_h, score_h)) if len(np.unique(y_h)) > 1 else 0.5
        brier = float(brier_score_loss(y_h, prob_h))
        base_rate = float(y_h.mean())

        horizon_metrics[str(h)] = {
            "eligible_samples": int(eligible.sum()),
            "empirical_event_rate": round(base_rate, 4),
            "roc_auc": round(auc, 4),
            "brier_score": round(brier, 4),
        }
        print(f"  Horizon {h:3d}d: AUC = {auc:.4f}, Brier = {brier:.4f}, Base Rate = {base_rate:.4f}")

    # 3. Decile Analysis on 90d return risk
    val_df_eligible = val_df[(val_df["duration_days"] >= 90) | (val_df["event_observed"] == 1)].copy()
    val_df_eligible["event_90d"] = ((val_df_eligible["duration_days"] <= 90) & (val_df_eligible["event_observed"] == 1)).astype(int)
    val_df_eligible["decile"] = pd.qcut(val_df_eligible["oracle_true_hazard_instantaneous"], q=10, labels=False, duplicates="drop")

    decile_summary = []
    for dec in sorted(val_df_eligible["decile"].unique()):
        sub = val_df_eligible[val_df_eligible["decile"] == dec]
        decile_summary.append({
            "decile": int(dec) + 1,
            "count": len(sub),
            "min_hazard": round(float(sub["oracle_true_hazard_instantaneous"].min()), 6),
            "max_hazard": round(float(sub["oracle_true_hazard_instantaneous"].max()), 6),
            "mean_propensity_90d": round(float((1.0 - np.exp(-30.0 * sub["oracle_true_hazard_instantaneous"])).mean()), 4),
            "empirical_event_rate_90d": round(float(sub["event_90d"].mean()), 4),
        })

    # Temporal slice evaluation
    val_df["landmark_month"] = pd.to_datetime(val_df["landmark_at"]).dt.month
    slices = {
        "slice_jul_aug": val_df["landmark_month"].isin([7, 8]),
        "slice_sep_oct": val_df["landmark_month"].isin([9, 10]),
        "slice_nov_dec": val_df["landmark_month"].isin([11, 12]),
    }
    slice_ipcw = {}
    for s_name, s_mask in slices.items():
        s_idx = np.where(s_mask)[0]
        s_res = concordance_index_ipcw(train_y, val_y[s_idx], true_hazard[s_idx], tau=tau)[0]
        slice_ipcw[s_name] = round(float(s_res), 4)

    results = {
        "study": "RIDEBASE_V1_5_GENERATOR_ORACLE",
        "sample_size_val": len(val_df),
        "overall_metrics": {
            "ipcw_c_index": round(ipcw_c, 6),
            "harrell_c_index": round(harrell_c, 6),
            "mean_horizon_auc": round(float(np.mean([m["roc_auc"] for m in horizon_metrics.values()])), 4),
            "horizon_metrics": horizon_metrics,
        },
        "temporal_slice_ipcw_c": slice_ipcw,
        "decile_calibration_table": decile_summary,
    }

    REPORT_JSON.write_text(json.dumps(results, indent=2))

    # Markdown Report
    md_lines = [
        "# RideBase V1.5 Generator Oracle & Bayes-Ceiling Report",
        "",
        "## 1. Executive Summary",
        "The **GENERATOR_ORACLE** evaluates the theoretical Bayes ranking ceiling of the V1.5 synthetic world. It uses the exact instantaneous conditional hazard computed by the synthetic event generator at the landmark date without any estimation error or future outcome leakage.",
        "",
        "### Benchmark Metrics",
        f"- **Generator Oracle IPCW C-Index**: `{ipcw_c:.6f}`",
        f"- **Generator Oracle Harrell C-Index**: `{harrell_c:.6f}`",
        f"- **Mean Dynamic Horizon AUC**: `{results['overall_metrics']['mean_horizon_auc']:.4f}`",
        "",
        "### Horizon Discriminative Performance",
        "| Horizon | Eligible Samples | Empirical Base Rate | Generator Oracle ROC AUC | Brier Score |",
        "|:---:|:---:|:---:|:---:|:---:|",
    ]
    for h, data in horizon_metrics.items():
        md_lines.append(f"| **{h}d** | {data['eligible_samples']} | {data['empirical_event_rate']:.4f} | **{data['roc_auc']:.4f}** | {data['brier_score']:.4f} |")

    md_lines.extend([
        "",
        "### Decile Calibration (90-day Empirical Event Rates)",
        "| Decile | Min Hazard | Max Hazard | Mean Theoretical Risk | Empirical 90d Event Rate |",
        "|:---:|:---:|:---:|:---:|:---:|",
    ])
    for d in decile_summary:
        md_lines.append(f"| **D{d['decile']}** | {d['min_hazard']:.5f} | {d['max_hazard']:.5f} | {d['mean_propensity_90d']:.4f} | **{d['empirical_event_rate_90d']:.4f}** |")

    md_lines.extend([
        "",
        "### Key Finding",
        f"Even with perfect oracle knowledge of the true instantaneous hazard and latent behavioral parameters, the C-index in the synthetic world is **~{ipcw_c:.3f}**. This demonstrates that the synthetic event generation process possesses a substantial amount of **irreducible stochastic noise** (Bernoulli trial randomness at each 3-day step).",
    ])

    REPORT_MD.write_text("\n".join(md_lines))
    print(f"Generator Oracle report written to {REPORT_JSON} and {REPORT_MD}.")
    return results


if __name__ == "__main__":
    t0 = time.perf_counter()
    run_generator_oracle_evaluation()
    print(f"Phase 5 completed in {time.perf_counter() - t0:.2f}s.")
