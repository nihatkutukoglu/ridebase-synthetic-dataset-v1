"""/api/v2_1/* — V2.1 dynamic-landmark survival service.

Serves calibrated 30/60/90/120-day *service-return* probabilities anchored to a
landmark date, from the frozen Phase-3 champion (xgb_cox + isotonic). Separate
from /api/v2/* — V1 and V2.0 routes are untouched.

Risk = probability the next eligible DELIVERED service occurs within the horizon,
measured from the landmark. It is NOT maintenance-due probability.

Status: SYNTHETICALLY VALIDATED (RideBase Synthetic Dataset v1.4 / V2.1 landmarks).
Real-fleet validation PENDING.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from .config import settings
from .v2_1_schemas import (V21BatchPredictRequest, V21ByMotorcycleRequest,
                           V21PredictRequest, V21ScenarioRequest)
from .v2_1_service import (V21Unavailable, get_history_adapter, get_predictor,
                           predict_by_motorcycle)

v2_1 = APIRouter(prefix="/api/v2_1", tags=["v2_1"])

_SYNTH_WARNING = ("SENTETİK VERİDE DOĞRULANDI. GERÇEK RIDEBASE FİLO TESTİ BEKLENİYOR. "
                  "This model is SYNTHETICALLY VALIDATED on RideBase Synthetic Dataset "
                  "v1.4 (V2.1 landmarks) only — not production-validated.")
_MODEL_DIR = settings.MODEL_DIR / "v2_1_v1_4"


def _pred():
    try:
        return get_predictor()
    except V21Unavailable as exc:
        raise HTTPException(status_code=503, detail=f"V2.1 model unavailable: {exc}")


def _predict_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _history_adapter():
    try:
        return get_history_adapter()
    except V21Unavailable as exc:
        raise HTTPException(status_code=503, detail=f"V2.1 history source unavailable: {exc}")


@v2_1.get("/model/info")
def model_info() -> Dict[str, Any]:
    return {**_pred().model_info(), "warning": _SYNTH_WARNING}


@v2_1.get("/features")
def features() -> Dict[str, Any]:
    return _pred().features()


@v2_1.get("/metrics")
def metrics() -> Dict[str, Any]:
    """Artifact-driven — the frozen models/v2_1_v1_4/metrics.json. No hard-coded numbers."""
    path = _MODEL_DIR / "metrics.json"
    if not path.exists():
        raise HTTPException(status_code=503, detail="V2.1 metrics artifact not present")
    report = json.loads(path.read_text())
    parity = _MODEL_DIR / "golden_parity.json"
    return {
        "status": report.get("status"),
        "gate_checks": report.get("gate_checks"),
        "selected": report.get("selected"),
        "test_metrics": report.get("test_metrics"),
        "unseen_motorcycle_metrics": report.get("unseen_motorcycle_metrics"),
        "grouped_bootstrap": report.get("grouped_bootstrap"),
        "p30_distribution": report.get("p30_distribution"),
        "metamorphic_audit": report.get("metamorphic_audit", {}).get("checks"),
        "feature_importance_top20": report.get("feature_importance_top20"),
        "calibration_comparison": report.get("calibration_comparison"),
        "golden_prediction_parity": json.loads(parity.read_text()) if parity.exists() else None,
        "model_validation": "SYNTHETICALLY_VALIDATED",
        "real_fleet_validation": "PENDING",
    }


@v2_1.get("/sample")
def sample() -> Dict[str, Any]:
    """A frozen TEST landmark's feature row, for wiring up POST /predict. Targets excluded."""
    import pandas as pd

    p = _pred()
    table = _MODEL_DIR.parent.parent / "derived_outputs" / "v2_1_v1_4" / "v2_1_modeling_table.parquet"
    if not table.exists():
        raise HTTPException(status_code=404, detail="V2.1 modeling table not available for a sample")
    frame = pd.read_parquet(table, filters=[("modeling_role", "==", "TEST")],
                            columns=["landmark_id", "landmark_at", "motorcycle_id", *p.feature_cols])
    row = frame.sample(1).iloc[0]
    feats: Dict[str, Any] = {}
    for col in p.feature_cols:
        val = row[col]
        if pd.isna(val):
            continue
        feats[col] = (bool(val) if isinstance(val, bool)
                      else float(val) if hasattr(val, "__float__") and not isinstance(val, str)
                      else str(val))
    return {"landmark_id": str(row["landmark_id"]),
            "landmark_at": pd.to_datetime(row["landmark_at"]).date().isoformat(),
            # this motorcycle_id/landmark_at pair is also a valid POST /predict/by-motorcycle input,
            # since both are built from the same V1.4 source history (K2)
            "motorcycle_id": str(row["motorcycle_id"]),
            "features": feats,
            "note": "Frozen TEST landmark; survival targets are excluded."}


