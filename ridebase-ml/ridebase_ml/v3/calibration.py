"""V3 probability calibration (Phase 16).

The V3 card shows percentages, so the numbers have to mean something. Calibration
is fitted on a held-out slice of TRAIN -- never on the data the model was fitted
on, and never on TEST -- and the method is chosen per label on VALIDATION.

Selection rule, in order:

1. A label with fewer than ``MIN_POSITIVES_FOR_CALIBRATION`` positives in the
   calibration fold is left **uncalibrated**. Fitting isotonic regression on 20
   positives produces a step function that is confidently wrong, which is worse
   than a mildly miscalibrated raw score.
2. Otherwise pick the method with the lowest VALIDATION Brier score, but reject
   any method that costs more than ``MAX_PR_AUC_LOSS`` PR-AUC. Calibration must
   not buy reliability by destroying ranking -- ranking is what the top-K product
   surface is built on.
"""

from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss

MIN_POSITIVES_FOR_CALIBRATION = 50
MAX_PR_AUC_LOSS = 0.01
METHODS = ("none", "isotonic", "sigmoid")


class _Identity:
    def transform(self, p):
        return p


class _Isotonic:
    def __init__(self, iso):
        self.iso = iso

    def transform(self, p):
        return self.iso.predict(p)


class _Sigmoid:
    def __init__(self, lr):
        self.lr = lr

    def transform(self, p):
        return self.lr.predict_proba(p.reshape(-1, 1))[:, 1]


def _fit_one(method, p, y):
    if method == "none":
        return _Identity()
    if method == "isotonic":
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(p, y)
        return _Isotonic(iso)
    lr = LogisticRegression(max_iter=1000)
    lr.fit(p.reshape(-1, 1), y)
    return _Sigmoid(lr)


class MultiLabelCalibrator:
    """Per-label calibrator with per-label method selection."""

    def __init__(self, labels: list[str]):
        self.labels = labels
        self.method_: list[str] = []
        self.cal_: list = []
        self.report_: list[dict] = []

    def fit(self, p_cal: np.ndarray, y_cal: np.ndarray,
            p_val: np.ndarray, y_val: np.ndarray,
            app_cal: np.ndarray, app_val: np.ndarray) -> "MultiLabelCalibrator":
        for j, name in enumerate(self.labels):
            mc, mv = app_cal[:, j], app_val[:, j]
            pc, yc = p_cal[mc, j], y_cal[mc, j]
            pv, yv = p_val[mv, j], y_val[mv, j]
            n_pos = int(yc.sum())
            row = {"label": name, "calibration_positives": n_pos}

            if n_pos < MIN_POSITIVES_FOR_CALIBRATION or len(np.unique(yc)) < 2:
                self.method_.append("none")
                self.cal_.append(_Identity())
                row.update(chosen="none", reason=f"only {n_pos} calibration positives "
                                                 f"(< {MIN_POSITIVES_FOR_CALIBRATION})")
                self.report_.append(row)
                continue

            base_ap = average_precision_score(yv, pv) if yv.sum() else float("nan")
            best, best_brier, cands = None, np.inf, {}
            for m in METHODS:
                try:
                    cal = _fit_one(m, pc, yc)
                    q = np.clip(cal.transform(pv), 0.0, 1.0)
                except ValueError:
                    continue
                brier = brier_score_loss(yv, q)
                ap = average_precision_score(yv, q) if yv.sum() else float("nan")
                cands[m] = {"brier": float(brier), "pr_auc": float(ap)}
                loses_ranking = np.isfinite(base_ap) and np.isfinite(ap) and (base_ap - ap) > MAX_PR_AUC_LOSS
                if brier < best_brier and not loses_ranking:
                    best, best_brier = (m, cal), brier
            if best is None:
                best = ("none", _Identity())
            self.method_.append(best[0])
            self.cal_.append(best[1])
            row.update(chosen=best[0], candidates=cands, baseline_pr_auc=float(base_ap))
            self.report_.append(row)
        return self

    def transform(self, proba: np.ndarray) -> np.ndarray:
        out = np.empty_like(proba, dtype="float64")
        for j, cal in enumerate(self.cal_):
            out[:, j] = np.clip(cal.transform(proba[:, j]), 0.0, 1.0)
        return out


def reliability_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    """Observed frequency vs mean predicted probability, per decile of prediction."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        rows.append({"bin": f"{edges[b]:.1f}-{edges[b+1]:.1f}", "n": int(m.sum()),
                     "mean_predicted": float(p[m].mean()),
                     "observed_rate": float(y[m].mean())})
    return rows


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    rows = reliability_table(y, p, bins)
    n = sum(r["n"] for r in rows)
    return float(sum(r["n"] * abs(r["mean_predicted"] - r["observed_rate"]) for r in rows) / max(n, 1))
