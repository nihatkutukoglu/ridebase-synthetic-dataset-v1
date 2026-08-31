"""RideBase V2 survival — production inference package.

Loads the frozen FULL/FINAL ensemble (XGBoost survival:cox + CoxNet, per-horizon
IPCW-isotonic calibrated) and serves deterministic 30/60/90/120-day service
probabilities. No training. Model status: SYNTHETICALLY VALIDATED (v1.3); real-fleet
validation PENDING.
"""
from .loader import V2Bundle, load_bundle, model_metadata, sha256
from .predictor import PredictionError, V2SurvivalPredictor

__all__ = [
    "V2SurvivalPredictor",
    "PredictionError",
    "V2Bundle",
    "load_bundle",
    "model_metadata",
    "sha256",
]