def _shape_one(pred: Dict[str, Any], p) -> Dict[str, Any]:
    body = {
        "risk_30d": pred["risk_30d"], "risk_60d": pred["risk_60d"],
        "risk_90d": pred["risk_90d"], "risk_120d": pred["risk_120d"],
        "median_service_days": pred["median_service_days"],
        "risk_score": pred["risk_score"],
    }
    out: Dict[str, Any] = {"prediction": body, "model": p.model_info()}
    if pred.get("warnings"):
        out["warnings"] = pred["warnings"]
    out["warning"] = _SYNTH_WARNING
    out["risk_meaning"] = ("probability of an eligible real service return within the horizon, "
                           "measured from the landmark — NOT maintenance-needed probability")
    return out


@v2_1.post("/predict")
def predict(req: V21PredictRequest) -> Dict[str, Any]:
    p = _pred()
    try:
        result = p.predict([dict(req.features)], strict=req.strict)
    except Exception as exc:
        raise _predict_error(exc)
    shaped = _shape_one(result["predictions"][0], p)
    shaped["latency_ms"] = result["latency_ms"]
    return shaped


@v2_1.post("/predict/batch")
def predict_batch(req: V21BatchPredictRequest) -> Dict[str, Any]:
    p = _pred()
    if not req.items:
        raise HTTPException(status_code=422, detail="items must be a non-empty list")
    try:
        result = p.predict([dict(x) for x in req.items], strict=req.strict)
    except Exception as exc:
        raise _predict_error(exc)
    preds = []
    for pr in result["predictions"]:
        row = {k: pr[k] for k in ("risk_30d", "risk_60d", "risk_90d", "risk_120d",
                                  "median_service_days", "risk_score")}
        if pr.get("warnings"):
            row["warnings"] = pr["warnings"]
        preds.append(row)
    return {"n": result["n"], "predictions": preds, "model": p.model_info(),
            "warning": _SYNTH_WARNING, "latency_ms": result["latency_ms"]}


@v2_1.post("/predict/scenario")
def predict_scenario(req: V21ScenarioRequest) -> Dict[str, Any]:
    """KISMİ BİLGİYLE SENARYO TAHMİNİ — resolves only genuinely knowable features;
    the rest stay missing for the frozen preprocessor. No demo-sample overlay."""
    p = _pred()
    try:
        from ridebase_ml.v2_1.scenario import ScenarioInputError, derive
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"scenario derivation unavailable: {exc}")
    payload = req.model_dump()
    payload["landmark_date"] = req.landmark_date.isoformat()
    if req.last_service_date:
        payload["last_service_date"] = req.last_service_date.isoformat()
    # source catalog dir: same frozen tables the backend already ships
    # (Dockerfile.prod copies them to /app/app/data/; v1.3 == v1.4 for these files)
    src_dir = settings.MODEL_CATALOG_PATH.parent
    try:
        derived = derive(payload, source_dir=src_dir if (src_dir / "maintenance_policies.csv").exists() else None)
        result = p.predict([derived["features"]], strict=False)
    except ScenarioInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise _predict_error(exc)
    shaped = _shape_one(result["predictions"][0], p)
    shaped["mode"] = "KISMİ BİLGİYLE SENARYO TAHMİNİ"
    shaped["provenance"] = derived["provenance"]
    shaped["resolved_features"] = derived["features"]
    shaped["feature_coverage"] = {
        "resolved": len(derived["features"]),
        "contract": len(p.feature_cols),
        "note": "coverage is not a confidence score",
    }
    shaped["latency_ms"] = result["latency_ms"]
    return shaped


