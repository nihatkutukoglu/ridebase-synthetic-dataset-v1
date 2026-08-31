"""V2 survival inference for the dashboard API.

Thin adapter around ``ridebase_ml.v2.V2SurvivalPredictor`` (single source of inference
truth, shared with notebook 16). Loads the frozen FULL/FINAL bundle **once** at import
time; if anything is missing the API degrades gracefully (``/api/v2/*`` -> 503,
``/health`` shows the reason) while V1 keeps working.

Model status: SYNTHETICALLY VALIDATED (RideBase Synthetic Dataset v1.3). Real-fleet
validation PENDING — never presented as production-validated.
"""
from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import settings

log = logging.getLogger("ridebase.api.v2")

# make the `ridebase_ml` package importable without installing it. Prefer an explicit
# RIDEBASE_ML_ROOT, then the models dir's parent (repo layout / Docker /artifacts), then
# the repo root. If the package was `pip install`-ed this is all a no-op.
def _add_pkg_paths() -> None:
    import os

    candidates = [
        os.environ.get("RIDEBASE_ML_ROOT"),
        str(settings.MODEL_DIR.parent),
        str(settings.MODEL_DIR.parent.parent),
        str(settings.MODEL_DIR.parent.parent / "ridebase-ml"),
    ]
    for c in candidates:
        if c and (Path(c) / "ridebase_ml" / "__init__.py").exists() and c not in sys.path:
            sys.path.insert(0, c)


_add_pkg_paths()


class V2Unavailable(RuntimeError):
    """Raised when the V2 bundle could not be loaded."""


@lru_cache(maxsize=1)
def _load() -> Any:
    from ridebase_ml.v2 import V2SurvivalPredictor  # noqa: WPS433 - lazy import by design

    predictor = V2SurvivalPredictor.load(str(settings.MODEL_DIR), verify_checksums=True)
    log.info("V2 bundle loaded: %s | checksums=%s", predictor.bundle.model_name,
             predictor.bundle.checksum_status)
    return predictor


_STATE: dict[str, Any] = {"predictor": None, "error": None}


def init_v2() -> None:
    """Called once at app startup. Never raises."""
    try:
        _STATE["predictor"] = _load()
        _STATE["error"] = None
    except Exception as exc:  # pragma: no cover - env-dependent
        _STATE["predictor"] = None
        _STATE["error"] = f"{type(exc).__name__}: {exc}"
        log.warning("V2 bundle NOT loaded: %s", _STATE["error"])


def get_predictor() -> Any:
    if _STATE["predictor"] is None:
        init_v2()
    if _STATE["predictor"] is None:
        raise V2Unavailable(_STATE["error"] or "V2 bundle not loaded")
    return _STATE["predictor"]


def v2_loaded() -> bool:
    if _STATE["predictor"] is None and _STATE["error"] is None:
        init_v2()
    return _STATE["predictor"] is not None


def health_fields() -> dict[str, Any]:
    ok = v2_loaded()
    out: dict[str, Any] = {
        "v2_status": "ok" if ok else "unavailable",
        "v2_model_loaded": ok,
        "v2_calibrator_loaded": False,
        "v2_config_loaded": False,
    }
    if ok:
        p = _STATE["predictor"]
        out["v2_calibrator_loaded"] = bool(getattr(p, "_ensemble_ok", False))
        out["v2_config_loaded"] = bool(p.cfg)
        out["v2_model"] = p.bundle.model_name
        out["v2_dataset_version"] = p.bundle.dataset_version
        out["v2_run_mode"] = p.bundle.run_mode
        out["v2_model_validation"] = "SYNTHETICALLY_VALIDATED"
        out["v2_real_fleet_validation"] = "PENDING"
        out["v2_checksums"] = p.bundle.checksum_status
    else:
        out["v2_error"] = _STATE["error"]
    return out
