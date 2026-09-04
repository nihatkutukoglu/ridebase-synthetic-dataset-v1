"""Persistable censor-aware discrete-time hazard model."""

from __future__ import annotations

import numpy as np
import pandas as pd


HORIZONS = np.array([30, 60, 90, 120], dtype=int)


class DiscreteHazardModel:
    def __init__(self, preprocessor, estimator, features: list[str]):
        self.preprocessor = preprocessor
        self.estimator = estimator
        self.features = list(features)

    def _design(self, frame: pd.DataFrame) -> np.ndarray:
        base = self.preprocessor.transform(frame[self.features]).astype(np.float32)
        blocks = [np.column_stack([base, np.full(len(frame), i, dtype=np.float32)]) for i in range(4)]
        return np.vstack(blocks)

    def predict_hazards(self, frame: pd.DataFrame) -> np.ndarray:
        values = self.estimator.predict_proba(self._design(frame))[:, 1]
        return values.reshape(4, len(frame)).T

    def predict_probability(self, frame: pd.DataFrame) -> np.ndarray:
        hazards = np.clip(self.predict_hazards(frame), 1e-7, 1-1e-7)
        return np.maximum.accumulate(1-np.cumprod(1-hazards, axis=1), axis=1)

    def predict_score(self, frame: pd.DataFrame) -> np.ndarray:
        probability = self.predict_probability(frame)
        return probability @ np.array([4., 3., 2., 1.])
