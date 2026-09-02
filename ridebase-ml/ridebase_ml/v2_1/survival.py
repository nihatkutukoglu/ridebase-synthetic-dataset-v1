"""Shared V2.1 survival math — imported by both training and inference so the
persisted calibrator unpickles without dragging in the training pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

HORIZONS = np.array([30.0, 60.0, 90.0, 120.0])
SEED = 42


def survival_from_score(score: np.ndarray, baseline: dict[str, np.ndarray], horizons: np.ndarray = HORIZONS) -> np.ndarray:
    indices = np.searchsorted(baseline["times"], horizons, side="right") - 1
    h0 = np.where(indices >= 0, baseline["cumulative_hazard"][np.maximum(indices, 0)], 0.0)
    return np.exp(-np.exp(np.clip(score, -18, 18))[:, None] * h0[None, :])


# training-time name kept as a private alias
_survival_from_score = survival_from_score


def _horizon_labels(frame: pd.DataFrame, horizon: float) -> tuple[np.ndarray, np.ndarray]:
    eligible = frame.event_observed.eq(1) | frame.duration_days.ge(horizon)
    label = (frame.event_observed.eq(1) & frame.duration_days.le(horizon)).astype(int)
    return eligible.to_numpy(), label.to_numpy()


class HorizonCalibrator:
    def __init__(self, method: str): self.method, self.models = method, []

    def fit(self, probabilities: np.ndarray, frame: pd.DataFrame) -> "HorizonCalibrator":
        self.models = []
        for index, horizon in enumerate(HORIZONS):
            eligible, label = _horizon_labels(frame, horizon)
            p = np.clip(probabilities[eligible, index], 1e-6, 1 - 1e-6)
            y = label[eligible]
            if self.method == "uncalibrated": model = None
            elif self.method == "isotonic": model = IsotonicRegression(out_of_bounds="clip").fit(p, y)
            elif self.method == "platt": model = LogisticRegression(C=1e3, random_state=SEED).fit(np.log(p / (1 - p))[:, None], y)
            elif self.method == "beta": model = LogisticRegression(C=100, random_state=SEED).fit(np.column_stack([np.log(p), -np.log(1 - p)]), y)
            else: raise ValueError(self.method)
            self.models.append(model)
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        out = np.zeros_like(probabilities)
        for index, model in enumerate(self.models):
            p = np.clip(probabilities[:, index], 1e-6, 1 - 1e-6)
            if self.method == "uncalibrated": q = p
            elif self.method == "isotonic": q = model.predict(p)
            elif self.method == "platt": q = model.predict_proba(np.log(p / (1 - p))[:, None])[:, 1]
            else: q = model.predict_proba(np.column_stack([np.log(p), -np.log(1 - p)]))[:, 1]
            out[:, index] = q
        # Separate horizon calibrators can cross.  Cumulative event risk cannot.
        return np.maximum.accumulate(np.clip(out, 0, 1), axis=1)
