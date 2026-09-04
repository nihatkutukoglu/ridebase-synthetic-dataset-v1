"""Persistable model wrappers for the V2.2.1 offline experiment."""

from __future__ import annotations

import numpy as np


class StandardizedRiskBlendModel:
    """Blend two Cox risk rankings after TRAIN-only standardization."""

    def __init__(self, constrained, free, constrained_mean: float, constrained_std: float, free_mean: float, free_std: float, free_weight: float):
        self.constrained = constrained
        self.free = free
        self.constrained_mean = constrained_mean
        self.constrained_std = constrained_std
        self.free_mean = free_mean
        self.free_std = free_std
        self.free_weight = free_weight

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        constrained = (self.constrained.predict(matrix)-self.constrained_mean) / self.constrained_std
        free = (self.free.predict(matrix)-self.free_mean) / self.free_std
        return (1-self.free_weight)*constrained + self.free_weight*free

