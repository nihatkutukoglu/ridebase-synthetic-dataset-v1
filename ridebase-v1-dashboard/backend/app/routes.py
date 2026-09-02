"""HTTP surface. Analytics endpoints normalise the notebook artifacts; the
predict endpoint runs the frozen models."""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from . import analytics
from .artifacts import get_store, read_predictions
from .config import settings
from .predictor import PredictionError, predict
from .schemas import BatchPredictRequest, PredictRequest
from .v2_1_routes import v2_1 as v2_1_router
from .v2_1_service import health_fields as v2_1_health_fields
from .v2_routes import unified as v2_unified_router
from .v2_routes import v2 as v2_router
from .v2_service import health_fields as v2_health_fields

router = APIRouter()


@router.get("/health")
def health():
    h = dict(get_store().health())
    h["v1"] = h.get("status")
    try:
        h.update(v2_health_fields())
    except Exception as exc:  # pragma: no cover
        h["v2_status"] = f"error: {exc}"
    try:
        h.update(v2_1_health_fields())
    except Exception as exc:  # pragma: no cover
        h["v2_1_status"] = f"error: {exc}"
    return h


@router.post("/admin/reload", tags=["admin"])
def reload_artifacts():
    # never a public unauthenticated reload in production
    if settings.APP_ENV == "production":
        raise HTTPException(status_code=403, detail="reload disabled in production")
    store = get_store(reload=True)
    return {"reloaded": True, "generation": store.generation, "health": store.health()}


api = APIRouter(prefix="/api/v1")


@api.get("/model/info")
def model_info():
    return get_store().model_info()


@api.get("/metrics")
def metrics():
    store = get_store()
    return {
        "days": analytics._bands("DAYS"),
        "km": analytics._bands("KM"),
        "test_comparison": analytics.read_table("v1_final_tuning_test_comparison") or [],
        "qa": analytics.read_table("v1_final_tuning_qa")
        or analytics.read_table("v1_3_final_qa") or [],
        "model_generation": store.generation,
    }


@api.get("/features")
def features(mode: str = Query("all", pattern="^(all|simple|days|km)$")):
    store = get_store()
    cat = store.feature_catalog
    if mode == "simple":
        cat = [f for f in cat if f["simple"]]
    elif mode == "days":
        cat = [f for f in cat if f["in_days_model"]]
    elif mode == "km":
        cat = [f for f in cat if f["in_km_model"]]
    groups: dict[str, list] = {}
    for f in cat:
        groups.setdefault(f["group"], []).append(f)
    return {
        "mode": mode,
        "count": len(cat),
        "feature_count_days": len(store.bundles["days"].feature_cols),
        "feature_count_km": len(store.bundles["km"].feature_cols),
        "groups": groups,
        "features": cat,
        "leakage_guard": store.leakage_report,
    }


@api.get("/sample")
def sample_motorcycle():
    """An anonymised snapshot row from the held-out TEST predictions - target
    columns are stripped so it can seed the prediction form."""
    store = get_store()
    rows = read_predictions(sample=0)
    if not rows:
        raise HTTPException(404, "no prediction artifact available for sampling")
    rec = rows[int(np.random.default_rng().integers(0, len(rows)))]
    snap_p = settings.DATASET_DIR / "ml_maintenance_snapshots.parquet"
    feats: dict = {}
    snapshot_date = None
    if snap_p.exists():
        df = pd.read_parquet(snap_p)
        r = df[df["snapshot_id"] == rec["snapshot_id"]]
        if len(r):
            r = r.iloc[0]
            for f in store.feature_catalog:
                if f["name"] in r.index and f["type"] != "derived":
                    v = r[f["name"]]
                    if pd.isna(v):
                        continue
                    feats[f["name"]] = bool(v) if isinstance(v, (bool, np.bool_)) else (
                        float(v) if isinstance(v, (int, float, np.integer, np.floating)) else str(v))
            for dc in ("snapshot_date", "snapshot_at"):
                if dc in r.index and not pd.isna(r[dc]):
                    snapshot_date = pd.to_datetime(r[dc]).date().isoformat()
                    break
    return {
        "snapshot_id": rec["snapshot_id"],
        "snapshot_date": snapshot_date,
        "features": feats,
        "note": "actual target values are intentionally excluded",
    }


@api.post("/predict")
def do_predict(req: PredictRequest):
    store = get_store()
    try:
        return predict(store, req.features, req.snapshot_date, strict=req.strict)
    except PredictionError as exc:
        raise HTTPException(exc.status, exc.detail)


@api.post("/predict/batch")
def do_predict_batch(req: BatchPredictRequest):
    store = get_store()
    out = []
    for item in req.items:
        try:
            out.append({"ok": True, "result": predict(store, item.features, item.snapshot_date,
                                                       strict=item.strict)})
        except PredictionError as exc:
            out.append({"ok": False, "status": exc.status, "detail": exc.detail})
    return {"count": len(out), "results": out}


# ---------------------------------------------------------------- analytics
@api.get("/analytics/overview")
def a_overview():
    return analytics.overview(get_store())


@api.get("/analytics/target/{target}")
def a_target(target: str):
    if target.upper() not in ("DAYS", "KM"):
        raise HTTPException(404, "target must be DAYS or KM")
    return analytics.target_detail(get_store(), target.upper())


@api.get("/analytics/models")
def a_models():
    return analytics.models(get_store())


@api.get("/analytics/features")
def a_features():
    return analytics.features(get_store())


@api.get("/analytics/errors")
def a_errors():
    return analytics.errors(get_store())


@api.get("/analytics/drift")
def a_drift():
    return analytics.drift(get_store())


@api.get("/analytics/experiments")
def a_experiments():
    return analytics.experiments(get_store())


@api.get("/analytics/verdict")
def a_verdict():
    return analytics.verdict(get_store())


router.include_router(api)
router.include_router(v2_router)
router.include_router(v2_unified_router)
router.include_router(v2_1_router)
