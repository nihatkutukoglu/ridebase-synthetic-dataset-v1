"""Motorcycle catalog and deterministic partial-snapshot derivation for V2.

No model is trained here and no sample/default motorcycle is consulted. Scenario
inputs have exactly four possible provenances: USER_INPUT, MODEL_MASTER, DERIVED,
or MISSING_PREPROCESSOR.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Tuple

from .artifacts import DERIVED_FROM_DATE, get_store
from .config import settings
from .predictor import predict as v1_predict
from .v2_schemas import V2ScenarioRequest


MODEL_FEATURES = (
    "brand", "category", "powertrain_type", "engine_displacement_cc",
    "cylinder_count", "cooling_type", "final_drive_type", "transmission_type",
    "spark_plug_count", "fuel_type", "policy_group", "policy_ready",
    "spec_confidence",
)

_NUMERIC_MODEL_FIELDS = {
    "engine_displacement_cc", "cylinder_count", "spark_plug_count",
}

_BOOL_MODEL_FIELDS = {"policy_ready"}


class ScenarioInputError(ValueError):
    """A user-facing scenario contract error."""


def _clean(value: Any) -> Any:
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def _number(value: Any) -> Any:
    value = _clean(value)
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _boolean(value: Any) -> Any:
    value = _clean(value)
    if value is None:
        return None
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise ValueError(f"invalid boolean in model catalog: {value!r}")


def _public_model(row: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "brand": _clean(row.get("brand")),
        "model_id": _clean(row.get("model_id")),
        "model_name": _clean(row.get("model_name")),
        "variant_or_generation": _clean(row.get("variant_or_generation")),
        "year_min": _number(row.get("production_start_year")),
        "year_max": _number(row.get("production_end_year")),
        "year_range_basis": _clean(row.get("production_year_range_basis")),
        "year_range_confidence": _clean(row.get("production_year_range_confidence")),
    }
    for feature in MODEL_FEATURES:
        if feature in _NUMERIC_MODEL_FIELDS:
            out[feature] = _number(row.get(feature))
        elif feature in _BOOL_MODEL_FIELDS:
            out[feature] = _boolean(row.get(feature))
        else:
            out[feature] = _clean(row.get(feature))
    out["year_range_authoritative"] = out["year_range_confidence"] in {"HIGH", "VERIFIED"}
    return out


@lru_cache(maxsize=1)
def motorcycle_catalog() -> Tuple[Dict[str, Any], ...]:
    path = settings.MODEL_CATALOG_PATH
    if not path.exists():
        raise RuntimeError(f"motorcycle model catalog not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(_public_model(row) for row in csv.DictReader(handle))
    if not rows:
        raise RuntimeError("motorcycle model catalog is empty")
    ids = [row["model_id"] for row in rows]
    if any(not row["brand"] or not row["model_id"] or not row["model_name"] for row in rows):
        raise RuntimeError("motorcycle model catalog contains an incomplete identity row")
    if len(ids) != len(set(ids)):
        raise RuntimeError("motorcycle model catalog contains duplicate model_id values")
    return rows


def catalog_response() -> Dict[str, Any]:
    rows = list(motorcycle_catalog())
    brands = sorted({str(row["brand"]) for row in rows})
    return {
        "source": "ridebase_v1_3/source_tables/ridebase_motorcycle_models_v1.csv",
        "dataset_version": "1.3.0",
        "brand_count": len(brands),
        "model_count": len(rows),
        "brands": brands,
        "models": rows,
        "year_range_note": (
            "Production-year ranges are simulation-prior catalog ranges with LOW confidence; "
            "out-of-range years are warned, not silently rewritten."
        ),
    }


def _selected_model(brand: str, model_id: str) -> Dict[str, Any]:
    by_id = {row["model_id"]: row for row in motorcycle_catalog()}
    model = by_id.get(model_id)
    if model is None:
        raise ScenarioInputError(f"Unknown model_id: {model_id}")
    if model["brand"] != brand:
        raise ScenarioInputError(
            f"Invalid brand/model pair: {model_id} belongs to {model['brand']}, not {brand}"
        )
    return dict(model)


def _set(features: Dict[str, Any], origins: Dict[str, Dict[str, str]], key: str,
         value: Any, source: str, detail: str) -> None:
    if value is None or value == "":
        return
    features[key] = value
    origins[key] = {"source": source, "detail": detail}


def _feature_group(feature: str) -> Tuple[str, str]:
    if feature in {"brand", "category", "powertrain_type", "engine_displacement_cc",
                   "cylinder_count", "cooling_type", "final_drive_type", "transmission_type",
                   "spark_plug_count", "fuel_type", "policy_group", "policy_ready",
                   "spec_confidence", "production_year", "motorcycle_age_years",
                   "ownership_months", "initial_mileage_km"}:
        return "motorcycle", "Motosiklet / model"
    if feature in {"customer_type", "is_fleet_customer", "acquisition_channel", "usage_type",
                   "annual_km_baseline", "city_ratio", "highway_ratio", "offroad_ratio",
                   "track_ratio", "avg_ride_days_per_week", "avg_km_per_active_day",
                   "riding_intensity", "seasonality_strength", "winter_usage_factor",
                   "weather_sensitivity", "storage_condition", "load_severity_factor",
                   "climate_zone"}:
        return "usage", "Kullanım"
    if feature in {"split", "snapshot_year", "snapshot_month", "snapshot_month_sin",
                   "snapshot_month_cos", "is_left_truncated", "days_observed"} or \
            feature.startswith("workshop_") or feature.startswith("current_") or \
            feature in {"price_level", "service_bay_count", "appointment_rate",
                        "avg_parts_lead_days", "customer_volume_index", "courier_customer_share"}:
        return "snapshot_context", "Anlık / atölye bağlamı"
    return "service_history", "Servis geçmişi"


def _coverage(feature_order: Iterable[str], origins: Dict[str, Dict[str, str]]) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    provenance: List[Dict[str, str]] = []
    known = 0
    order = list(feature_order)
    for feature in order:
        group_key, group_label = _feature_group(feature)
        group = grouped.setdefault(group_key, {"key": group_key, "label": group_label,
                                                "known": 0, "total": 0, "missing": 0})
        group["total"] += 1
        meta = origins.get(feature)
        if meta is None:
            source = "MISSING_PREPROCESSOR"
            detail = "Not supplied or safely derivable; frozen train-time preprocessing handles missingness."
            group["missing"] += 1
        else:
            source = meta["source"]
            detail = meta["detail"]
            known += 1
            group["known"] += 1
        provenance.append({"feature": feature, "group": group_key, "source": source, "detail": detail})
    ratio = known / len(order)
    verdict = "FULL_SNAPSHOT" if ratio >= 0.90 else "MEDIUM_COVERAGE" if ratio >= 0.50 else "LIMITED_INFORMATION"
    return {
        "known_or_derived": known,
        "total": len(order),
        "missing": len(order) - known,
        "ratio": round(ratio, 4),
        "verdict": verdict,
        "groups": list(grouped.values()),
        "history_features_missing": grouped.get("service_history", {}).get("missing", 0),
        "note": "This is input coverage, not a model confidence score.",
    }, provenance


def derive_scenario(req: V2ScenarioRequest, predictor: Any) -> Dict[str, Any]:
    """Validate product inputs and create only defensible frozen V2 features."""
    today = dt.date.today()
    if req.snapshot_date > today:
        raise ScenarioInputError("snapshot_date cannot be in the future")
    if req.production_year > req.snapshot_date.year:
        raise ScenarioInputError("production_year cannot be after snapshot_date")
    if req.last_service_date and req.last_service_date > req.snapshot_date:
        raise ScenarioInputError("last_service_date cannot be in the future or after snapshot_date")
    if req.last_service_odometer_km is not None and req.current_odometer_km is None:
        raise ScenarioInputError("current_odometer_km is required when last_service_odometer_km is supplied")
    if (req.last_service_odometer_km is not None and req.current_odometer_km is not None
            and req.last_service_odometer_km > req.current_odometer_km):
        raise ScenarioInputError("last_service_odometer_km cannot exceed current_odometer_km")

    model = _selected_model(req.brand, req.model_id)
    for key, value in (("usage_type", req.usage_type), ("riding_intensity", req.riding_intensity)):
        allowed = predictor.options.get(key, [])
        if value is not None and allowed and value not in allowed:
            raise ScenarioInputError(f"Invalid {key}: {value!r}")

    warnings: List[str] = []
    year_min, year_max = model.get("year_min"), model.get("year_max")
    if not model.get("year_range_authoritative"):
        warnings.append("Model yılı için katalog doğruluğu sınırlı (simulation-prior range, LOW confidence).")
    if year_min is not None and year_max is not None and not (year_min <= req.production_year <= year_max):
        warnings.append(
            f"Selected year {req.production_year} is outside the catalog range {year_min}–{year_max}; "
            "the value was not changed because range confidence is LOW."
        )

    features: Dict[str, Any] = {}
    origins: Dict[str, Dict[str, str]] = {}
    for feature in MODEL_FEATURES:
        _set(features, origins, feature, model.get(feature), "MODEL_MASTER",
             f"Resolved from selected model {model['model_id']}.")

    _set(features, origins, "production_year", req.production_year, "USER_INPUT", "Selected model year.")
    _set(features, origins, "usage_type", req.usage_type, "USER_INPUT", "Usage type entered by user.")
    _set(features, origins, "riding_intensity", req.riding_intensity, "USER_INPUT",
         "Riding intensity entered by user.")
    _set(features, origins, "annual_km_baseline", req.annual_km_baseline, "USER_INPUT",
         "Estimated annual distance entered by user.")

    month = req.snapshot_date.month
    for key, value, detail in (
        ("snapshot_year", req.snapshot_date.year, "Year derived from snapshot_date."),
        ("snapshot_month", month, "Month derived from snapshot_date."),
        ("snapshot_month_sin", math.sin(2 * math.pi * month / 12.0), "Cyclical month sine."),
        ("snapshot_month_cos", math.cos(2 * math.pi * month / 12.0), "Cyclical month cosine."),
        ("motorcycle_age_years", max(0, req.snapshot_date.year - req.production_year),
         "Calendar-year age approximation from production_year and snapshot_date."),
    ):
        _set(features, origins, key, value, "DERIVED", detail)
    origins["split"] = {"source": "DERIVED", "detail": "Internal inert inference sentinel; caller cannot set it."}

    if req.last_service_date is not None:
        days = (req.snapshot_date - req.last_service_date).days
        _set(features, origins, "days_since_previous_service", days, "DERIVED",
             "snapshot_date minus last_service_date.")
    if req.current_odometer_km is not None and req.last_service_odometer_km is not None:
        km = req.current_odometer_km - req.last_service_odometer_km
        _set(features, origins, "km_since_previous_service", km, "DERIVED",
             "current_odometer_km minus last_service_odometer_km.")
        if req.last_service_date is not None and (req.snapshot_date - req.last_service_date).days > 0:
            per_day = km / (req.snapshot_date - req.last_service_date).days
            _set(features, origins, "avg_km_per_day_since_previous_service", per_day, "DERIVED",
                 "km_since_previous_service divided by days_since_previous_service.")

    coverage, provenance = _coverage(predictor.feature_cols, origins)
    return {
        "model": model,
        "features": features,
        "origins": origins,
        "coverage": coverage,
        "provenance": provenance,
        "warnings": warnings,
    }


def predict_scenario(req: V2ScenarioRequest, predictor: Any) -> Dict[str, Any]:
    built = derive_scenario(req, predictor)
    v2_input = dict(built["features"])
    v2_input["snapshot_date"] = req.snapshot_date.isoformat()
    result = predictor.predict_batch([v2_input], strict=False)
    pred = result["predictions"][0]

    store = get_store()
    v1_known = {item["name"] for item in store.feature_catalog}
    v1_features = {key: value for key, value in built["features"].items()
                   if key in v1_known and key not in DERIVED_FROM_DATE}
    if req.current_odometer_km is not None and "snapshot_odometer_km" in v1_known:
        v1_features["snapshot_odometer_km"] = req.current_odometer_km
    v1 = v1_predict(store, v1_features, req.snapshot_date, strict=False)

    warnings = list(built["warnings"])
    warnings.extend(pred.get("warnings", []))
    return {
        "mode": "SCENARIO_PARTIAL",
        "selected_motorcycle": built["model"],
        "v1": {
            "next_service_days": v1["prediction"]["next_service_days"],
            "next_service_km": v1["prediction"]["next_service_km"],
            "estimated_service_date": v1["derived"].get("estimated_service_date"),
            "estimated_service_odometer_km": v1["derived"].get("estimated_service_odometer_km"),
        },
        "v2": {key: pred.get(key) for key in (
            "risk_30d", "risk_60d", "risk_90d", "risk_120d",
            "median_service_days", "risk_group_90d", "estimated_median_service_date",
        ) if key in pred},
        "coverage": built["coverage"],
        "provenance": built["provenance"],
        "warnings": warnings,
        "calibration": result["calibration"],
        "model": result["model"],
        "warning": result["warning"],
        "interpretation": (
            "V1 is a point estimate of days/km to next service. V2 is the calibrated "
            "probability of service return within each time window."
        ),
        "mileage_contract": {
            "initial_mileage_km": (
                "Frozen V2 feature: motorcycle mileage at observation_start_date, generated from the "
                "AGE_CUSTOMER_TYPE_CATEGORY_PRIOR basis; it is not current odometer and remains missing "
                "in scenario mode."
            ),
            "current_odometer_km": (
                "Natural product input; used for V1 snapshot_odometer_km and, with last-service odometer, "
                "to derive V2 km_since_previous_service."
            ),
        },
    }
