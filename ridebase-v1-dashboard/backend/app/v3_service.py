"""V3 next-service-task inference for the dashboard API.

Thin adapter around ``ridebase_ml.v3.predictor.V3TaskPredictor`` and the V3
serving feature builder. Loads the frozen research artifacts
(``ridebase-ml/models/v3_research/``) ONCE at startup; if anything is missing the
API degrades gracefully (``/api/v3/*`` -> 503, ``/health`` shows why) while V1,
V2.0 and V2.1 keep working exactly as before.

V3 reuses the **V2.1 read-only history adapter** rather than introducing a second
source of truth: the same audited, point-in-time-safe store already serving
``/api/v2_1/predict/by-motorcycle`` supplies the services and task lines V3 needs.

Status: V3 SYNTHETIC PRODUCT CANDIDATE — SYNTHETICALLY VALIDATED, REAL FLEET
VALIDATION PENDING. Nothing here is presented as production-validated, and no V3
probability is ever combined with a V2.1 probability or a Maintenance Urgency
score.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from .config import settings
from .v2_service import _add_pkg_paths

log = logging.getLogger("ridebase.api.v3")

_MODEL_DIR = settings.MODEL_DIR / "v3_research"
#: hard cap on a batch request; keeps memory and latency bounded
MAX_BATCH = 100

_STATE: dict[str, Any] = {"predictor": None, "error": None, "loaded_ms": None}


class V3Unavailable(RuntimeError):
    """Raised when the frozen V3 artifacts could not be loaded."""


def init_v3() -> None:
    """Called once at app startup. Never raises."""
    if not settings.V3_ENABLED:
        _STATE["predictor"] = None
        _STATE["error"] = "disabled by V3_ENABLED=false"
        log.info("V3 disabled by configuration (V3_ENABLED=false)")
        return
    _add_pkg_paths()
    started = time.perf_counter()
    try:
        from ridebase_ml.v3.predictor import V3TaskPredictor

        _STATE["predictor"] = V3TaskPredictor.load(_MODEL_DIR)
        _STATE["error"] = None
        _STATE["loaded_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        log.info("V3 predictor loaded from %s in %sms", _MODEL_DIR, _STATE["loaded_ms"])
    except Exception as exc:  # pragma: no cover - env-dependent
        _STATE["predictor"] = None
        _STATE["error"] = f"{type(exc).__name__}: {exc}"
        log.warning("V3 predictor NOT loaded: %s", _STATE["error"])


def get_predictor() -> Any:
    if not settings.V3_ENABLED:
        raise V3Unavailable("V3 is disabled on this deployment (V3_ENABLED=false)")
    if _STATE["predictor"] is None and _STATE["error"] is None:
        init_v3()
    if _STATE["predictor"] is None:
        raise V3Unavailable(_STATE["error"] or "V3 artifacts not loaded")
    return _STATE["predictor"]


def v3_loaded() -> bool:
    if not settings.V3_ENABLED:
        return False
    if _STATE["predictor"] is None and _STATE["error"] is None:
        init_v3()
    return _STATE["predictor"] is not None


def get_history_adapter() -> Any:
    """V3 shares V2.1's read-only history adapter -- one audited source, not two."""
    from .v2_1_service import V21Unavailable, get_history_adapter as v2_1_adapter

    try:
        return v2_1_adapter()
    except V21Unavailable as exc:
        raise V3Unavailable(f"shared V2.1 history source unavailable: {exc}")


def predict_by_motorcycle(motorcycle_id: str, landmark_date: Any,
                          top_k: int = 3, include_hidden: bool = False) -> dict[str, Any]:
    """ID + date -> PIT history -> frozen 277 features -> frozen V3 predictor."""
    from ridebase_ml.v3.serving import build_v3_features

    predictor = get_predictor()
    adapter = get_history_adapter()

    started = time.perf_counter()
    vector = build_v3_features(motorcycle_id, landmark_date, adapter,
                               predictor.labels, predictor.feature_cols)
    built_ms = (time.perf_counter() - started) * 1000.0

    frame = vector.to_frame(predictor.feature_cols)
    predict_started = time.perf_counter()
    payload = predictor.predict_product(
        frame, [motorcycle_id], top_k=top_k, landmark_dates=[landmark_date],
        feature_coverage=[vector.coverage], include_hidden=include_hidden,
        extra_warnings=[vector.warnings])[0]
    predict_ms = (time.perf_counter() - predict_started) * 1000.0

    payload["input_source"] = "SYNTHETIC_HISTORY_V1_4"
    payload["motorcycle_id"] = motorcycle_id
    payload["history_provenance"] = vector.provenance
    payload["missing_features"] = vector.missing[:20]
    payload["timing_ms"] = {
        "history_build": round(built_ms, 2),
        "prediction": round(predict_ms, 2),
        "total": round((time.perf_counter() - started) * 1000.0, 2),
    }
    return payload


def frozen_metrics() -> dict[str, Any]:
    """Frozen synthetic TEST metrics, read from the artifact. Never hard-coded."""
    path = _MODEL_DIR / "test_evaluation.json"
    if not path.exists():
        raise V3Unavailable("V3 test_evaluation.json artifact not present")
    report = json.loads(path.read_text())
    test, unseen = report.get("TEST", {}), report.get("UNSEEN_MOTORCYCLE_TEST", {})
    keys = ("micro_f1", "macro_f1", "weighted_f1", "micro_pr_auc",
            "mean_average_precision", "precision_at_1", "precision_at_3",
            "recall_at_3", "precision_at_5", "recall_at_5", "hamming_loss")
    return {
        "validation_scope": "SYNTHETIC_ONLY",
        "real_fleet_validation": "PENDING",
        "dataset": "RideBase Synthetic Dataset v1.4 / V2.1 landmark grid",
        "test": {k: test.get(k) for k in keys},
        "unseen_motorcycle_test": {k: unseen.get(k) for k in keys},
        "unseen_motorcycle_test_rows": unseen.get("rows"),
        "subgroups": report.get("subgroups"),
        "metric_notes": {
            "precision_at_1": ("share of landmarks where the highest-ranked task was "
                               "actually performed at the next completed service. This is "
                               "a ranking metric, NOT an accuracy figure."),
            "mean_average_precision": "macro-averaged PR-AUC across labels with positives",
            "macro_f1": ("low by design: a single global threshold under-serves the "
                         "low-frequency labels, which are meant to be read as "
                         "probabilities and ranks rather than binary flags"),
        },
        "test_first_touch": report.get("test_first_touch"),
    }


def health_fields() -> dict[str, Any]:
    ok = v3_loaded()
    out: dict[str, Any] = {
        "v3_status": "ok" if ok else ("disabled" if not settings.V3_ENABLED else "unavailable"),
        "v3_model_loaded": ok,
        "v3_enabled": settings.V3_ENABLED,
    }
    if ok:
        p = _STATE["predictor"]
        out.update({
            "v3_champion": p.manifest.get("champion_family"),
            "v3_label_count": len(p.labels),
            "v3_feature_count": len(p.feature_cols),
            "v3_model_validation": "SYNTHETICALLY_VALIDATED",
            "v3_real_fleet_validation": "PENDING",
            "v3_load_ms": _STATE["loaded_ms"],
        })
    else:
        out["v3_error"] = _STATE["error"]
    return out
