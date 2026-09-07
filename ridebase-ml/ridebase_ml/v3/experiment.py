"""V3 experiment harness: prepared splits, threshold selection, one-call runs.

Thresholds are always chosen on VALIDATION and never on TEST (Phase 15).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import SEED
from .dataset import V3Dataset, build
from .metrics import apply_mask, evaluate
from .target import applicability_matrix

LABEL_SET = "config/v3_label_set.json"


def load_labels(root: Path | str = ".") -> list[str]:
    return json.loads((Path(root) / LABEL_SET).read_text())["labels"]


@dataclass
class Prepared:
    ds: V3Dataset
    labels: list[str]
    idx: dict[str, np.ndarray]        # split name -> row positions
    app: np.ndarray                   # (rows x labels) applicability
    y: np.ndarray

    def part(self, split: str):
        i = self.idx[split]
        return self.ds.features.iloc[i], self.y[i], self.app[i]

    @property
    def unseen_test(self) -> np.ndarray:
        m = self.ds.meta
        return np.flatnonzero((m["v3_split"] == "TEST").to_numpy()
                              & (m["is_unseen_motorcycle_holdout"] == 1).to_numpy())


def prepare(labels: list[str], strategy: str = "random_one", root: str | None = None,
            seed: int = SEED) -> Prepared:
    ds = build(labels, strategy, root=root, seed=seed)
    meta = ds.meta
    app_by_moto = applicability_matrix(pd.Index(meta["motorcycle_id"].unique()), labels, root)
    app = app_by_moto.reindex(meta["motorcycle_id"].to_numpy())[labels].to_numpy(dtype=bool)
    y = ds.targets[labels].to_numpy(dtype=np.int8)
    idx = {s: np.flatnonzero((meta["v3_split"] == s).to_numpy())
           for s in ("TRAIN", "VALIDATION", "TEST")}
    return Prepared(ds, labels, idx, app, y)


def tune_thresholds(y: np.ndarray, proba: np.ndarray, app: np.ndarray,
                    grid: np.ndarray | None = None, mode: str = "per_label",
                    precision_floor: float = 0.3) -> np.ndarray:
    """Choose decision thresholds on VALIDATION only. Never on TEST.

    Three policies:

    ``global``           one threshold shared by every label, maximising micro F1.
    ``per_label``        each label's own F1-maximising threshold.
    ``precision_floor``  each label's lowest threshold that still reaches
                         ``precision_floor`` precision, i.e. maximum recall subject
                         to a precision floor; falls back to the label's F1
                         optimum when the floor is unreachable.

    ``per_label`` maximises each label in isolation, which for a 0.6%-prevalence
    label means a threshold near zero. Summed over 44 labels that predicts ~9.8
    tasks per service against an actual 3.3 -- individually optimal, collectively
    useless. The floor policy exists because of that.
    """
    grid = np.linspace(0.01, 0.95, 95) if grid is None else grid
    proba = apply_mask(proba, app)
    n_lab = y.shape[1]
    if mode == "global":
        best, best_f1 = 0.5, -1.0
        for t in grid:
            pred = (proba >= t).astype(int)
            tp = (pred & y).sum()
            f1 = 2 * tp / max(pred.sum() + y.sum(), 1)
            if f1 > best_f1:
                best, best_f1 = float(t), f1
        return np.full(n_lab, best)
    out = np.full(n_lab, 0.5)
    for j in range(n_lab):
        m = app[:, j]
        yj, sj = y[m, j], proba[m, j]
        if yj.sum() == 0:
            out[j] = 1.01          # never fires; no positives to learn a cut from
            continue
        best, best_f1 = 0.5, -1.0
        floor_t = None
        for t in grid:
            pred = (sj >= t)
            n_pred = int(pred.sum())
            tp = int((pred & (yj == 1)).sum())
            if tp == 0:
                continue
            f1 = 2 * tp / (n_pred + yj.sum())
            if f1 > best_f1:
                best, best_f1 = float(t), f1
            if mode == "precision_floor" and floor_t is None and tp / n_pred >= precision_floor:
                floor_t = float(t)   # grid ascends, so the first hit is max recall
        out[j] = best if (mode != "precision_floor" or floor_t is None) else floor_t
    return out


def run(model, prep: Prepared, fit_split: str = "TRAIN",
        eval_splits: tuple[str, ...] = ("VALIDATION",),
        thresholds: np.ndarray | None = None, threshold_mode: str = "per_label") -> dict:
    """Fit on one split, tune thresholds on VALIDATION, evaluate on the rest."""
    Xf, yf, af = prep.part(fit_split)
    t0 = time.time()
    model.fit(Xf, yf, applicable=af) if _takes_applicable(model) else model.fit(Xf, yf)
    fit_s = time.time() - t0

    Xv, yv, av = prep.part("VALIDATION")
    pv = model.predict_proba(Xv)
    thr = tune_thresholds(yv, pv, av, mode=threshold_mode) if thresholds is None else thresholds

    out = {"model": getattr(model, "name", type(model).__name__),
           "fit_seconds": round(fit_s, 1), "thresholds": thr.tolist()}
    for s in eval_splits:
        Xs, ys, as_ = prep.part(s)
        ps = pv if s == "VALIDATION" else model.predict_proba(Xs)
        res = evaluate(ys, ps, thr, prep.labels, as_)
        out[s] = res["global"]
        out[f"{s}_per_label"] = res["per_label"]
        out[f"{s}_proba"] = apply_mask(ps, as_)
    return out


def _takes_applicable(model) -> bool:
    import inspect
    try:
        return "applicable" in inspect.signature(model.fit).parameters
    except (TypeError, ValueError):
        return False
