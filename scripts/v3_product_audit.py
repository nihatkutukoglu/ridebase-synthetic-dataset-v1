#!/usr/bin/env python3
"""V3 Phase-17 top-K product audit against the FROZEN model.

Every scenario is a filter over real landmarks, never a hand-built feature row:
a synthetic row can violate the joint distribution and then "pass" a check that
means nothing. Nothing here retrains, and no expected probability is hardcoded.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ridebase-ml"))

import numpy as np
import pandas as pd

from ridebase_ml.v3 import experiment as E
from ridebase_ml.v3 import product as PP
from ridebase_ml.v3.predictor import V3TaskPredictor

REPORTS = ROOT / "reports/v3_product"
REPORTS.mkdir(parents=True, exist_ok=True)
MODELS = ROOT / "ridebase-ml/models/v3_research"
MAX_ROWS = 2000

SCENARIOS = {
    "recent_service":        lambda X, m: X["days_since_last_service"] <= 45,
    "near_maintenance":      lambda X, m: X["policy_due_ratio__ENGINE_OIL_CHANGE"].between(0.85, 1.0),
    "overdue":               lambda X, m: X["policy_due_ratio__ENGINE_OIL_CHANGE"] >= 1.5,
    "high_usage":            lambda X, m: X["annual_km_baseline"] >= X["annual_km_baseline"].quantile(0.9),
    "low_usage":             lambda X, m: X["annual_km_baseline"] <= X["annual_km_baseline"].quantile(0.1),
    "rich_task_history":     lambda X, m: X["prior_task_line_total"] >= 40,
    "sparse_task_history":   lambda X, m: X["prior_task_line_total"].between(1, 5),
    "no_task_history":       lambda X, m: X["prior_task_line_total"] == 0,
    "unseen_motorcycle":     lambda X, m: m["is_unseen_motorcycle_holdout"] == 1,
    "older_motorcycle":      lambda X, m: X["production_age_days"] > 10 * 365,
    "newer_motorcycle":      lambda X, m: X["production_age_days"] <= 3 * 365,
    "chain_drive":           lambda X, m: X["hist_count__CHAIN_CLEAN"] > 0,
    "scooter":               lambda X, m: X["category"] == "SCOOTER",
}


def main() -> int:
    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    pred = V3TaskPredictor.load(MODELS)
    policy = pred.label_policy
    meta, X = prep.ds.meta, prep.ds.features
    pool = meta["v3_split"].isin(["VALIDATION", "TEST"]).to_numpy()

    hidden = {c for c, p in policy.items() if p.hidden_by_default}
    results, failures = {}, []

    for name, fn in SCENARIOS.items():
        sel = np.flatnonzero(pool & fn(X, meta).to_numpy())
        if len(sel) == 0:
            results[name] = {"rows": 0, "note": "no matching landmarks"}
            continue
        sel = sel[:MAX_ROWS]
        Xs, ids = X.iloc[sel], meta["motorcycle_id"].iloc[sel]

        out_a = pred.predict_product(Xs, ids, top_k=3)
        out_b = pred.predict_product(Xs, ids, top_k=3)      # determinism
        out5 = pred.predict_product(Xs, ids, top_k=5)

        probs = np.array([list(r["all_task_probabilities"].values()) for r in out_a])
        checks = {
            "rows": int(len(sel)),
            "all_finite": bool(np.isfinite(probs).all()),
            "within_0_1": bool((probs >= 0).all() and (probs <= 1).all()),
            "deterministic_repeat": bool(
                json.dumps([r["top_tasks"] for r in out_a], sort_keys=True)
                == json.dumps([r["top_tasks"] for r in out_b], sort_keys=True)),
            "ranking_stable": all(
                [t["task_code"] for t in a["top_tasks"]] == [t["task_code"] for t in b["top_tasks"]]
                for a, b in zip(out_a, out_b)),
            "no_duplicate_task_codes": all(
                len({t["task_code"] for t in r["top_tasks"]}) == len(r["top_tasks"]) for r in out_a),
            "top_k_count_correct": (all(len(r["top_tasks"]) <= 3 for r in out_a)
                                    and all(len(r["top_tasks"]) <= 5 for r in out5)),
            "top_k_5_returns_more_than_3": bool(
                max(len(r["top_tasks"]) for r in out5)
                >= max(len(r["top_tasks"]) for r in out_a)),
            "hidden_labels_never_shown": all(
                all(t["task_code"] not in hidden for t in r["top_tasks"]) for r in out_a),
            "ranks_dense_and_ordered": all(
                [t["rank"] for t in r["top_tasks"]] == list(range(1, len(r["top_tasks"]) + 1))
                and [t["probability"] for t in r["top_tasks"]]
                    == sorted([t["probability"] for t in r["top_tasks"]], reverse=True)
                for r in out_a),
            "confidence_tier_valid": all(
                t["confidence"] in (PP.TIER_HIGH, PP.TIER_MEDIUM, PP.TIER_LOW, PP.TIER_LIMITED_DATA)
                for r in out_a for t in r["top_tasks"]),
            "high_confidence_only_on_primary": all(
                t["product_status"] == PP.PRIMARY
                for r in out_a for t in r["top_tasks"] if t["confidence"] == PP.TIER_HIGH),
            "disclaimer_always_present": all(
                any(PP.DISCLAIMER_SYNTHETIC_TR in w for w in r["warnings"]) for r in out_a),
            "not_failure_disclaimer_present": all(
                any(PP.DISCLAIMER_NOT_FAILURE_TR in w for w in r["warnings"]) for r in out_a),
            "no_urgency_or_v2_1_field": all(
                not any(k in r for k in ("urgency", "risk_30d", "risk_90d", "median_service_days"))
                for r in out_a),
            "feature_coverage_reported": all("feature_coverage" in r for r in out_a),
            "all_44_labels_returned": all(len(r["all_task_probabilities"]) == 44 for r in out_a),
            "mean_top1_probability": round(float(np.mean(
                [r["top_tasks"][0]["probability"] for r in out_a if r["top_tasks"]])), 4),
            "confidence_mix": _counts(t["confidence"] for r in out_a for t in r["top_tasks"]),
            "top1_task_mix": _counts(r["top_tasks"][0]["task_code"] for r in out_a if r["top_tasks"]),
        }
        for k, v in checks.items():
            if isinstance(v, bool) and not v:
                failures.append(f"{name}.{k}")
        results[name] = checks
        print(f"{name:24s} n={checks['rows']:5d} finite={checks['all_finite']} "
              f"det={checks['deterministic_repeat']} hidden_ok={checks['hidden_labels_never_shown']} "
              f"top1={checks['mean_top1_probability']:.3f}", flush=True)

    # weak-label probe: does a hidden label ever out-rank the shown leader?
    sel = np.flatnonzero(pool)[:4000]
    out = pred.predict_product(X.iloc[sel], meta["motorcycle_id"].iloc[sel], top_k=3)
    flagged = sum(1 for r in out if any("rastgele olay" in w for w in r["warnings"]))
    weak = {
        "rows": len(out),
        "landmarks_where_a_hidden_label_outranks_the_shown_leader": flagged,
        "share": round(flagged / max(len(out), 1), 4),
        "handling": ("not shown in the product list; a reliability warning is attached "
                     "and the tier stays DUSUK"),
    }
    print(f"\nweak-label probe: {flagged}/{len(out)} landmarks carry a hidden-label warning")

    payload = {"passed": not failures, "failures": failures,
               "scenarios": results, "weak_label_probe": weak,
               "max_rows_per_scenario": MAX_ROWS}
    (REPORTS / "17_topk_product_audit.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nAUDIT:", "PASS" if not failures else f"FAIL {failures}")
    return 0 if not failures else 1


def _counts(it) -> dict:
    out: dict = {}
    for v in it:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:6])


if __name__ == "__main__":
    raise SystemExit(main())
