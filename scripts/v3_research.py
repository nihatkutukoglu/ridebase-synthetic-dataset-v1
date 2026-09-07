#!/usr/bin/env python3
"""V3 research driver. One subcommand per phase; every phase writes its artifacts.

    python3 scripts/v3_research.py leakage      # Phase 8
    python3 scripts/v3_research.py landmarks    # Phase 6
    python3 scripts/v3_research.py generator    # Phase 9
    python3 scripts/v3_research.py signal       # Phase 10
    python3 scripts/v3_research.py tournament   # Phases 11-14
    python3 scripts/v3_research.py ablation     # Phase 19
    python3 scripts/v3_research.py oracle       # Phase 20
    python3 scripts/v3_research.py freeze       # Phases 15/16/21
    python3 scripts/v3_research.py test         # Phase 22 (single frozen touch)

Run from the repository root with /usr/bin/python3.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ridebase-ml"))

import numpy as np
import pandas as pd

from ridebase_ml.v3 import dataset as D
from ridebase_ml.v3 import experiment as E
from ridebase_ml.v3 import features as F
from ridebase_ml.v3 import leakage as LK
from ridebase_ml.v3 import models as M

REPORTS = ROOT / "reports/v3"
OUT = ROOT / "ridebase-ml/derived_outputs/v3"
MODELS = ROOT / "ridebase-ml/models/v3_research"
for d in (REPORTS, OUT, MODELS):
    d.mkdir(parents=True, exist_ok=True)


def _json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")
    print(f"wrote {path.relative_to(ROOT)}")


def _pool():
    return D.select_landmarks(D.assign_split(D.observed_landmarks(), purge=True), "random_one")


# ---------------------------------------------------------------- Phase 8
def cmd_leakage(_):
    labels = E.load_labels(ROOT)
    ds = D.build(labels, "random_one")
    res = LK.run_all(_pool(), ds.features.columns.tolist(), labels)
    res["dataset_manifest"] = ds.manifest
    _json(OUT / "08_leakage_audit.json", res)
    print("LEAKAGE GATE:", "PASS" if res["passed"] else "FAIL")
    return res


# ---------------------------------------------------------------- Phase 6
def cmd_landmarks(_):
    labels = E.load_labels(ROOT)
    pool = D.assign_split(D.observed_landmarks(), purge=True)
    rows = []
    for s in D.STRATEGIES:
        lm = D.select_landmarks(pool, s)
        per_target = lm.groupby(["motorcycle_id", "next_service_id"]).size()
        rows.append({
            "strategy": s, "rows": len(lm),
            "motorcycles": int(lm["motorcycle_id"].nunique()),
            "target_services": int(lm["next_service_id"].nunique()),
            "landmarks_per_target": round(len(lm) / lm["next_service_id"].nunique(), 3),
            "max_landmarks_per_target": int(per_target.max()),
            "landmarks_per_motorcycle": round(len(lm) / lm["motorcycle_id"].nunique(), 2),
            "lead_days_p10": float(lm["lead_days"].quantile(0.10)),
            "lead_days_median": float(lm["lead_days"].median()),
            "lead_days_mean": round(float(lm["lead_days"].mean()), 1),
            "lead_days_p90": float(lm["lead_days"].quantile(0.90)),
            "pct_lead_le_30d": round(float((lm["lead_days"] <= 30).mean()), 4),
            **{f"n_{k}": int(v) for k, v in lm["v3_split"].value_counts().items()},
        })
    df = pd.DataFrame(rows)
    df.to_csv(REPORTS / "06_landmark_strategies.csv", index=False)
    print(df.to_string(index=False))

    # cross-split target sharing: a target service must never span two splits
    shared = (pool.groupby("next_service_id")["v3_split"].nunique() > 1).sum()
    stats = {"strategies": rows,
             "target_services_spanning_two_splits_in_pool": int(shared),
             "note": "measured on the purged 'all' pool, the worst case"}
    _json(OUT / "06_landmark_design.json", stats)
    return stats


# ---------------------------------------------------------------- Phase 9
def cmd_generator(_):
    from ridebase_ml.v3.sources import load_sources
    labels = E.load_labels(ROOT)
    st = load_sources()["service_tasks"]
    done = st[st["status"] == "COMPLETED"]
    mix = pd.crosstab(done["task_code"], done["trigger_reason"], normalize="index")
    mix = mix.reindex(labels).fillna(0.0)
    mix["n_task_lines"] = done["task_code"].value_counts().reindex(labels).fillna(0).astype(int)
    mix["policy_due_rate"] = done.groupby("task_code")["is_policy_due"].mean().reindex(labels)

    det = mix.get("MILEAGE", 0) + mix.get("TIME", 0) + mix.get("MILEAGE_AND_TIME", 0)
    bundle = mix.get("INSPECTION_BUNDLE", 0)
    finding = mix.get("INSPECTION_FINDING", 0)
    fault = mix.get("FAULT", 0)
    wear = mix.get("WEAR", 0)

    def classify(i):
        if fault[i] >= 0.9:
            return "E_BREAKDOWN_RANDOM_EVENT"
        if finding[i] >= 0.9:
            return "E_INSPECTION_FINDING_RANDOM"
        if wear[i] >= 0.9:
            return "B_STOCHASTIC_WEAR"
        if det[i] >= 0.95 and mix["policy_due_rate"][i] >= 0.95:
            return "A_DETERMINISTIC_THRESHOLD"
        if bundle[i] >= 0.6:
            return "D_STOCHASTIC_BUNDLE_ATTACHMENT"
        return "F_MIXED_THRESHOLD_AND_BUNDLE"

    mix["generating_process"] = [classify(i) for i in mix.index]
    mix["deterministic_share"] = det
    mix["bundle_share"] = bundle
    mix["random_event_share"] = finding + fault
    mix.round(4).to_csv(REPORTS / "09_generator_process_by_label.csv")
    print(mix["generating_process"].value_counts().to_string())
    _json(OUT / "09_generator_rule_audit.json", {
        "generator_source_available_in_repo": False,
        "note": ("The core MAINTENANCE_EVENT_SIM_V1 generator that produced services.csv "
                 "and service_tasks.csv is not present in this repository -- only the "
                 "v1.1 QA pass and the v1.4/v1.5 tail extenders are. The audit is "
                 "therefore empirical, inferred from trigger_reason and is_policy_due."),
        "process_counts": mix["generating_process"].value_counts().to_dict(),
        "by_label": mix.round(4).reset_index().to_dict("records"),
    })
    return mix


def _baselines(labels):
    iv = F.policy_intervals()
    return [M.PrevalenceBaseline(), M.RuleBaseline(labels),
            M.RuleProjectedBaseline(labels, iv), M.RecurrenceBaseline(labels)]


def _row(name, g, extra=None):
    r = {"model": name, **{k: (round(v, 4) if isinstance(v, float) else v)
                           for k, v in g.items()}}
    return {**r, **(extra or {})}


# ---------------------------------------------------------------- Phase 6b
def cmd_landmark_models(_):
    """Empirical half of Phase 6: does a strategy inflate its own metrics?"""
    labels = E.load_labels(ROOT)
    rows = []
    for s in D.STRATEGIES:
        prep = E.prepare(labels, strategy=s)
        cols = prep.ds.features.columns.tolist()
        mdl = M.candidate_models(cols)["xgboost"]()
        r = E.run(mdl, prep)
        rows.append(_row(s, r["VALIDATION"],
                         {"train_rows": len(prep.idx["TRAIN"]),
                          "val_rows": len(prep.idx["VALIDATION"]),
                          "lead_days_median": float(prep.ds.meta["lead_days"].median())}))
        print(rows[-1]["model"], "microF1", rows[-1]["micro_f1"], "P@3", rows[-1]["precision_at_3"])
    df = pd.DataFrame(rows)
    df.to_csv(REPORTS / "06_landmark_strategy_models.csv", index=False)
    _json(OUT / "06_landmark_strategy_models.json", rows)
    return rows


# ---------------------------------------------------------------- Phase 10
def cmd_signal(_):
    """Per-label learnability on TRAIN/VAL only, before any big tournament."""
    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    cols = prep.ds.features.columns.tolist()
    runs = {}
    for b in _baselines(labels):
        runs[b.name] = E.run(b, prep)
    runs["logreg"] = E.run(M.candidate_models(cols)["logreg"](), prep)
    runs["xgboost"] = E.run(M.candidate_models(cols)["xgboost"](), prep)

    frames = []
    for name, r in runs.items():
        pl = r["VALIDATION_per_label"].copy()
        pl.insert(0, "model", name)
        frames.append(pl)
    per_label = pd.concat(frames, ignore_index=True)
    per_label.round(4).to_csv(REPORTS / "10_signal_study.csv", index=False)

    # signal strength = best ML PR-AUC lift over the label's own prevalence
    piv = per_label.pivot(index="label", columns="model", values="pr_auc")
    prev = per_label[per_label.model == "xgboost"].set_index("label")["prevalence"]
    sup = per_label[per_label.model == "xgboost"].set_index("label")["support"]
    best = piv[["logreg", "xgboost"]].max(axis=1)
    lift = best / prev
    band = pd.cut(lift, [-np.inf, 1.15, 1.6, 3.0, np.inf],
                  labels=["WEAK", "MEDIUM", "STRONG", "VERY_STRONG"])
    summary = pd.DataFrame({"prevalence": prev, "support": sup,
                            "pr_auc_best_ml": best,
                            "pr_auc_rule": piv.get("baseline1b_rule_projected"),
                            "pr_auc_recurrence": piv.get("baseline2_recurrence"),
                            "lift_over_prevalence": lift, "signal_band": band})
    summary = summary.sort_values("lift_over_prevalence", ascending=False)
    summary.round(4).to_csv(REPORTS / "10_signal_summary.csv")
    print(summary.round(3).to_string())
    print()
    print(summary.signal_band.value_counts().to_string())
    _json(OUT / "10_signal_study.json",
          {"bands": summary.signal_band.value_counts().to_dict(),
           "global": {k: v["VALIDATION"] for k, v in runs.items()}})
    return summary


# ---------------------------------------------------------------- Phases 11-14
def cmd_tournament(_):
    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    cols = prep.ds.features.columns.tolist()
    rows, per_label = [], []

    def record(name, r):
        rows.append(_row(name, r["VALIDATION"], {"fit_seconds": r["fit_seconds"]}))
        pl = r["VALIDATION_per_label"].copy(); pl.insert(0, "model", name)
        per_label.append(pl)
        g = r["VALIDATION"]
        print(f"{name:26s} microF1={g['micro_f1']:.4f} macroF1={g['macro_f1']:.4f} "
              f"mAP={g['mean_average_precision']:.4f} microPR={g['micro_pr_auc']:.4f} "
              f"P@3={g['precision_at_3']:.4f} R@3={g['recall_at_3']:.4f} "
              f"({r['fit_seconds']}s)", flush=True)

    for b in _baselines(labels):
        record(b.name, E.run(b, prep))
    for name, factory in M.candidate_models(cols).items():
        record(name, E.run(factory(), prep))

    df = pd.DataFrame(rows).sort_values("mean_average_precision", ascending=False)
    df.to_csv(REPORTS / "12_tournament_validation.csv", index=False)
    pd.concat(per_label, ignore_index=True).round(4).to_csv(
        REPORTS / "12_tournament_per_label_validation.csv", index=False)
    _json(OUT / "12_tournament.json", rows)
    print()
    print(df[["model", "micro_f1", "macro_f1", "mean_average_precision",
              "micro_pr_auc", "precision_at_3", "recall_at_3", "hamming_loss"]].to_string(index=False))
    return df


# ---------------------------------------------------------------- Phase 19
ABLATION_SETS = {
    "F0_basic":                 ("F0_base",),
    "F1_plus_policy":           ("F0_base", "F1_policy"),
    "F2_plus_task_history":     ("F0_base", "F1_policy", "F2_hist"),
    "F3_plus_task_recency":     ("F0_base", "F1_policy", "F2_hist", "F3_recency"),
    "F4_plus_behavioural":      ("F0_base", "F1_policy", "F2_hist", "F3_recency", "F4_behaviour"),
    "task_history_only_no_policy": ("F0_base", "F2_hist", "F3_recency"),
}


def cmd_ablation(_):
    """Where does the signal come from: rules, task history, or behaviour?"""
    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    rows = []
    for name, blocks in ABLATION_SETS.items():
        cols = prep.ds.block(*blocks)
        mdl = M.candidate_models(cols)["xgboost"]()
        r = E.run(mdl, prep)
        rows.append(_row(name, r["VALIDATION"],
                         {"blocks": "+".join(blocks), "n_features": len(cols)}))
        g = r["VALIDATION"]
        print(f"{name:30s} n={len(cols):4d} microF1={g['micro_f1']:.4f} "
              f"mAP={g['mean_average_precision']:.4f} microPR={g['micro_pr_auc']:.4f} "
              f"P@3={g['precision_at_3']:.4f}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(REPORTS / "19_history_depth_ablation.csv", index=False)
    _json(OUT / "19_ablation.json", rows)
    return df


# ---------------------------------------------------------------- Phase 20
def cmd_oracle(_):
    """RESEARCH ORACLE -- NOT DEPLOYABLE. Upper bound if the next visit were known.

    Oracle features describe the *target* service (its date, type and odometer).
    They are pure future information and exist only to size the gap between what
    an observable model can reach and what is knowable at all. They never enter a
    candidate production dataset or any frozen artifact.
    """
    from ridebase_ml.v3.target import service_index
    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    meta = prep.ds.meta
    X = prep.ds.features.copy()
    obs_cols = X.columns.tolist()

    target_odo = service_index().set_index("service_id")["odometer_km"]
    X["ORACLE_lead_days"] = meta["lead_days"].to_numpy()
    X["ORACLE_target_km_delta"] = (
        meta["next_service_id"].map(target_odo).to_numpy()
        - X["current_odometer_km_at_landmark"].to_numpy())
    for t in ("PERIODIC", "REPAIR", "TIRE", "BREAKDOWN"):
        X[f"ORACLE_target_type_{t}"] = (meta["target_service_type"] == t).astype(float).to_numpy()
    oracle_cols = obs_cols + [c for c in X.columns if c.startswith("ORACLE_")]

    prep_o = E.Prepared(prep.ds, prep.labels, prep.idx, prep.app, prep.y)
    prep_o.ds = D.V3Dataset(X, prep.ds.targets, prep.ds.meta, prep.ds.labels,
                            prep.ds.feature_blocks, prep.ds.manifest)

    rows = []
    for name, cols in (("observable_champion_family", obs_cols), ("RESEARCH_ORACLE", oracle_cols)):
        r = E.run(M.candidate_models(cols)["xgboost"](), prep_o)
        rows.append(_row(name, r["VALIDATION"], {"n_features": len(cols)}))
        g = r["VALIDATION"]
        print(f"{name:28s} mAP={g['mean_average_precision']:.4f} "
              f"microPR={g['micro_pr_auc']:.4f} microF1={g['micro_f1']:.4f} "
              f"P@3={g['precision_at_3']:.4f}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(REPORTS / "20_oracle_gap.csv", index=False)
    _json(OUT / "20_oracle_gap.json",
          {"label": "RESEARCH ORACLE — NOT DEPLOYABLE",
           "oracle_features": [c for c in X.columns if c.startswith("ORACLE_")],
           "rows": rows})
    return df


# ---------------------------------------------------------------- Phase 17
def cmd_chains(_):
    """Classifier Chains as a research challenger, given real label dependence."""
    from sklearn.multioutput import ClassifierChain
    from xgboost import XGBClassifier
    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    cols = prep.ds.features.columns.tolist()
    Xtr, ytr, atr = prep.part("TRAIN")
    Xv, yv, av = prep.part("VALIDATION")
    pre = M.make_preprocessor(cols)
    Ttr = pre.fit_transform(Xtr[cols]); Tv = pre.transform(Xv[cols])

    base = XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.08,
                         subsample=0.9, colsample_bytree=0.7, min_child_weight=5,
                         tree_method="hist", eval_metric="logloss", n_jobs=-1,
                         random_state=1, verbosity=0)
    # order labels most->least prevalent so a chain link conditions on a
    # well-estimated parent rather than on a noisy rare one
    order = list(np.argsort(-ytr.mean(axis=0)))
    cc = ClassifierChain(base, order=order, random_state=1)
    cc.fit(Ttr, ytr)
    pv = cc.predict_proba(Tv)
    thr = E.tune_thresholds(yv, pv, av)
    from ridebase_ml.v3.metrics import evaluate
    res = evaluate(yv, pv, thr, labels, av)
    row = _row("classifier_chain_xgb", res["global"])
    print({k: row[k] for k in ("micro_f1", "macro_f1", "mean_average_precision",
                               "micro_pr_auc", "precision_at_3", "recall_at_3")})
    _json(OUT / "17_classifier_chain.json", row)
    return row


# ---------------------------------------------------- Phases 15, 16, 21
#: champion selection is a lexicographic rule fixed BEFORE the tournament ran, so
#: it cannot be reverse-engineered from the results. See reports/v3/21_champion.md.
SELECTION_CRITERIA = [
    ("leakage_gate", "must be PASS -- gate, not a score"),
    ("beats_rule_baseline_mAP", "mAP must exceed baseline1b_rule_projected"),
    ("mean_average_precision", "primary: ranking quality across all labels"),
    ("micro_pr_auc", "secondary: ranking quality weighted by prevalence"),
    ("micro_f1", "thresholded decision quality"),
    ("precision_at_3", "the product surface actually shows a top-3/5 list"),
    ("simplicity", "tie-break: fewer moving parts wins"),
]
CAL_FRACTION = 0.2


def _split_train_for_calibration(prep):
    """Hold out the most recent 20% of TRAIN, by landmark date, for calibration.

    Temporal rather than random: a calibrator fitted on rows interleaved with the
    fitting rows sees the same motorcycles in the same months and reports
    optimistic reliability.
    """
    tr = prep.idx["TRAIN"]
    dates = prep.ds.meta["landmark_at"].to_numpy()[tr]
    order = np.argsort(dates, kind="stable")
    cut = int(len(tr) * (1 - CAL_FRACTION))
    return tr[order[:cut]], tr[order[cut:]]


def cmd_freeze(args):
    import joblib
    from ridebase_ml.v3 import calibration as C
    from ridebase_ml.v3.metrics import evaluate

    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    cols = prep.ds.features.columns.tolist()

    tour = pd.read_csv(REPORTS / "12_tournament_validation.csv")
    rule = tour.loc[tour.model == "baseline1b_rule_projected", "mean_average_precision"].iloc[0]
    ml = tour[~tour.model.str.startswith("baseline")].copy()
    eligible = ml[ml.mean_average_precision > rule]
    champion_family = args.champion or eligible.sort_values(
        ["mean_average_precision", "micro_pr_auc", "micro_f1", "precision_at_3"],
        ascending=False).iloc[0]["model"]
    print(f"champion family: {champion_family} (rule baseline mAP {rule:.4f})")

    fit_idx, cal_idx = _split_train_for_calibration(prep)
    Xf, yf, af = prep.ds.features.iloc[fit_idx], prep.y[fit_idx], prep.app[fit_idx]
    Xc, yc, ac = prep.ds.features.iloc[cal_idx], prep.y[cal_idx], prep.app[cal_idx]
    Xv, yv, av = prep.part("VALIDATION")

    model = M.candidate_models(cols)[champion_family]()
    model.fit(Xf, yf, applicable=af)

    p_cal = model.predict_proba(Xc)
    p_val_raw = model.predict_proba(Xv)
    cal = C.MultiLabelCalibrator(labels).fit(p_cal, yc, p_val_raw, yv, ac, av)
    p_val = cal.transform(p_val_raw)

    # ---- Phase 15: threshold policy, VALIDATION only ----------------------
    # Criterion, fixed before TEST: maximise mean(micro F1, macro F1) subject to a
    # count-realism guard -- the number of tasks predicted per service must not
    # exceed 1.5x the number that actually occur. Without the guard, per-label F1
    # maximisation wins on paper while predicting ~10 tasks per service against an
    # actual 3.3, which is individually optimal per label and collectively useless
    # to a workshop.
    actual_tasks = float(yv.sum(axis=1).mean())
    policies = {"global": {}, "per_label": {},
                "precision_floor@0.3": {"precision_floor": 0.3},
                "precision_floor@0.5": {"precision_floor": 0.5}}
    cand = {}
    for name, kw in policies.items():
        mode = name.split("@")[0]
        t = E.tune_thresholds(yv, p_val, av, mode=mode, **kw)
        g = evaluate(yv, p_val, t, labels, av)["global"]
        n_pred = float((np.where(av, p_val, 0.0) >= t[None, :]).sum(axis=1).mean())
        cand[name] = {"thresholds": t, "micro_f1": g["micro_f1"], "macro_f1": g["macro_f1"],
                      "mean_micro_macro_f1": (g["micro_f1"] + g["macro_f1"]) / 2,
                      "hamming_loss": g["hamming_loss"], "precision_at_3": g["precision_at_3"],
                      "predicted_tasks_per_service": n_pred,
                      "count_ratio": n_pred / actual_tasks}
        print(f"  {name:22s} microF1={g['micro_f1']:.4f} macroF1={g['macro_f1']:.4f} "
              f"tasks/row={n_pred:.2f} ratio={n_pred/actual_tasks:.2f}")
    realistic = {k: v for k, v in cand.items() if v["count_ratio"] <= 1.5}
    pool_ = realistic or cand
    policy = max(pool_, key=lambda k: pool_[k]["mean_micro_macro_f1"])
    thr = cand[policy]["thresholds"]
    print(f"threshold policy: {policy} (actual tasks/service {actual_tasks:.2f})")

    val = evaluate(yv, p_val, thr, labels, av)
    rel = {l: C.reliability_table(yv[av[:, j], j], p_val[av[:, j], j])
           for j, l in enumerate(labels)}
    ece = {l: C.expected_calibration_error(yv[av[:, j], j], p_val[av[:, j], j])
           for j, l in enumerate(labels)}

    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODELS / "champion_model.joblib")
    joblib.dump(cal, MODELS / "calibrator.joblib")
    _json(MODELS / "feature_list.json", {"features": cols, "feature_count": len(cols),
                                         "blocks": {k: len(v) for k, v in prep.ds.feature_blocks.items()}})
    inv = pd.read_csv(REPORTS / "03_label_inventory.csv").set_index("task_code")
    _json(MODELS / "label_list.json",
          {"labels": labels,
           "label_classes": {l: inv.loc[l, "label_class"] for l in labels}})
    _json(MODELS / "thresholds.json",
          {"policy": policy, "tuned_on": "VALIDATION",
           "criterion": ("max mean(micro F1, macro F1) subject to "
                         "predicted tasks per service <= 1.5x actual"),
           "actual_tasks_per_service": actual_tasks,
           "thresholds": thr.tolist(),
           "by_label": {l: float(t) for l, t in zip(labels, thr)},
           "candidates": {k: {m: v for m, v in d.items() if m != "thresholds"}
                          for k, d in cand.items()}})
    _json(MODELS / "calibration_report.json",
          {"fold": "last 20% of TRAIN by landmark date",
           "min_positives_for_calibration": C.MIN_POSITIVES_FOR_CALIBRATION,
           "max_pr_auc_loss": C.MAX_PR_AUC_LOSS,
           "method_counts": pd.Series(cal.method_).value_counts().to_dict(),
           "per_label": cal.report_,
           "expected_calibration_error": ece,
           "reliability": rel})
    _json(MODELS / "selection_before_test.json",
          {"selected_at": "before any TEST evaluation",
           "criteria": SELECTION_CRITERIA,
           "champion_family": champion_family,
           "rule_baseline_mAP": float(rule),
           "eligible_families": eligible.model.tolist(),
           "validation_metrics": val["global"]})
    manifest = {
        "model_version": "v3.0-research",
        "status": "RESEARCH_OFFLINE_SYNTHETIC_ONLY",
        "deployed": False,
        "champion_family": champion_family,
        "source_world": "v1_4",
        "landmark_strategy": "random_one",
        "seed": prep.ds.manifest["seed"],
        "dataset_manifest": prep.ds.manifest,
        "threshold_policy": policy,
        "calibration_policy": pd.Series(cal.method_).value_counts().to_dict(),
        "train_fit_rows": int(len(fit_idx)), "calibration_rows": int(len(cal_idx)),
        "validation_rows": int(len(prep.idx["VALIDATION"])),
        "real_fleet_validation": "PENDING",
    }
    _json(MODELS / "artifact_manifest.json", manifest)
    val["per_label"].round(4).to_csv(REPORTS / "16_validation_per_label.csv", index=False)
    _json(OUT / "21_champion_validation.json", val["global"])
    print("VALIDATION:", {k: round(v, 4) for k, v in val["global"].items() if isinstance(v, float)})
    return manifest


# ---------------------------------------------------------------- Phase 22
def cmd_test(_):
    """The single frozen TEST touch. Nothing is tuned after this runs."""
    import joblib
    from ridebase_ml.v3.metrics import evaluate

    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    model = joblib.load(MODELS / "champion_model.joblib")
    cal = joblib.load(MODELS / "calibrator.joblib")
    thr = np.asarray(json.loads((MODELS / "thresholds.json").read_text())["thresholds"])

    out = {}
    Xt, yt, at = prep.part("TEST")
    pt = cal.transform(model.predict_proba(Xt))
    res = evaluate(yt, pt, thr, labels, at)
    out["TEST"] = res["global"]
    res["per_label"].round(4).to_csv(REPORTS / "22_test_per_label.csv", index=False)

    u = prep.unseen_test
    if len(u):
        Xu, yu, au = prep.ds.features.iloc[u], prep.y[u], prep.app[u]
        pu = cal.transform(model.predict_proba(Xu))
        ru = evaluate(yu, pu, thr, labels, au)
        out["UNSEEN_MOTORCYCLE_TEST"] = ru["global"]
        out["UNSEEN_MOTORCYCLE_TEST"]["rows"] = int(len(u))
        ru["per_label"].round(4).to_csv(REPORTS / "22_test_unseen_per_label.csv", index=False)

    # subgroup breakdown (Phase 18) -- reported whether or not it flatters V3
    meta, feats = prep.ds.meta, prep.ds.features
    hist = feats["prior_task_line_total"].to_numpy()
    cat = feats["category"].to_numpy()          # category is a feature, not metadata
    age = feats["production_age_days"].to_numpy()
    groups = {
        "low_history (<= 5 prior task lines)": hist <= 5,
        "high_history (> 20 prior task lines)": hist > 20,
        "scooter": cat == "SCOOTER",
        "non_scooter": cat != "SCOOTER",
        "newer_motorcycle (<= 5y)": age <= 5 * 365,
        "older_motorcycle (> 10y)": age > 10 * 365,
        "unseen_motorcycle": (meta["is_unseen_motorcycle_holdout"] == 1).to_numpy(),
        "target_PERIODIC": (meta["target_service_type"] == "PERIODIC").to_numpy(),
        "target_not_PERIODIC": (meta["target_service_type"] != "PERIODIC").to_numpy(),
    }
    test_mask = (meta["v3_split"] == "TEST").to_numpy()
    sub = {}
    for name, m in groups.items():
        sel = np.flatnonzero(test_mask & m)
        if len(sel) < 100:
            sub[name] = {"rows": int(len(sel)), "note": "fewer than 100 TEST rows, not scored"}
            continue
        Xs, ys, as_ = prep.ds.features.iloc[sel], prep.y[sel], prep.app[sel]
        ps = cal.transform(model.predict_proba(Xs))
        sub[name] = {"rows": int(len(sel)), **evaluate(ys, ps, thr, labels, as_)["global"]}
    out["subgroups"] = sub

    out["test_first_touch"] = {
        "frozen_champion": json.loads((MODELS / "artifact_manifest.json").read_text())["champion_family"],
        "thresholds_frozen_before_test": True,
        "model_changed_after_seeing_test": False,
    }
    _json(MODELS / "test_evaluation.json", out)
    _json(OUT / "22_frozen_test.json", out)
    for k in ("TEST", "UNSEEN_MOTORCYCLE_TEST"):
        if k in out:
            print(k, {m: round(v, 4) for m, v in out[k].items() if isinstance(v, float)})
    return out


# ------------------------------------------------------------ Phases 23, 24
#: Realistic scenario sweeps. Each is a *filter over real landmarks*, not a
#: hand-built feature row -- a synthetic row can silently violate the joint
#: distribution (100,000 km on a 3-month-old bike) and then "pass" a sanity check
#: that means nothing. No expected probability is hardcoded anywhere below.
SCENARIOS = {
    "low_mileage_recently_serviced":
        lambda X, m: (X["days_since_last_service"] <= 30) & (X["annual_km_baseline"] <= 4000),
    "near_oil_interval":
        lambda X, m: X["policy_due_ratio__ENGINE_OIL_CHANGE"].between(0.85, 1.0),
    "overdue_oil_interval":
        lambda X, m: X["policy_due_ratio__ENGINE_OIL_CHANGE"] >= 1.5,
    "chain_heavy_history":
        lambda X, m: X["hist_count__CHAIN_CLEAN"] >= 5,
    "repeated_front_brake_pad_history":
        lambda X, m: X["hist_count__FRONT_BRAKE_PAD_INSPECTION"] >= 3,
    "high_usage":
        lambda X, m: X["annual_km_baseline"] >= X["annual_km_baseline"].quantile(0.9),
    "low_usage":
        lambda X, m: X["annual_km_baseline"] <= X["annual_km_baseline"].quantile(0.1),
    "no_previous_task_history":
        lambda X, m: X["prior_task_line_total"] == 0,
    "long_service_gap":
        lambda X, m: X["days_since_last_service"] >= 540,
    "new_motorcycle":
        lambda X, m: X["production_age_days"] <= 365,
    "unseen_motorcycle":
        lambda X, m: m["is_unseen_motorcycle_holdout"] == 1,
}


def cmd_product(_):
    import joblib
    labels = E.load_labels(ROOT)
    prep = E.prepare(labels)
    model = joblib.load(MODELS / "champion_model.joblib")
    cal = joblib.load(MODELS / "calibrator.joblib")
    thr = np.asarray(json.loads((MODELS / "thresholds.json").read_text())["thresholds"])
    meta, X = prep.ds.meta, prep.ds.features
    val_test = meta["v3_split"].isin(["VALIDATION", "TEST"]).to_numpy()

    def score(idx):
        p = cal.transform(model.predict_proba(X.iloc[idx]))
        return np.where(prep.app[idx], p, 0.0)

    out, tops = {}, {}
    for name, fn in SCENARIOS.items():
        sel = np.flatnonzero(val_test & fn(X, meta).to_numpy())
        if len(sel) == 0:
            out[name] = {"rows": 0, "note": "no matching landmarks"}
            continue
        sel = sel[:2000]
        p = score(sel)
        # determinism: identical input scored twice must be bit-identical
        p2 = score(sel)
        rank = np.argsort(-p, axis=1, kind="stable")
        mean_top = [{"task": labels[j],
                     "mean_probability": round(float(p[:, j].mean()), 4),
                     "observed_rate": round(float(prep.y[sel][:, j].mean()), 4)}
                    for j in np.argsort(-p.mean(axis=0))[:5]]
        tops[name] = mean_top
        out[name] = {
            "rows": int(len(sel)),
            "probabilities_within_0_1": bool((p >= 0).all() and (p <= 1).all()),
            "no_nan": bool(np.isfinite(p).all()),
            "deterministic_repeat": bool(np.array_equal(p, p2)),
            "ranking_stable_on_repeat": bool(np.array_equal(rank, np.argsort(-p2, axis=1, kind="stable"))),
            "inapplicable_forced_to_zero": bool((p[~prep.app[sel]] == 0).all()),
            "mean_predicted_tasks_at_threshold": round(float((p >= thr[None, :]).sum(1).mean()), 3),
            "mean_actual_tasks": round(float(prep.y[sel].sum(1).mean()), 3),
            "top5_by_mean_probability": mean_top,
        }
        print(f"{name:34s} n={out[name]['rows']:5d} "
              f"bounds={out[name]['probabilities_within_0_1']} "
              f"det={out[name]['deterministic_repeat']} "
              f"pred/actual tasks={out[name]['mean_predicted_tasks_at_threshold']}/"
              f"{out[name]['mean_actual_tasks']}", flush=True)
    _json(OUT / "23_product_behavior.json", out)

    # ---- Phase 24: rule expectation vs ML expectation
    sel = np.flatnonzero(val_test)[:8000]
    p = score(sel)
    rule = M.RuleProjectedBaseline(labels, F.policy_intervals()).fit(X.iloc[sel])
    pr = np.where(prep.app[sel], rule.predict_proba(X.iloc[sel]), 0.0)
    y = prep.y[sel]
    rows = []
    for j, lab in enumerate(labels):
        a = prep.app[sel][:, j]
        if a.sum() < 200:
            continue
        rule_says = pr[a, j] >= 0.5           # >= 0.5 means at or past the OEM interval
        ml_says = p[a, j] >= thr[j]
        yj = y[a, j]
        both = rule_says & ml_says
        rule_only = rule_says & ~ml_says
        ml_only = ~rule_says & ml_says
        neither = ~rule_says & ~ml_says
        rows.append({
            "label": lab, "applicable_rows": int(a.sum()), "prevalence": round(float(yj.mean()), 4),
            "agree_both_yes": int(both.sum()), "agree_both_yes_hit_rate": round(float(yj[both].mean()), 4) if both.any() else None,
            "rule_only": int(rule_only.sum()), "rule_only_hit_rate": round(float(yj[rule_only].mean()), 4) if rule_only.any() else None,
            "ml_only": int(ml_only.sum()), "ml_only_hit_rate": round(float(yj[ml_only].mean()), 4) if ml_only.any() else None,
            "agree_both_no": int(neither.sum()), "agree_both_no_hit_rate": round(float(yj[neither].mean()), 4) if neither.any() else None,
        })
    rv = pd.DataFrame(rows)
    rv.to_csv(REPORTS / "24_rule_vs_ml.csv", index=False)
    _json(OUT / "24_rule_vs_ml.json", rows)
    print()
    print(rv.head(20).to_string(index=False))
    return out


COMMANDS = {"leakage": cmd_leakage, "landmarks": cmd_landmarks, "generator": cmd_generator,
            "landmark_models": cmd_landmark_models, "signal": cmd_signal,
            "tournament": cmd_tournament, "ablation": cmd_ablation,
            "oracle": cmd_oracle, "chains": cmd_chains,
            "freeze": cmd_freeze, "test": cmd_test, "product": cmd_product}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=sorted(COMMANDS))
    ap.add_argument("--strategy", default="random_one")
    ap.add_argument("--champion", default=None,
                    help="override the automatic champion family (freeze only)")
    args = ap.parse_args()
    COMMANDS[args.phase](args)


if __name__ == "__main__":
    main()