@v2_1.post("/predict/by-motorcycle")
def predict_by_motorcycle_route(req: V21ByMotorcycleRequest) -> Dict[str, Any]:
    """Synthetic-history mode: ID + date -> frozen 54 features -> frozen V2.1."""
    from ridebase_ml.v2_1.adapters.base import SourceContractError
    from ridebase_ml.v2_1.source_contract import HistoryInputError, UnknownMotorcycleError

    started = time.perf_counter()
    adapter = _history_adapter()
    if not adapter.motorcycle_exists(req.motorcycle_id):
        raise HTTPException(status_code=404, detail=f"unknown motorcycle_id {req.motorcycle_id!r}")
    try:
        result = predict_by_motorcycle(req.motorcycle_id, req.landmark_date)
    except UnknownMotorcycleError as exc:
        # Identifier exists, but it was not observable yet at this landmark.
        raise HTTPException(status_code=422, detail=str(exc))
    except HistoryInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SourceContractError as exc:
        raise HTTPException(status_code=503, detail=f"history source contract failure: {exc}")
    except V21Unavailable as exc:
        raise HTTPException(status_code=503, detail=f"V2.1 unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"history prediction unavailable: {exc}")

    built = result["built"]
    pred = result["prediction"]
    evidence = built["source_evidence"]
    last_service = evidence["last_eligible_service"]
    resolved = built["feature_coverage"]["resolved_features"]
    provenance_summary = Counter(built["provenance"][name] for name in resolved)
    warnings = [*built["warnings"], *pred.get("warnings", [])]
    return {
        "mode": "HISTORY_PIPELINE",
        "history_source": "SYNTHETIC_V1_4",
        "prediction": {
            name: pred[name] for name in (
                "risk_30d", "risk_60d", "risk_90d", "risk_120d",
                "median_service_days", "risk_score",
            )
        },
        "context": {
            "motorcycle_id": req.motorcycle_id,
            "landmark_date": req.landmark_date.isoformat(),
            "current_odometer_km": built["features"]["current_odometer_km_at_landmark"],
            "current_odometer_source_date": (
                evidence["current_odometer_source"]["period_end_date"]
                if evidence["current_odometer_source"] else None
            ),
            "last_eligible_service_date": last_service["received_date"] if last_service else None,
            "last_service_odometer_km": last_service["odometer_km"] if last_service else None,
        },
        "feature_metadata": {
            "resolved_count": built["feature_coverage"]["resolved_count"],
            "contract_count": built["feature_coverage"]["contract_count"],
            "missing_features": built["feature_coverage"]["missing_features"],
            "provenance_summary": dict(sorted(provenance_summary.items())),
            "coverage_ratio": built["feature_coverage"]["ratio"],
            "coverage_is_confidence": False,
        },
        "warnings": warnings,
        "warning": _SYNTH_WARNING,
        "model_status": "V2.1 EXPERIMENTAL LIVE",
        "model_validation": "SYNTHETICALLY_VALIDATED",
        "real_fleet_validation": "PENDING",
        "risk_meaning": (
            "service-return probability within each horizon, measured from the landmark; "
            "NOT maintenance-needed probability"
        ),
        "latency_ms": {
            "history_build": result["history_build_ms"],
            "prediction": result["prediction_ms"],
            "total_service": result["total_ms"],
            "total_route": round((time.perf_counter() - started) * 1000.0, 3),
        },
    }
