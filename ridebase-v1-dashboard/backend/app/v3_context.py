"""PIT-safe, response-only motorcycle identity/context for V3.

This module never supplies predictor features. It reads the same synthetic source
world used by the V3 serving path and adds human-readable context only after the
frozen 44 probabilities have been produced.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Tuple

import pandas as pd

from .v3_schemas import V3MotorcycleContext


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _date(value: Any) -> date | None:
    if value is None or value == "" or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _reference_identity(motorcycle_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return immutable identity rows from the shipped V1.4 reference tables."""
    from ridebase_ml.v3.sources import load_table

    motorcycles = load_table("motorcycles")
    matched = motorcycles.loc[
        motorcycles["motorcycle_id"].astype(str) == str(motorcycle_id)
    ]
    identity = matched.iloc[0].to_dict() if len(matched) == 1 else {}

    model_id = _text(identity.get("model_id"))
    model_row: Dict[str, Any] = {}
    if model_id:
        models = load_table("ridebase_motorcycle_models_v1")
        selected = models.loc[models["model_id"].astype(str) == model_id]
        if len(selected) == 1:
            model_row = selected.iloc[0].to_dict()
    return identity, model_row


def friendly_motorcycle_label(context: Dict[str, Any]) -> str:
    """Human-readable presentation label; the ID remains the stable key."""
    motorcycle_id = _text(context.get("motorcycle_id")) or ""
    name = " ".join(
        part for part in (_text(context.get("brand")), _text(context.get("model")))
        if part
    )
    year = _integer(context.get("model_year"))
    if name and year is not None:
        return f"{name} ({year}) · {motorcycle_id}"
    if name:
        return f"{name} · {motorcycle_id}"
    return motorcycle_id


def build_motorcycle_context(
    motorcycle_id: str,
    landmark_date: Any,
    adapter: Any,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """Build product context using records available at/before the landmark.

    Missing fields are omitted from the returned context. No default odometer,
    date, year, model, or usage value is synthesized.
    """
    from ridebase_ml.v2_1.source_contract import HistoryFeatureRequest

    request = HistoryFeatureRequest.parse(motorcycle_id, landmark_date)
    landmark = request.landmark_date
    source_motorcycle = adapter.get_motorcycle(request.motorcycle_id, landmark)
    warnings: List[str] = []

    try:
        reference, model_master = _reference_identity(request.motorcycle_id)
    except (FileNotFoundError, KeyError, ValueError):
        reference, model_master = {}, {}
        warnings.append("Motosiklet kimlik referansı kullanılamadı; yalnız güvenli geçmiş alanları gösteriliyor.")

    source_motorcycle = source_motorcycle or {}
    brand = (
        _text(reference.get("brand"))
        or _text(source_motorcycle.get("brand"))
        or _text(model_master.get("brand"))
    )
    model = _text(reference.get("model_name")) or _text(model_master.get("model_name"))
    model_year = _integer(reference.get("production_year"))
    category = (
        _text(reference.get("category"))
        or _text(source_motorcycle.get("category"))
        or _text(model_master.get("category"))
    )

    mileage_rows = adapter.get_mileage_before(request.motorcycle_id, landmark)
    valid_mileage = []
    for row in mileage_rows:
        odometer = _number(row.get("closing_odometer_km"))
        effective = _date(row.get("_effective_at"))
        if (
            odometer is not None
            and odometer >= 0
            and effective is not None
            and effective <= landmark
        ):
            valid_mileage.append((effective, str(row.get("timeline_id", "")), odometer, row))
    latest_mileage = max(valid_mileage, key=lambda item: (item[0], item[1])) if valid_mileage else None
    current_odometer = latest_mileage[2] if latest_mileage else None

    services = [
        dict(row) for row in adapter.get_services_before(request.motorcycle_id, landmark)
        if str(row.get("status", "")).upper() == "DELIVERED"
        and _date(row.get("_effective_at")) is not None
        and (_date(row.get("_effective_at")) or date.max) <= landmark
    ]
    services.sort(key=lambda row: (
        _date(row.get("_effective_at")) or date.min,
        str(row.get("service_id", "")),
    ))
    last_service = services[-1] if services else None
    last_service_date = _date(last_service.get("_effective_at")) if last_service else None
    last_service_odometer = _number(last_service.get("odometer_km")) if last_service else None

    usage = adapter.get_usage_profile(request.motorcycle_id, landmark)
    if usage and (
        _date(usage.get("profile_start_date")) is None
        or (_date(usage.get("profile_start_date")) or date.max) > landmark
    ):
        usage = None
    annual_usage = _number(usage.get("annual_km_baseline")) if usage else None

    raw_context: Dict[str, Any] = {
        "motorcycle_id": request.motorcycle_id,
        "landmark_date": landmark.isoformat(),
        "source": "SYNTHETIC_HISTORY_V1_4",
        "brand": brand,
        "model": model,
        "model_year": model_year,
        "category": category,
        "current_odometer_km": current_odometer,
        "last_service_date": last_service_date.isoformat() if last_service_date else None,
        "last_service_odometer_km": last_service_odometer,
        "days_since_last_service": (
            (landmark - last_service_date).days if last_service_date else None
        ),
        "km_since_last_service": (
            current_odometer - last_service_odometer
            if current_odometer is not None
            and last_service_odometer is not None
            and current_odometer >= last_service_odometer
            else None
        ),
        "annual_usage_km": annual_usage,
    }
    context = V3MotorcycleContext(**raw_context).model_dump(exclude_none=True)

    if (
        current_odometer is not None
        and last_service_odometer is not None
        and current_odometer < last_service_odometer
    ):
        warnings.append(
            "Güncel kilometre kanıtı son servis kilometresinden eski; "
            "son servisten beri kilometre gösterilmedi."
        )

    missing = [
        label for key, label in (
            ("brand", "marka"),
            ("model", "model"),
            ("model_year", "model yılı"),
            ("current_odometer_km", "güncel kilometre"),
            ("last_service_date", "son servis"),
            ("annual_usage_km", "yıllık kullanım"),
        )
        if key not in context
    ]
    if missing:
        warnings.append("Eksik motosiklet bağlamı: " + ", ".join(missing) + ".")

    provenance: Dict[str, Any] = {
        "metadata_source": "ridebase_v1_4.motorcycles + ridebase_motorcycle_models_v1",
        "identity_boundary": "observation_start_date <= landmark_date",
        "odometer_source": (
            {
                "table": "mileage_timeline_monthly",
                "timeline_id": latest_mileage[1] or None,
                "period_end_date": latest_mileage[0].isoformat(),
                "boundary": "period_end_date <= landmark_date",
            }
            if latest_mileage else None
        ),
        "last_service_source": (
            {
                "table": "services",
                "service_id": _text(last_service.get("service_id")),
                "received_date": last_service_date.isoformat() if last_service_date else None,
                "status": "DELIVERED",
                "boundary": "received_at.date <= landmark_date",
            }
            if last_service else None
        ),
        "annual_usage_source": (
            {
                "table": "usage_profiles",
                "usage_profile_id": _text(usage.get("usage_profile_id")),
                "boundary": "profile_start_date <= landmark_date and active at landmark",
            }
            if usage else None
        ),
        "future_records_used": False,
    }
    return context, provenance, warnings
