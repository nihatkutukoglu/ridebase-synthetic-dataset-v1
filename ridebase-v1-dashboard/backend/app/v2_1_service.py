"""V2.1 dynamic-landmark survival inference for the dashboard API.

Thin adapter around ``ridebase_ml.v2_1.V21SurvivalPredictor`` (single inference
source of truth, shared with the training/golden-parity module). Loads the frozen
Phase-3 artifacts (``ridebase-ml/models/v2_1_v1_4/``) once; if anything is missing
the API degrades gracefully (``/api/v2_1/*`` -> 503, ``/health`` shows why) while
V1 and V2.0 keep working.

Status: SYNTHETICALLY VALIDATED (RideBase Synthetic Dataset v1.4 / V2.1 landmarks).
Real-fleet validation PENDING — never presented as production-validated.
"""
from __future__ import annotations

import logging
from typing import Any

from .config import settings
from .v2_service import _add_pkg_paths  # same repo-layout sys.path shim as V2.0

log = logging.getLogger("ridebase.api.v2_1")

_MODEL_DIR = settings.MODEL_DIR / "v2_1_v1_4"
_STATE: dict[str, Any] = {"predictor": None, "error": None}


class V21Unavailable(RuntimeError):
    """Raised when the V2.1 artifacts could not be loaded."""


def init_v2_1() -> None:
    """Called once at app startup. Never raises."""
    _add_pkg_paths()
    try:
        from ridebase_ml.v2_1.predictor import V21SurvivalPredictor

        _STATE["predictor"] = V21SurvivalPredictor.load(_MODEL_DIR)
        _STATE["error"] = None
        log.info("V2.1 predictor loaded from %s", _MODEL_DIR)
    except Exception as exc:  # pragma: no cover - env-dependent
        _STATE["predictor"] = None
        _STATE["error"] = f"{type(exc).__name__}: {exc}"
        log.warning("V2.1 predictor NOT loaded: %s", _STATE["error"])


def get_predictor() -> Any:
    if _STATE["predictor"] is None and _STATE["error"] is None:
        init_v2_1()
    if _STATE["predictor"] is None:
        raise V21Unavailable(_STATE["error"] or "V2.1 artifacts not loaded")
    return _STATE["predictor"]


def v2_1_loaded() -> bool:
    if _STATE["predictor"] is None and _STATE["error"] is None:
        init_v2_1()
    return _STATE["predictor"] is not None


def health_fields() -> dict[str, Any]:
    ok = v2_1_loaded()
    out: dict[str, Any] = {"v2_1_status": "ok" if ok else "unavailable", "v2_1_model_loaded": ok}
    if ok:
        info = _STATE["predictor"].model_info()
        out["v2_1_champion"] = info["champion"]
        out["v2_1_calibration_method"] = info["calibration_method"]
        out["v2_1_dataset_version"] = info["dataset_version"]
        out["v2_1_model_validation"] = "SYNTHETICALLY_VALIDATED"
        out["v2_1_real_fleet_validation"] = "PENDING"
    else:
        out["v2_1_error"] = _STATE["error"]
    return out
