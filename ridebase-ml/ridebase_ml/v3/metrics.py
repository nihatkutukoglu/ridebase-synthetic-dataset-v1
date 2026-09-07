"""V3 multi-label metric contract (Phase 14).

Plain accuracy is never reported as a primary metric -- with a 0.6%-prevalence
label, predicting all-zero scores 99.4% and is worthless.

Applicability masking
---------------------
Predicted probabilities are forced to 0 wherever the task is not physically
applicable to that motorcycle (a chain task on a CVT scooter). This is a
deterministic, point-in-time-safe product rule derived from the taxonomy, not a
learned correction, and it is applied identically to every model and baseline so
comparisons stay fair. Per-label metrics are additionally restricted to the
applicable rows, so a label is never scored on bikes that cannot receive it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score, brier_score_loss, f1_score, hamming_loss,
    precision_score, recall_score, roc_auc_score,
)

TOP_K = (1, 3, 5)


def apply_mask(proba: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Zero out probabilities for tasks that cannot apply to that motorcycle."""
    return np.where(mask, proba, 0.0)


def _safe(fn, y, s, default=float("nan")):
    try:
        if len(np.unique(y)) < 2:
            return default
        return float(fn(y, s))
    except ValueError:
        return default


def top_k_scores(y: np.ndarray, proba: np.ndarray, k: int) -> tuple[float, float]:
    """Precision@k and Recall@k, averaged over rows that have >=1 positive.

    Rows with no positive label are excluded: precision@k is undefined against an
    empty truth set, and including them as zeros would just measure how often the
    next service was empty (never, here -- every service has >=1 task).
    """
    n_pos = y.sum(axis=1)
    keep = n_pos > 0
    if not keep.any():
        return float("nan"), float("nan")
    y, proba, n_pos = y[keep], proba[keep], n_pos[keep]
    kk = min(k, proba.shape[1])
    idx = np.argpartition(-proba, kk - 1, axis=1)[:, :kk]
    hits = np.take_along_axis(y, idx, axis=1).sum(axis=1)
    return float((hits / kk).mean()), float((hits / n_pos).mean())


def global_metrics(y: np.ndarray, proba: np.ndarray, thresholds: np.ndarray) -> dict:
    pred = (proba >= thresholds[None, :]).astype(int)
    out = {
        "micro_f1": float(f1_score(y, pred, average="micro", zero_division=0)),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y, pred, average="weighted", zero_division=0)),
        "micro_precision": float(precision_score(y, pred, average="micro", zero_division=0)),
        "micro_recall": float(recall_score(y, pred, average="micro", zero_division=0)),
        "hamming_loss": float(hamming_loss(y, pred)),
        "subset_accuracy": float((pred == y).all(axis=1).mean()),  # secondary only
        "micro_pr_auc": float(average_precision_score(y.ravel(), proba.ravel())),
    }
    # macro PR-AUC / mAP over labels that have at least one positive here
    aps = [average_precision_score(y[:, j], proba[:, j])
           for j in range(y.shape[1]) if y[:, j].sum() > 0]
    out["macro_pr_auc"] = float(np.mean(aps)) if aps else float("nan")
    out["mean_average_precision"] = out["macro_pr_auc"]
    out["labels_with_positives"] = len(aps)
    for k in TOP_K:
        p, r = top_k_scores(y, proba, k)
        out[f"precision_at_{k}"], out[f"recall_at_{k}"] = p, r
    return out


def per_label_metrics(y: np.ndarray, proba: np.ndarray, thresholds: np.ndarray,
                      labels: list[str], applicable: np.ndarray) -> pd.DataFrame:
    rows = []
    for j, name in enumerate(labels):
        m = applicable[:, j]
        yj, sj = y[m, j], proba[m, j]
        pj = (sj >= thresholds[j]).astype(int)
        rows.append({
            "label": name,
            "support": int(yj.sum()),
            "applicable_rows": int(m.sum()),
            "prevalence": float(yj.mean()) if m.any() else float("nan"),
            "threshold": float(thresholds[j]),
            "pr_auc": _safe(average_precision_score, yj, sj),
            "roc_auc": _safe(roc_auc_score, yj, sj),
            "precision": float(precision_score(yj, pj, zero_division=0)),
            "recall": float(recall_score(yj, pj, zero_division=0)),
            "f1": float(f1_score(yj, pj, zero_division=0)),
            "brier": float(brier_score_loss(yj, np.clip(sj, 0, 1))) if m.any() else float("nan"),
        })
    return pd.DataFrame(rows)


def evaluate(y: np.ndarray, proba: np.ndarray, thresholds: np.ndarray,
             labels: list[str], applicable: np.ndarray) -> dict:
    proba = apply_mask(proba, applicable)
    return {
        "global": global_metrics(y, proba, thresholds),
        "per_label": per_label_metrics(y, proba, thresholds, labels, applicable),
    }
