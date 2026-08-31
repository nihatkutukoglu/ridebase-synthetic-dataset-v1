"""Inference service. Uses the frozen train-time preprocessor with ``transform``
only (never ``fit``), preserves the exact model column order, and derives the
absolute service date / odometer from the snapshot the caller supplies."""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

import numpy as np
import pandas as pd

from .artifacts import ArtifactStore, DERIVED_FROM_DATE, contains_leak

_TYPICAL_ERROR_CACHE: dict[str, dict] = {}


class PredictionError(Exception):
    def __init__(self, status: int, detail: Any):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _derive_date_features(d: dt.date) -> dict[str, float]:
    doy = d.timetuple().tm_yday
    return {
        "snapshot_year": float(d.year),
        "snapshot_month": float(d.month),
        "snapshot_quarter": float((d.month - 1) // 3 + 1),
        "snapshot_day_of_year": float(doy),
        "snapshot_month_sin": math.sin(2 * math.pi * d.month / 12.0),
        "snapshot_month_cos": math.cos(2 * math.pi * d.month / 12.0),
    }


def _coerce(value: Any) -> Any:
    if value is None or value == "":
        return np.nan
    if isinstance(value, bool):
        return value
    return value


def validate_payload(store: ArtifactStore, features: dict[str, Any]) -> list[str]:
    """Return a list of human-readable validation errors (empty = ok)."""
    errors: list[str] = []
    known = {f["name"] for f in store.feature_catalog}
    by_name = {f["name"]: f for f in store.feature_catalog}
    for key, val in features.items():
        tok = contains_leak(key)
        if tok:
            raise PredictionError(422, f"Field '{key}' looks like a target/future value ('{tok}') and is not allowed.")
        if key in DERIVED_FROM_DATE:
            errors.append(f"'{key}' is derived from snapshot_date and must not be sent directly.")
            continue
        if key not in known:
            errors.append(f"Unknown field '{key}'.")
            continue
        if val in (None, ""):
            continue
        spec = by_name[key]
        if spec["type"] == "number":
            try:
                fv = float(val)
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be a number.")
                continue
            if not math.isfinite(fv):
                errors.append(f"'{key}' must be finite.")
            if key.endswith("_km") or "odometer" in key or "mileage" in key or key.endswith("_cc"):
                if fv < 0:
                    errors.append(f"'{key}' cannot be negative.")
            if key in ("motorcycle_age_years", "ownership_months", "previous_service_count") and fv < 0:
                errors.append(f"'{key}' cannot be negative.")
        elif spec["type"] == "categorical" and spec.get("options"):
            if str(val) not in spec["options"]:
                errors.append(f"'{key}'='{val}' is not a known value.")
    return errors


def _ood_flags(store: ArtifactStore, features: dict[str, Any]) -> list[dict]:
    by_name = {f["name"]: f for f in store.feature_catalog}
    out = []
    for key, val in features.items():
        spec = by_name.get(key)
        if not spec or spec["type"] != "number" or val in (None, ""):
            continue
        try:
            fv = float(val)
        except (TypeError, ValueError):
            continue
        lo, hi = spec.get("p01"), spec.get("p99")
        if lo is not None and hi is not None and (fv < lo or fv > hi):
            out.append({"field": key, "value": fv, "typical_range": [lo, hi]})
    return out


def _typical_error(store: ArtifactStore) -> dict:
    from .artifacts import read_table

    if _TYPICAL_ERROR_CACHE.get("gen") == store.generation:
        return _TYPICAL_ERROR_CACHE["val"]
    val = {"days_mae": None, "km_mae": None, "source": None}
    bands = read_table("v1_final_tuning_test_metric_bands")
    if bands:
        for row in bands:
            if row.get("config") == "tuned" and row.get("target") == "DAYS":
                val["days_mae"] = row.get("mae")
            if row.get("config") == "tuned" and row.get("target") == "KM":
                val["km_mae"] = row.get("mae")
        val["source"] = "v1_final_tuning_test_metric_bands.csv"
    else:
        m = read_table("v1_3_final_test_metrics")
        if m:
            for row in m:
                if row.get("split") == "TEST" and row.get("metric") == "mae":
                    if row.get("target") == "DAYS":
                        val["days_mae"] = row.get("value")
                    if row.get("target") == "KM":
                        val["km_mae"] = row.get("value")
            val["source"] = "v1_3_final_test_metrics.csv"
    _TYPICAL_ERROR_CACHE.update(gen=store.generation, val=val)
    return val


def _predict_one_target(bundle, row_df: pd.DataFrame) -> float:
    sub = row_df.reindex(columns=bundle.feature_cols)
    for c in bundle.feature_cols:
        if c in bundle.cat_cols:
            sub[c] = sub[c].astype("object").where(sub[c].notna(), "UNKNOWN").astype(str)
        else:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
    if bundle.mode == "native_cat":
        for c in bundle.cat_cols:
            sub[c] = sub[c].astype("category")
        raw = bundle.model.predict(sub)
    else:
        X = bundle.preprocessor.transform(sub)
        raw = bundle.model.predict(X)
    pred = float(np.asarray(raw).ravel()[0])
    if bundle.transform == "log1p":
        pred = math.expm1(pred)
    return max(0.0, pred)


def predict(
    store: ArtifactStore,
    features: dict[str, Any],
    snapshot_date: dt.date | None,
    strict: bool = True,
) -> dict:
    d, k = store.bundles.get("days"), store.bundles.get("km")
    if not (d and d.ok and k and k.ok):
        raise PredictionError(503, "Models are not loaded (see /health).")

    errors = validate_payload(store, features)
    if errors and strict:
        raise PredictionError(422, {"validation_errors": errors})

    clean = {kk: _coerce(vv) for kk, vv in features.items()
             if kk not in DERIVED_FROM_DATE and not contains_leak(kk)}
    if snapshot_date:
        clean.update(_derive_date_features(snapshot_date))

    row = pd.DataFrame([clean])
    days = _predict_one_target(d, row)
    km = _predict_one_target(k, row)

    derived: dict[str, Any] = {"estimated_service_date": None, "estimated_service_odometer_km": None}
    if snapshot_date:
        derived["estimated_service_date"] = (snapshot_date + dt.timedelta(days=round(days))).isoformat()
    odo = features.get("snapshot_odometer_km")
    try:
        if odo not in (None, ""):
            derived["estimated_service_odometer_km"] = round(float(odo) + km, 1)
    except (TypeError, ValueError):
        pass

    te = _typical_error(store)
    return {
        "prediction": {"next_service_days": round(days, 1), "next_service_km": round(km, 1)},
        "derived": derived,
        "typical_model_error": te,
        "input_diagnostics": {
            "validation_errors": errors,
            "out_of_distribution": _ood_flags(store, features),
            "fields_supplied": len([v for v in features.values() if v not in (None, "")]),
            "fields_imputed_days": sum(1 for c in d.feature_cols if features.get(c) in (None, "")),
            "fields_imputed_km": sum(1 for c in k.feature_cols if features.get(c) in (None, "")),
        },
        "model": {
            "days_model": store.model_info()["days_model_name"],
            "km_model": store.model_info()["km_model_name"],
            "dataset_version": store.dataset_version(),
            "model_generation": store.generation,
            "deterministic": True,
        },
        "warning": "Model developed on synthetic RideBase v1.3 data; real-fleet validation pending.",
    }
