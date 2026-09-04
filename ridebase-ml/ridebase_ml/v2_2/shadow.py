"""Offline-only loader for the frozen V2.2 challenger package.

This module is intentionally not wired into the backend or Control Center.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ridebase_ml.v2_1.survival import HORIZONS, _survival_from_score
from ridebase_ml.v2_2.landmarks import FEATURE_COLUMNS


class V22ShadowPredictor:
    """Load and score the accepted V2.2 package without production promotion."""

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir).resolve()
        card = json.loads((self.model_dir / "model_card.json").read_text())
        if card["deployment_status"] != "OFFLINE_SHADOW_ONLY":
            raise RuntimeError("V2.2 package is not marked OFFLINE_SHADOW_ONLY")
        self.card = card
        self.preprocessor = joblib.load(self.model_dir / "preprocessor.joblib")
        self.model = joblib.load(self.model_dir / "challenger_model.joblib")
        self.baseline = joblib.load(self.model_dir / "baseline_hazard.joblib")
        self.calibrator = joblib.load(self.model_dir / "calibrator.joblib")

    def predict(self, rows: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        missing = [name for name in FEATURE_COLUMNS if name not in rows.columns]
        if missing:
            raise ValueError(f"Missing V2.2 features: {missing}")
        warnings: list[str] = []
        annual = pd.to_numeric(rows["annual_km_baseline"], errors="coerce")
        if annual.isna().any() or ((annual < 1000) | (annual > 60000)).any():
            warnings.append("annual_km_baseline is outside the V1.5 audit support range [1k, 60k]")
        if pd.to_numeric(rows["max_due_ratio"], errors="coerce").gt(4).any():
            warnings.append("max_due_ratio exceeds the controlled audit range")
        matrix = self.preprocessor.transform(rows[FEATURE_COLUMNS]).astype(np.float32)
        score = self.model.predict(matrix)
        probability = self.calibrator.transform(1 - _survival_from_score(score, self.baseline))
        result = pd.DataFrame({"risk_score": score}, index=rows.index)
        for index, horizon in enumerate(HORIZONS.astype(int)):
            result[f"return_probability_{horizon}d"] = probability[:, index]
        return result, warnings


def package_metadata() -> dict[str, Any]:
    return {
        "model": "V2.2 challenger",
        "semantics": "probability of eligible service return after landmark; not maintenance need",
        "real_fleet_validation": "PENDING",
        "production_promotion": False,
    }
