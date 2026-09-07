#!/usr/bin/env python3
"""Phase 7 — research vs packaged-serving PREDICTOR parity.

Feature parity is necessary but not sufficient: identical inputs can still diverge
downstream through preprocessing, calibration, masking or threshold application.
This compares the two paths end to end, on predictions, at scale:

    research path : research feature matrix -> frozen model -> calibrator -> mask
    serving path  : motorcycle_id + landmark -> history adapter -> 277 features
                    -> V3TaskPredictor.predict_product()

and reports probability deltas, ranking mismatches and threshold mismatches over
every one of the 44 labels.

Tolerance: 1e-9 on probabilities. The two paths run the *same* fitted objects in
the same process, so any nonzero delta is float-ordering noise, not model drift;
a real divergence would show up orders of magnitude above this.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ridebase-ml"))

import numpy as np
import pandas as pd

from ridebase_ml.v2_1.adapters.sqlite import SyntheticSQLiteSourceAdapter
from ridebase_ml.v3 import experiment as E
from ridebase_ml.v3 import serving as S
from ridebase_ml.v3.serving import straddling_history_service
from ridebase_ml.v3.predictor import V3TaskPredictor

MODELS = ROOT / "ridebase-ml/models/v3_research"
STORE = ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite"
REPORTS = ROOT / "reports/v3_product"
TOLERANCE = 1e-9


def main(rows: int, seed: int) -> int:
    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    pred = V3TaskPredictor.load(MODELS)
    adapter = SyntheticSQLiteSourceAdapter(STORE)
    meta, feats = prep.ds.meta, prep.ds.features

    rng = np.random.default_rng(seed)
    idx = rng.choice(len(meta), min(rows, len(meta)), replace=False)

    # ---- research path: the frozen matrix straight through the frozen model ----
    t0 = time.perf_counter()
    app_research = pred.applicability(feats.iloc[idx], meta["motorcycle_id"].iloc[idx])
    p_research = pred.predict_proba(feats.iloc[idx], app_research)
    research_ms = (time.perf_counter() - t0) * 1000

    # ---- serving path: rebuild every feature vector from history, then predict ----
    built, cover, build_ms, straddling = [], [], [], []
    for i in idx:
        m = meta.iloc[i]
        t = time.perf_counter()
        fv = S.build_v3_features(m.motorcycle_id, m.landmark_at.date(), adapter,
                                 labels, pred.feature_cols)
        build_ms.append((time.perf_counter() - t) * 1000)
        built.append(fv.features)
        cover.append(fv.coverage)
        straddling.append(bool(fv.provenance.get("straddling_history_service")))
    straddling = np.asarray(straddling)
    X_serving = pd.DataFrame(built, columns=pred.feature_cols)

    t0 = time.perf_counter()
    app_serving = pred.applicability(X_serving, meta["motorcycle_id"].iloc[idx])
    p_serving = pred.predict_proba(X_serving, app_serving)
    serving_ms = (time.perf_counter() - t0) * 1000

    # ---------------------------------------------------------------- compare
    delta = np.abs(p_research - p_serving)
    thr = pred.thresholds[None, :]
    bin_r, bin_s = (p_research >= thr), (p_serving >= thr)
    threshold_mismatch = int((bin_r != bin_s).sum())

    rank_r = np.argsort(-p_research, axis=1, kind="stable")
    rank_s = np.argsort(-p_serving, axis=1, kind="stable")
    top3_mismatch = int(sum(list(a[:3]) != list(b[:3]) for a, b in zip(rank_r, rank_s)))
    top5_mismatch = int(sum(list(a[:5]) != list(b[:5]) for a, b in zip(rank_r, rank_s)))
    full_rank_mismatch = int(sum(not np.array_equal(a, b) for a, b in zip(rank_r, rank_s)))

    # feature-level parity, restated here so one artifact carries both
    feat_mismatch = 0
    feat_mismatch_rows: set[int] = set()
    for pos, i in enumerate(idx):
        for col in pred.feature_cols:
            a, b = feats.iloc[i][col], X_serving.iloc[pos][col]
            if isinstance(a, str) or isinstance(b, str):
                if str(a) != str(b):
                    feat_mismatch += 1
                    feat_mismatch_rows.add(pos)
            else:
                fa = float(a) if a is not None else np.nan
                fb = float(b) if b is not None else np.nan
                if not ((np.isnan(fa) and np.isnan(fb)) or abs(fa - fb) <= 1e-6):
                    feat_mismatch += 1
                    feat_mismatch_rows.add(pos)

    n, L = p_research.shape
    out = {
        "rows_tested": int(n),
        "labels": int(L),
        "prediction_cells_compared": int(n * L),
        "feature_cells_compared": int(n * len(pred.feature_cols)),
        "feature_mismatches": feat_mismatch,
        "max_probability_delta": float(delta.max()),
        "mean_probability_delta": float(delta.mean()),
        "cells_over_tolerance": int((delta > TOLERANCE).sum()),
        "tolerance": TOLERANCE,
        "top3_ranking_mismatches": top3_mismatch,
        "top5_ranking_mismatches": top5_mismatch,
        "full_ranking_mismatches": full_rank_mismatch,
        "threshold_mismatches": threshold_mismatch,
        "feature_coverage_min": float(np.min(cover)),
        "feature_coverage_mean": float(np.mean(cover)),
        "history_build_ms": {"p50": float(np.percentile(build_ms, 50)),
                             "p95": float(np.percentile(build_ms, 95)),
                             "mean": float(np.mean(build_ms))},
        "batch_inference_ms": {"research": round(research_ms, 1),
                               "serving": round(serving_ms, 1)},
        "seed": seed,
    }
    # Gate semantics. Every remaining divergence must be confined to landmarks the
    # serving layer itself flags as sitting inside a midnight-straddling service --
    # a known V2.1 history-builder property that V3 cannot fix without mutating a
    # frozen production contract, and that V3 reports in its own warnings and
    # provenance. Drift on any UNFLAGGED landmark is a real failure.
    over_tol_rows = set(np.flatnonzero((delta > TOLERANCE).any(axis=1)).tolist())
    rank_rows = {i for i, (a, b) in enumerate(zip(rank_r, rank_s))
                 if not np.array_equal(a, b)}
    thr_rows = set(np.flatnonzero((bin_r != bin_s).any(axis=1)).tolist())
    diverging = feat_mismatch_rows | over_tol_rows | rank_rows | thr_rows
    flagged = set(np.flatnonzero(straddling).tolist())
    unexplained = sorted(diverging - flagged)

    out["landmarks_flagged_straddling"] = int(straddling.sum())
    out["landmarks_with_any_divergence"] = len(diverging)
    out["divergence_all_explained_by_straddle"] = not unexplained
    out["unexplained_divergent_rows"] = len(unexplained)
    out["unexplained_examples"] = [
        {"motorcycle_id": str(meta.iloc[idx[i]]["motorcycle_id"]),
         "landmark": str(meta.iloc[idx[i]]["landmark_at"].date())}
        for i in unexplained[:5]]

    clean = ~straddling
    if clean.any():
        out["unflagged_subset"] = {
            "rows": int(clean.sum()),
            "max_probability_delta": float(delta[clean].max()),
            "ranking_mismatches": len(rank_rows & set(np.flatnonzero(clean).tolist())),
            "threshold_mismatches": int((bin_r[clean] != bin_s[clean]).sum()),
        }
    out["passed"] = not unexplained

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "07_predictor_parity.json").write_text(
        json.dumps(out, indent=2) + "\n")
    for k, v in out.items():
        print(f"  {k:32s} {v}")
    print("\nPREDICTOR PARITY:", "PASS" if out["passed"] else "FAIL")
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=500)
    ap.add_argument("--seed", type=int, default=20260907)
    a = ap.parse_args()
    raise SystemExit(main(a.rows, a.seed))
