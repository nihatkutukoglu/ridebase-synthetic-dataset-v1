"""/api/v3/* — V3 next-service-task prediction (synthetic product candidate).

V3 answers: "at the NEXT COMPLETED SERVICE, which maintenance tasks are most
likely to be performed?"

It does NOT answer, and must never be read as:
  * when the next service will occur          -> that is V2.1
  * whether maintenance is required now       -> that is deterministic Maintenance Due
  * how overdue maintenance is                -> that is deterministic Maintenance Urgency
  * probability of mechanical failure         -> V3 predicts work orders, not faults

No V3 probability is ever multiplied by, reconciled with, or adjusted using a
V2.1 horizon probability or a Maintenance Urgency score.

Status: V3 SYNTHETIC PRODUCT CANDIDATE — SYNTHETICALLY VALIDATED, REAL FLEET
VALIDATION PENDING.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from .config import settings
from .v3_schemas import (V3BatchPredictRequest, V3ByMotorcycleRequest,
                         V3PredictRequest)
from .v3_service import (MAX_BATCH, V3Unavailable, frozen_metrics,
                         get_history_adapter, get_predictor,
                         predict_by_motorcycle)

v3 = APIRouter(prefix="/api/v3", tags=["v3"])

_MODEL_DIR = settings.MODEL_DIR / "v3_research"
_SYNTH_WARNING = (
    "SENTETİK VERİDE DOĞRULANDI. GERÇEK FİLO DOĞRULAMASI BEKLENİYOR. "
    "V3 is SYNTHETICALLY VALIDATED on RideBase Synthetic Dataset v1.4 only — "
    "not production-validated."
)
_MEANING = (
    "probability that the task appears on the work order of the next COMPLETED "
    "service — NOT a mechanical failure probability, NOT a maintenance-urgency "
    "score, and NOT a V2.1 service-return probability"
)


def _pred():
    try:
        return get_predictor()
    except V3Unavailable as exc:
        raise HTTPException(status_code=503, detail=f"V3 model unavailable: {exc}")


def _adapter():
    try:
        return get_history_adapter()
    except V3Unavailable as exc:
        raise HTTPException(status_code=503, detail=f"V3 history source unavailable: {exc}")


def _decorate(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload["warning"] = _SYNTH_WARNING
    payload["probability_meaning"] = _MEANING
    return payload


@v3.get("/model/info")
def model_info() -> Dict[str, Any]:
    p = _pred()
    man = p.manifest
    return _decorate({
        "model_version": man.get("model_version"),
        "status": "V3_SYNTHETIC_PRODUCT_CANDIDATE",
        "validation_scope": "SYNTHETIC_ONLY",
        "real_fleet_validation": "PENDING",
        "deployed_as_production_model": False,
        "champion_family": man.get("champion_family"),
        "source_world": man.get("source_world"),
        "landmark_strategy": man.get("landmark_strategy"),
        "seed": man.get("seed"),
        "feature_count": len(p.feature_cols),
        "label_count": len(p.labels),
        "threshold_policy": man.get("threshold_policy"),
        "threshold": float(p.thresholds[0]),
        "calibration_policy": man.get("calibration_policy"),
        "question": ("at the next completed service, which maintenance tasks are "
                     "most likely to be performed?"),
        "does_not_predict": [
            "when the next service occurs (V2.1)",
            "whether maintenance is required (deterministic Maintenance Due)",
            "how overdue maintenance is (deterministic Maintenance Urgency)",
            "mechanical failure probability",
        ],
        "scenario_route_implemented": False,
        "scenario_route_reason": ("80.5% of the frozen feature contract depends on "
                                  "per-task service history that natural inputs cannot "
                                  "supply — see reports/v3_product/09_scenario_feasibility.md"),
    })


@v3.get("/labels")
def labels() -> Dict[str, Any]:
    """The V3 task taxonomy plus the presentation policy and frozen per-label metrics."""
    p = _pred()
    policy = p.label_policy
    rows = []
    for code in p.labels:
        pol = policy.get(code)
        if pol is None:
            continue
        rows.append({
            "task_code": code,
            "display_name": pol.display_name_tr,
            "display_name_en": pol.display_name_en,
            "component_group": pol.component_group,
            "product_status": pol.product_status,
            "support_class": pol.support_class,
            "generating_process": pol.generating_process,
            "test_support": pol.test_support,
            "test_prevalence": pol.test_prevalence,
            "test_pr_auc": pol.test_pr_auc,
            "threshold": float(p.thresholds[p.labels.index(code)]),
            "note": pol.note,
        })
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["product_status"]] = counts.get(r["product_status"], 0) + 1
    return _decorate({
        "label_count": len(rows),
        "product_status_counts": counts,
        "presentation_only": True,
        "presentation_note": ("product_status governs presentation only; every label "
                              "remains in the model and in all_task_probabilities"),
        "labels": rows,
    })


@v3.get("/metrics")
def metrics() -> Dict[str, Any]:
    """Frozen synthetic TEST metrics, read from the artifact. Never hard-coded."""
    try:
        return _decorate(frozen_metrics())
    except V3Unavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@v3.get("/sample")
def sample() -> Dict[str, Any]:
    """A real motorcycle_id + landmark_date pair that POST /predict/by-motorcycle accepts.

    Input only: no task list, no target service, no label is returned. The pair is
    drawn from the frozen V3 TEST split so it is guaranteed resolvable by the
    history adapter.
    """
    import pandas as pd

    path = _MODEL_DIR.parent.parent / "derived_outputs" / "v3" / "v3_sample_landmarks.parquet"
    if not path.exists():
        raise HTTPException(status_code=503, detail="V3 sample index not available")
    frame = pd.read_parquet(path)
    row = frame.sample(1).iloc[0]
    return _decorate({
        "motorcycle_id": str(row["motorcycle_id"]),
        "landmark_date": pd.to_datetime(row["landmark_at"]).date().isoformat(),
        "split": str(row["v3_split"]),
        "note": ("Input only — a valid POST /predict/by-motorcycle payload. "
                 "No target service and no task labels are exposed."),
    })


def _one(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _decorate(payload)


@v3.post("/predict")
def predict(req: V3PredictRequest) -> Dict[str, Any]:
    """Predict from a complete frozen feature row. ML-facing, not a product surface."""
    import pandas as pd

    from ridebase_ml.v3.predictor import V3PredictionError

    p = _pred()
    try:
        frame = pd.DataFrame([dict(req.features)])
        ids = [req.motorcycle_id] if req.motorcycle_id else None
        result = p.predict_product(frame, ids, top_k=req.top_k,
                                   landmark_dates=[req.landmark_date],
                                   include_hidden=req.include_hidden)[0]
    except V3PredictionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"{type(exc).__name__}: {exc}")
    result["input_source"] = "CALLER_SUPPLIED_FEATURES"
    return _one(result)


@v3.post("/predict/batch")
def predict_batch(req: V3BatchPredictRequest) -> Dict[str, Any]:
    import pandas as pd

    from ridebase_ml.v3.predictor import V3PredictionError

    if len(req.rows) > MAX_BATCH:
        raise HTTPException(status_code=413, detail=f"batch limit is {MAX_BATCH} rows")
    if req.motorcycle_ids is not None and len(req.motorcycle_ids) != len(req.rows):
        raise HTTPException(status_code=422,
                            detail="motorcycle_ids must be the same length as rows")
    p = _pred()
    started = time.perf_counter()
    try:
        frame = pd.DataFrame([dict(r) for r in req.rows])
        results = p.predict_product(frame, req.motorcycle_ids, top_k=req.top_k,
                                    include_hidden=req.include_hidden)
    except V3PredictionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"{type(exc).__name__}: {exc}")
    return _decorate({
        "count": len(results),
        "predictions": results,
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
    })


@v3.post("/predict/by-motorcycle")
def predict_by_motorcycle_route(req: V3ByMotorcycleRequest) -> Dict[str, Any]:
    """Primary product flow: ID + landmark date -> PIT history -> frozen V3."""
    from ridebase_ml.v2_1.adapters.base import SourceContractError
    from ridebase_ml.v2_1.source_contract import (HistoryInputError,
                                                  UnknownMotorcycleError)

    adapter = _adapter()
    if not adapter.motorcycle_exists(req.motorcycle_id):
        raise HTTPException(status_code=404,
                            detail=f"unknown motorcycle_id {req.motorcycle_id!r}")
    try:
        result = predict_by_motorcycle(req.motorcycle_id, req.landmark_date,
                                       top_k=req.top_k, include_hidden=req.include_hidden)
    except UnknownMotorcycleError as exc:
        # known bike, but the landmark predates its observation window
        raise HTTPException(status_code=422, detail=str(exc))
    except (HistoryInputError, SourceContractError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except V3Unavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _one(result)
