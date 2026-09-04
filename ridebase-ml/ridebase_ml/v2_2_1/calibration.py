"""Calibration variants for the offline V2.2.1 recovery challenger."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ridebase_ml.v2_1.survival import HorizonCalibrator


class BlendedHorizonCalibrator:
    """Blend isotonic calibration with a smooth beta map to retain resolution."""

    def __init__(self, isotonic_weight: float = 0.75):
        self.isotonic_weight = isotonic_weight
        self.isotonic = HorizonCalibrator("isotonic")
        self.beta = HorizonCalibrator("beta")
        self.method = f"isotonic_beta_blend_{isotonic_weight:.2f}"

    def fit(self, probabilities: np.ndarray, frame: pd.DataFrame) -> "BlendedHorizonCalibrator":
        self.isotonic.fit(probabilities, frame)
        self.beta.fit(probabilities, frame)
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        iso = self.isotonic.transform(probabilities)
        beta = self.beta.transform(probabilities)
        blended = self.isotonic_weight * iso + (1-self.isotonic_weight) * beta
        return np.maximum.accumulate(np.clip(blended, 0, 1), axis=1)

