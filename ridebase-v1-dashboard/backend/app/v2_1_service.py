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
import time
from typing import Any

from .config import settings
from .v2_service import _add_pkg_paths  # same repo-layout sys.path shim as V2.0

log = logging.getLogger("ridebase.api.v2_1")

_MODEL_DIR = settings.MODEL_DIR / "v2_1_v1_4"
_STATE: dict[str, Any] = {
    "predictor": None,
    "error": None,
    "history_adapter": None,
    "history_error": None,
}


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


def init_v2_1_history() -> None:
    """Initialize the read-only synthetic source adapter. Never raises."""
    _add_pkg_paths()
    try:
        from ridebase_ml.v2_1.adapters.synthetic import SyntheticRideBaseSourceAdapter

        _STATE["history_adapter"] = SyntheticRideBaseSourceAdapter(
            settings.V2_1_HISTORY_SOURCE_DIR,
            settings.V2_1_HISTORY_SCHEMA_CONTRACT,
        )
        _STATE["history_error"] = None
        log.info("V2.1 history adapter ready from %s", settings.V2_1_HISTORY_SOURCE_DIR)
    except Exception as exc:  # pragma: no cover - environment-dependent
        _STATE["history_adapter"] = None
        _STATE["history_error"] = f"{type(exc).__name__}: {exc}"
        log.warning("V2.1 history adapter NOT ready: %s", _STATE["history_error"])


def get_predictor() -> Any:
    if _STATE["predictor"] is None and _STATE["error"] is None:
        init_v2_1()
    if _STATE["predictor"] is None:
        raise V21Unavailable(_STATE["error"] or "V2.1 artifacts not loaded")
    return _STATE["predictor"]


def get_history_adapter() -> Any:
    if _STATE["history_adapter"] is None and _STATE["history_error"] is None:
        init_v2_1_history()
    if _STATE["history_adapter"] is None:
        raise V21Unavailable(_STATE["history_error"] or "V2.1 history adapter not loaded")
    return _STATE["history_adapter"]


def predict_by_motorcycle(motorcycle_id: str, landmark_date: Any) -> dict[str, Any]:
    """Direct history-builder + frozen-predictor flow shared by API parity tests."""
    from ridebase_ml.v2_1.history_features import build_features

    adapter = get_history_adapter()
    predictor = get_predictor()
    started = time.perf_counter()
    built = build_features(motorcycle_id, landmark_date, adapter)
    built_ms = (time.perf_counter() - started) * 1000.0
    predict_started = time.perf_counter()
    prediction = predictor.predict([built["features"]], strict=True)
    predict_ms = (time.perf_counter() - predict_started) * 1000.0
    return {
        "built": built,
        "prediction": prediction["predictions"][0],
        "history_build_ms": round(built_ms, 3),
        "prediction_ms": round(predict_ms, 3),
        "total_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }


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
    if _STATE["history_adapter"] is None and _STATE["history_error"] is None:
        init_v2_1_history()
    history_ok = _STATE["history_adapter"] is not None
    out["v2_1_history_status"] = "ok" if history_ok else "unavailable"
    out["v2_1_history_source"] = "SYNTHETIC_V1_4" if history_ok else None
    if not history_ok:
        out["v2_1_history_error"] = _STATE["history_error"]
    return out
