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
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .artifacts import DERIVED_FROM_DATE, get_store
from .config import settings
from .predictor import predict as v1_predict
from .v2_schemas import V2ScenarioRequest

try:
    from ridebase_ml.policy.urgency import calculate_maintenance_urgency
except ImportError:
    import sys
    from pathlib import Path
    _ml_root = Path(__file__).resolve().parents[3] / "ridebase-ml"
    if str(_ml_root) not in sys.path:
        sys.path.insert(0, str(_ml_root))
    from ridebase_ml.policy.urgency import calculate_maintenance_urgency


MODEL_FEATURES = (
    "brand", "category", "powertrain_type", "engine_displacement_cc",
    "cylinder_count", "cooling_type", "final_drive_type", "transmission_type",
    "spark_plug_count", "fuel_type", "policy_group", "policy_ready",
    "spec_confidence",
)

_PRIMARY_MAINTENANCE_TASKS = {
    "ICE": ("ENGINE_OIL_CHANGE", "GENERAL_SAFETY_INSPECTION"),
    "EV": ("GENERAL_SAFETY_INSPECTION", "EV_TRACTION_BATTERY_HEALTH_CHECK"),
}

# Product-facing, market/year-specific maintenance rules live outside the frozen
# synthetic dataset contract. They must never be presented as manufacturer-exact
# unless an authoritative year-specific manual backs them. The legacy NS200 rule
# below is the RideBase Türkiye operating policy confirmed for the 2016 scenario;
# current UG2 motorcycles continue to use the verified catalog policy.
_MAINTENANCE_POLICY_OVERRIDES = (
    {
        "model_id": "BAJAJ_NS200",
        "market": "TR",
        "year_min": 2016,
        "year_max": 2023,
        "task_code": "ENGINE_OIL_CHANGE",
        "interval_km": 3000,
        "interval_months": 6,
        "trigger_mode": "WHICHEVER_FIRST",
        "confidence": "OPERATIONAL",
        "source_authority": "RideBase Türkiye operational policy",
        "evidence_level": "OWNER_CONFIRMED_OPERATING_POLICY",
        "manufacturer_exact": False,
        "policy_version": "product-2026-09-02",
        "scope": "MODEL_YEAR_MARKET",
        "note": (
            "2016–2023 Türkiye NS200 için RideBase operasyonel yağ değişim aralığı; "
            "üreticiye ait yıl-spesifik resmî periyot olarak sunulmaz."
        ),
    },
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


@lru_cache(maxsize=1)
def maintenance_policies() -> Tuple[Dict[str, str], ...]:
    path = settings.MAINTENANCE_POLICY_PATH
    if not path.exists():
        raise RuntimeError(f"maintenance policy catalog not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    if not rows:
        raise RuntimeError("maintenance policy catalog is empty")
    return rows


def _maintenance_policy_for_model(
    model: Dict[str, Any], production_year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve one defensible primary service cadence for product-facing status.

    Tiny chain-clean/lubrication cadences are intentionally not used as the primary
    workshop-service interval. ICE models prefer engine-oil service; EV models and
    fallbacks use the general safety inspection.
    """
    if production_year is not None:
        for override in _MAINTENANCE_POLICY_OVERRIDES:
            if (override["model_id"] == model.get("model_id")
                    and override["year_min"] <= production_year <= override["year_max"]):
                out = dict(override)
                months = out.get("interval_months")
                out["interval_days"] = round(float(months) * 30.4375, 2) if months else None
                out["year_specific"] = True
                return out

    candidates = []
    for row in maintenance_policies():
        active = str(row.get("is_generator_active", "")).strip().lower()
        if active not in {"1", "true", "yes"} or row.get("policy_kind") != "SCHEDULED":
            continue
        exact_model = _clean(row.get("model_id")) == model.get("model_id")
        group_match = (not _clean(row.get("model_id"))
                       and _clean(row.get("policy_group")) == model.get("policy_group"))
        if not (exact_model or group_match):
            continue
        recurring_km = _number(row.get("recurring_km"))
        recurring_months = _number(row.get("recurring_months"))
        if recurring_km is None and recurring_months is None:
            continue
        candidates.append((row, exact_model, recurring_km, recurring_months))

    task_priority = _PRIMARY_MAINTENANCE_TASKS.get(
        str(model.get("powertrain_type")), ("GENERAL_SAFETY_INSPECTION",)
    )
    selected = None
    for task in task_priority:
        matches = [item for item in candidates if item[0].get("task_code") == task]
        if matches:
            selected = sorted(matches, key=lambda item: item[1], reverse=True)[0]
            break
    if selected is None:
        workshop_candidates = [
            item for item in candidates
            if not any(token in str(item[0].get("task_code"))
                       for token in ("CHAIN_CLEAN", "CHAIN_LUBRICATE", "CHAIN_INSPECTION"))
        ]
        if workshop_candidates:
            selected = min(
                workshop_candidates,
                key=lambda item: float(item[2]) if item[2] is not None else float("inf"),
            )
    if selected is None:
        return None

    row, exact_model, recurring_km, recurring_months = selected
    return {
        "task_code": row.get("task_code"),
        "interval_km": recurring_km,
        "interval_months": recurring_months,
        "interval_days": (round(float(recurring_months) * 30.4375, 2)
                          if recurring_months is not None else None),
        "trigger_mode": row.get("trigger_mode"),
        "confidence": row.get("confidence"),
        "source_authority": row.get("source_authority"),
        "evidence_level": row.get("evidence_level"),
        "manufacturer_exact": str(row.get("is_manufacturer_exact_interval", "")).strip().lower()
        in {"1", "true", "yes"},
        "policy_version": row.get("policy_version"),
        "scope": "MODEL" if exact_model else "POLICY_GROUP",
        "market": "TR",
        "year_specific": False,
        "source_url": row.get("source_url"),
        "note": (
            "Frozen manufacturer/model policy record; verify against the current owner manual."
            if str(row.get("is_manufacturer_exact_interval", "")).strip().lower()
            in {"1", "true", "yes"}
            else "RideBase simulation policy prior; not a manufacturer-verified interval."
        ),
    }


def _model_with_policy(
    model: Dict[str, Any], production_year: Optional[int] = None,
) -> Dict[str, Any]:
    out = dict(model)
    out["maintenance_policy"] = _maintenance_policy_for_model(out, production_year)
    return out


def catalog_response() -> Dict[str, Any]:
    rows = [_model_with_policy(row) for row in motorcycle_catalog()]
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


def _selected_model(
    brand: str, model_id: str, production_year: Optional[int] = None,
) -> Dict[str, Any]:
    by_id = {row["model_id"]: row for row in motorcycle_catalog()}
    model = by_id.get(model_id)
    if model is None:
        raise ScenarioInputError(f"Unknown model_id: {model_id}")
    if model["brand"] != brand:
        raise ScenarioInputError(
            f"Invalid brand/model pair: {model_id} belongs to {model['brand']}, not {brand}"
        )
    return _model_with_policy(model, production_year)


def _maintenance_assessment(req: V2ScenarioRequest, model: Dict[str, Any]) -> Dict[str, Any]:
    policy = model.get("maintenance_policy")
    result: Dict[str, Any] = {
        "status": "UNKNOWN",
        "label": "BAKIM DURUMU HESAPLANAMADI",
        "action": "PERSONAL_MAINTENANCE_UNAVAILABLE",
        "action_label": "KİŞİSEL BAKIM TARİHİ HESAPLANAMAZ",
        "service_history_complete": False,
        "missing_inputs": [],
        "policy": policy,
        "km_since_service": None,
        "days_since_service": None,
        "progress_ratio": None,
        "progress_pct": None,
        "overdue_km": None,
        "overdue_days": None,
        "remaining_km": None,
        "remaining_days": None,
        "driving_metric": None,
        "recent_annualized_km": None,
        "annual_baseline_ratio": None,
        "note": "Kişisel bakım kararı için son servis tarihi ve kilometre başlangıç noktası gerekir.",
    }
    if policy is None:
        result["missing_inputs"] = ["maintenance_policy"]
        return result

    required = {
        "current_odometer_km": req.current_odometer_km,
        "last_service_odometer_km": req.last_service_odometer_km,
        "last_service_date": req.last_service_date,
    }
    result["missing_inputs"] = [key for key, value in required.items() if value is None]
    if result["missing_inputs"]:
        return result
    result["service_history_complete"] = True

    progress = []
    km_since = None
    if req.current_odometer_km is not None and req.last_service_odometer_km is not None:
        km_since = float(req.current_odometer_km - req.last_service_odometer_km)
        result["km_since_service"] = round(km_since, 2)
        interval_km = policy.get("interval_km")
        if interval_km:
            km_ratio = km_since / float(interval_km)
            progress.append(("KM", km_ratio))
            result["overdue_km"] = round(max(0.0, km_since - float(interval_km)), 2)
            result["remaining_km"] = round(max(0.0, float(interval_km) - km_since), 2)

    days_since = None
    if req.last_service_date is not None:
        days_since = (req.snapshot_date - req.last_service_date).days
        result["days_since_service"] = days_since
        interval_days = policy.get("interval_days")
        if interval_days:
            day_ratio = days_since / float(interval_days)
            progress.append(("DAYS", day_ratio))
            result["overdue_days"] = round(max(0.0, days_since - float(interval_days)), 2)
            result["remaining_days"] = round(max(0.0, float(interval_days) - days_since), 2)

    if progress:
        metric, ratio = max(progress, key=lambda item: item[1])
        result["driving_metric"] = metric
        result["progress_ratio"] = round(ratio, 4)
        result["progress_pct"] = round(ratio * 100.0, 1)
        if ratio >= 1.0:
            result["status"] = "OVERDUE"
            result["label"] = "BAKIM GECİKMİŞ"
            result["action"] = "SERVICE_NOW_REQUIRED"
            result["action_label"] = "SERVİS ŞİMDİ GEREKLİ"
        elif ratio >= 0.8:
            result["status"] = "DUE_SOON"
            result["label"] = "BAKIM YAKLAŞIYOR"
            result["action"] = "PLAN_SERVICE"
            result["action_label"] = "SERVİSİ PLANLA"
        else:
            result["status"] = "NOT_DUE"
            result["label"] = "BAKIM PERİYODU İÇİNDE"
            result["action"] = "NO_IMMEDIATE_SERVICE"
            result["action_label"] = "HEMEN SERVİS GEREKMİYOR"

    km_ratio_val = (km_since / float(policy["interval_km"])) if (km_since is not None and policy.get("interval_km")) else None
    day_ratio_val = (days_since / float(policy["interval_days"])) if (days_since is not None and policy.get("interval_days")) else None

    urgency = calculate_maintenance_urgency(
        progress_ratio=result.get("progress_ratio"),
        km_ratio=km_ratio_val,
        day_ratio=day_ratio_val,
        overdue_km=result.get("overdue_km"),
        overdue_days=result.get("overdue_days"),
        interval_km=float(policy["interval_km"]) if policy.get("interval_km") else None,
        interval_days=float(policy["interval_days"]) if policy.get("interval_days") else None,
        remaining_km=result.get("remaining_km"),
        remaining_days=result.get("remaining_days"),
    )
    result["urgency"] = urgency
    result["maintenance_urgency_score"] = urgency["maintenance_urgency_score"]
    result["maintenance_urgency_level"] = urgency["maintenance_urgency_level"]
    result["maintenance_urgency_reason"] = urgency["maintenance_urgency_reason"]
    result["determining_dimension"] = urgency["determining_dimension"]

    if days_since and days_since >= 30 and km_since is not None and km_since >= 500:
        annualized = km_since * 365.0 / days_since
        result["recent_annualized_km"] = round(annualized, 1)
        if req.annual_km_baseline and req.annual_km_baseline > 0:
            result["annual_baseline_ratio"] = round(annualized / req.annual_km_baseline, 3)
    return result


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

    model = _selected_model(req.brand, req.model_id, req.production_year)
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
    policy = model.get("maintenance_policy") or {}
    _set(features, origins, "policy_interval_km", policy.get("interval_km"), "MODEL_MASTER",
         f"Primary {policy.get('task_code')} cadence resolved from the selected model's policy group.")

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
        if policy.get("interval_km"):
            overdue_km = max(0.0, km - float(policy["interval_km"]))
            _set(features, origins, "maintenance_overdue_km_pre_service", overdue_km, "DERIVED",
                 "max(0, km_since_previous_service minus primary policy_interval_km).")
        if req.last_service_date is not None and (req.snapshot_date - req.last_service_date).days > 0:
            per_day = km / (req.snapshot_date - req.last_service_date).days
            _set(features, origins, "avg_km_per_day_since_previous_service", per_day, "DERIVED",
                 "km_since_previous_service divided by days_since_previous_service.")

    if req.last_service_date is not None and policy.get("interval_days"):
        overdue_days = max(
            0.0,
            (req.snapshot_date - req.last_service_date).days - float(policy["interval_days"]),
        )
        _set(features, origins, "maintenance_overdue_days_pre_service", overdue_days, "DERIVED",
             "max(0, days_since_previous_service minus primary policy interval days).")

    maintenance = _maintenance_assessment(req, model)
    baseline_ratio = maintenance.get("annual_baseline_ratio")
    if baseline_ratio is not None and (baseline_ratio >= 2.0 or baseline_ratio <= 0.5):
        warnings.append(
            "Son servis sonrası tempo yıllık km girdisiyle belirgin biçimde çelişiyor: "
            f"son dönem yıllıklandırılmış ~{maintenance['recent_annualized_km']:.0f} km, "
            f"girilen yıllık {req.annual_km_baseline:.0f} km. V2 bu iki sinyali birlikte kullanır."
        )

    coverage, provenance = _coverage(predictor.feature_cols, origins)
    return {
        "model": model,
        "features": features,
        "origins": origins,
        "coverage": coverage,
        "provenance": provenance,
        "maintenance": maintenance,
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

    maintenance = built["maintenance"]
    show_v1 = maintenance["status"] not in {"UNKNOWN", "OVERDUE"}
    prediction_scope = (
        "PERSONAL_CONTEXT"
        if maintenance["service_history_complete"] and maintenance["status"] != "UNKNOWN"
        else "COHORT_SCENARIO"
    )
    if maintenance["status"] == "OVERDUE":
        v1_suppressed_reason = (
            "Bakım geciktiği için ileri tarih/mesafe tahmini gösterilmez; servis şimdi gereklidir."
        )
    elif maintenance["status"] == "UNKNOWN":
        v1_suppressed_reason = (
            "Son servis tarihi ve kilometresi bilinmediği için kişisel tarih/mesafe hesaplanamaz."
        )
    else:
        v1_suppressed_reason = None

    v1_payload = None
    if show_v1:
        v1_payload = {
            "next_service_days": v1["prediction"]["next_service_days"],
            "next_service_km": v1["prediction"]["next_service_km"],
            "estimated_service_date": v1["derived"].get("estimated_service_date"),
            "estimated_service_odometer_km": v1["derived"].get("estimated_service_odometer_km"),
        }

    warnings = list(built["warnings"])
    warnings.extend(pred.get("warnings", []))
    return {
        "mode": "SCENARIO_PARTIAL",
        "selected_motorcycle": built["model"],
        "v1": v1_payload,
        "v2": {key: pred.get(key) for key in (
            "risk_30d", "risk_60d", "risk_90d", "risk_120d",
            "median_service_days", "risk_group_90d", "estimated_median_service_date",
        ) if key in pred},
        "maintenance": maintenance,
        "decision": {
            "primary_source": "DETERMINISTIC_MAINTENANCE_POLICY",
            "primary_action": maintenance["action"],
            "primary_action_label": maintenance["action_label"],
            "prediction_scope": prediction_scope,
            "service_history_complete": maintenance["service_history_complete"],
            "show_v1_point_estimate": show_v1,
            "v1_suppressed_reason": v1_suppressed_reason,
            "v2_role": "CUSTOMER_SELF_RETURN_PROBABILITY",
            "v2_label": "Müşterinin kendiliğinden servise gelme ihtimali",
        },
        "coverage": built["coverage"],
        "provenance": built["provenance"],
        "warnings": warnings,
        "calibration": result["calibration"],
        "model": result["model"],
        "warning": result["warning"],
        "interpretation": (
            "Deterministic maintenance policy is the source of truth for whether service is due. "
            "V1 timing is hidden when history is incomplete or maintenance is overdue. V2 is only "
            "the calibrated probability that the customer returns within each time window."
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
