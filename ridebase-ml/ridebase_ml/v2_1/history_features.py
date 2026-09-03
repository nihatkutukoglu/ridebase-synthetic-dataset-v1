"""Canonical V2.1 history feature-builder contract (Prompt 1 foundation).

The builder reconstructs only source-supported values, reusing the frozen
offline aggregation helpers. Missing history remains missing; the frozen model
preprocessor may later impute model inputs, but this module never invents rows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from .adapters.base import RideBaseSourceAdapter
from .landmarks import (
    FEATURE_COLUMNS,
    _due_task_features,
    _history_features,
    _primary_policy_table,
)
from .source_contract import HistoryFeatureRequest, Provenance, UnknownMotorcycleError


@dataclass(frozen=True)
class FeatureMapping:
    sources: str
    derivation: str
    timestamp_boundary: str
    leakage_risk: str
    missing_behavior: str
    provenance: str
    reproducibility: str


def _mapping(
    sources: str,
    derivation: str,
    timestamp: str,
    provenance: Provenance,
    classification: str,
    leakage: str = "LOW",
    missing: str = "null; frozen preprocessor may impute",
) -> FeatureMapping:
    return FeatureMapping(sources, derivation, timestamp, leakage, missing, provenance.value, classification)


# Machine-readable companion to docs/v2_1_history_pipeline_contract.md.  Keeping
# this exhaustive makes feature-list drift fail tests instead of becoming silent.
FEATURE_MAPPING: dict[str, FeatureMapping] = {
    "brand": _mapping("motorcycles", "motorcycle brand", "observation_start_date <= T", Provenance.SOURCE_MOTORCYCLE, "directly available"),
    "category": _mapping("motorcycles", "motorcycle category", "observation_start_date <= T", Provenance.SOURCE_MOTORCYCLE, "directly available"),
    "powertrain_type": _mapping("motorcycles", "motorcycle powertrain", "observation_start_date <= T", Provenance.SOURCE_MOTORCYCLE, "directly available"),
    "policy_group": _mapping("ridebase_motorcycle_models_v1", "model policy group", "unversioned model master", Provenance.MODEL_MASTER, "directly available", "MEDIUM"),
    "customer_type": _mapping("customers", "linked customer type", "first_seen_date <= T", Provenance.SOURCE_CUSTOMER, "customer/history-derived", "MEDIUM"),
    "usage_type": _mapping("usage_profiles", "active profile at T", "profile_start_date <= T <= profile_end_date", Provenance.HISTORY_DERIVED, "customer/history-derived"),
    "riding_intensity": _mapping("usage_profiles", "active profile at T", "profile_start_date <= T <= profile_end_date", Provenance.HISTORY_DERIVED, "customer/history-derived"),
    "climate_zone": _mapping("usage_profiles", "active profile at T", "profile_start_date <= T <= profile_end_date", Provenance.HISTORY_DERIVED, "customer/history-derived"),
    "storage_condition": _mapping("usage_profiles", "active profile at T", "profile_start_date <= T <= profile_end_date", Provenance.HISTORY_DERIVED, "customer/history-derived"),
    "workshop_region": _mapping("workshops", "motorcycle workshop region", "unversioned workshop master", Provenance.HISTORY_DERIVED, "directly available", "MEDIUM"),
    "workshop_price_level": _mapping("workshops", "motorcycle workshop price level", "unversioned workshop master", Provenance.HISTORY_DERIVED, "directly available", "MEDIUM"),
    "last_service_type_code": _mapping("services", "last eligible service type", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "last_arrival_mode": _mapping("services", "last eligible service arrival mode", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "production_age_days": _mapping("motorcycles", "T - first_registration_date, clipped at zero", "first_registration_date <= T", Provenance.LANDMARK_DERIVED, "landmark-derived"),
    "ownership_age_days": _mapping("motorcycles", "T - ownership_start_date, clipped at zero", "ownership_start_date <= T", Provenance.LANDMARK_DERIVED, "landmark-derived"),
    "is_fleet_customer": _mapping("customers", "linked customer fleet flag", "first_seen_date <= T", Provenance.SOURCE_CUSTOMER, "customer/history-derived", "MEDIUM"),
    "current_odometer_km_at_landmark": _mapping("mileage_timeline_monthly", "latest valid closing_odometer_km", "period_end_date <= T", Provenance.SOURCE_MILEAGE_HISTORY, "mileage-history-derived", missing="null; never use initial_mileage_km"),
    "annual_km_baseline": _mapping("usage_profiles", "active profile annual baseline", "profile_start_date <= T <= profile_end_date", Provenance.HISTORY_DERIVED, "customer/history-derived"),
    "recent_90d_km": _mapping("mileage_timeline_monthly", "sum month exposure matching frozen 3-month rule", "period_end_date <= T; window ending T", Provenance.SOURCE_MILEAGE_HISTORY, "mileage-history-derived"),
    "recent_vs_baseline_usage_ratio": _mapping("mileage_timeline_monthly; usage_profiles", "recent_90d_km annualized / annual baseline", "both inputs known <= T", Provenance.HISTORY_DERIVED, "mileage-history-derived"),
    "days_since_last_service": _mapping("services", "T - last eligible received date", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "km_since_last_service": _mapping("mileage_timeline_monthly; services", "current odometer - last eligible service odometer, clipped zero", "both inputs <= T", Provenance.HISTORY_DERIVED, "service-history-derived"),
    "avg_km_per_day_since_last_service": _mapping("mileage_timeline_monthly; services", "km since / days since; zero on same day", "both inputs <= T", Provenance.HISTORY_DERIVED, "service-history-derived"),
    "oem_interval_days": _mapping("maintenance_policies; model master", "frozen primary-policy selection; months * 30.4375", "unversioned policy/model master", Provenance.POLICY_DERIVED, "policy-derived", "MEDIUM"),
    "oem_interval_km": _mapping("maintenance_policies; model master", "frozen primary-policy km interval", "unversioned policy/model master", Provenance.POLICY_DERIVED, "policy-derived", "MEDIUM"),
    "days_due_ratio": _mapping("services; maintenance_policies", "days since service / OEM days", "history <= T; unversioned policy", Provenance.POLICY_DERIVED, "policy-derived", "MEDIUM"),
    "km_due_ratio": _mapping("mileage; services; maintenance_policies", "km since service / OEM km", "history <= T; unversioned policy", Provenance.POLICY_DERIVED, "policy-derived", "MEDIUM"),
    "max_due_ratio": _mapping("derived ratios", "max non-null due ratio", "inputs known <= T", Provenance.POLICY_DERIVED, "policy-derived"),
    "days_overdue": _mapping("services; maintenance_policies", "max(days since - OEM days, 0)", "history <= T; unversioned policy", Provenance.POLICY_DERIVED, "policy-derived", "MEDIUM"),
    "km_overdue": _mapping("mileage; services; maintenance_policies", "max(km since - OEM km, 0)", "history <= T; unversioned policy", Provenance.POLICY_DERIVED, "policy-derived", "MEDIUM"),
    "maintenance_due_now": _mapping("service_tasks; policies; mileage", "one or more applicable tasks due", "completed_at/odometer <= T", Provenance.POLICY_DERIVED, "task/part-derived", "MEDIUM"),
    "due_task_count": _mapping("service_tasks; maintenance_policies", "count applicable due tasks", "completed_at <= T; unversioned policy", Provenance.POLICY_DERIVED, "task/part-derived", "MEDIUM"),
    "critical_due_task_count": _mapping("service_tasks; maintenance_policies", "count critical applicable due tasks", "completed_at <= T; unversioned policy", Provenance.POLICY_DERIVED, "task/part-derived", "MEDIUM"),
    "days_until_next_scheduled_due": _mapping("service_tasks; maintenance_policies", "minimum nonnegative remaining days", "completed_at <= T; unversioned policy", Provenance.POLICY_DERIVED, "task/part-derived", "MEDIUM"),
    "km_until_next_scheduled_due": _mapping("service_tasks; maintenance_policies; mileage", "minimum nonnegative remaining km", "completed_at/period_end_date <= T", Provenance.POLICY_DERIVED, "task/part-derived", "MEDIUM"),
    "recent_service_count_90d": _mapping("services", "eligible services in inclusive frozen 90d window", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "recent_service_count_365d": _mapping("services", "eligible services in inclusive frozen 365d window", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "prior_service_count": _mapping("services", "all eligible services through T", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "prior_periodic_service_count": _mapping("services", "eligible PERIODIC services through T", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "prior_breakdown_count": _mapping("services", "eligible BREAKDOWN services through T", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "prior_repair_count": _mapping("services", "eligible REPAIR services through T", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "historical_service_delay_mean_days": _mapping("services", "mean delay, frozen missing-as-zero service rule", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived", "MEDIUM"),
    "historical_on_time_rate": _mapping("services", "share delay <= 0 under frozen rule", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived", "MEDIUM"),
    "cumulative_service_spend": _mapping("services", "sum grand_total, frozen missing-as-zero rule", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived", "MEDIUM"),
    "last_service_was_breakdown": _mapping("services", "last eligible is_breakdown", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "last_service_was_warranty": _mapping("services", "last eligible is_warranty", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived"),
    "last_service_task_count": _mapping("service_tasks; services", "known task-row count for last eligible service", "completed_at <= T; declined task started_at <= T; service received_at <= T", Provenance.SOURCE_TASK_HISTORY, "task/part-derived"),
    "last_service_spend": _mapping("services", "last eligible grand_total, frozen missing-as-zero rule", "received_at.date <= T", Provenance.SOURCE_SERVICE_HISTORY, "service-history-derived", "MEDIUM"),
    "service_bay_count": _mapping("workshops", "linked workshop master value", "unversioned workshop master", Provenance.HISTORY_DERIVED, "directly available", "HIGH"),
    "appointment_rate": _mapping("workshops", "linked workshop master rate (not appointment history)", "unversioned workshop master", Provenance.HISTORY_DERIVED, "directly available", "HIGH"),
    "avg_parts_lead_days": _mapping("workshops", "linked workshop master value", "unversioned workshop master", Provenance.HISTORY_DERIVED, "directly available", "HIGH"),
    "customer_volume_index": _mapping("workshops", "linked workshop master value", "unversioned workshop master", Provenance.HISTORY_DERIVED, "directly available", "HIGH"),
    "landmark_month_sin": _mapping("landmark_date", "sin(2*pi*month/12)", "request T", Provenance.LANDMARK_DERIVED, "landmark-derived"),
    "landmark_month_cos": _mapping("landmark_date", "cos(2*pi*month/12)", "request T", Provenance.LANDMARK_DERIVED, "landmark-derived"),
}


def build_features(
    motorcycle_id: Any,
    landmark_date: Any,
    source_adapter: RideBaseSourceAdapter,
) -> dict[str, Any]:
    """Reconstruct the frozen 54-feature map from history known at/before T."""
    request = HistoryFeatureRequest.parse(motorcycle_id, landmark_date)
    motorcycle = source_adapter.get_motorcycle(request.motorcycle_id, request.landmark_date)
    if motorcycle is None:
        raise UnknownMotorcycleError(
            f"unknown motorcycle_id {request.motorcycle_id!r} at {request.landmark_date.isoformat()}"
        )

    histories = {
        "services": source_adapter.get_services_before(request.motorcycle_id, request.landmark_date),
        "mileage": source_adapter.get_mileage_before(request.motorcycle_id, request.landmark_date),
        "tasks": source_adapter.get_service_tasks_before(request.motorcycle_id, request.landmark_date),
        "parts": source_adapter.get_service_parts_before(request.motorcycle_id, request.landmark_date),
        "appointments": source_adapter.get_appointments_before(request.motorcycle_id, request.landmark_date),
    }
    context = {
        "customer": source_adapter.get_customer_for_motorcycle(request.motorcycle_id, request.landmark_date),
        "usage_profile": source_adapter.get_usage_profile(request.motorcycle_id, request.landmark_date),
        "workshops": source_adapter.get_workshop_history(request.motorcycle_id, request.landmark_date),
        "model_master": source_adapter.get_model_master(request.motorcycle_id, request.landmark_date),
        "maintenance_policies": source_adapter.get_maintenance_policy(request.motorcycle_id, request.landmark_date),
    }

    features = {name: None for name in FEATURE_COLUMNS}
    provenance = {name: Provenance.MISSING_HISTORY.value for name in FEATURE_COLUMNS}

    def put(name: str, value: Any, source: Provenance) -> None:
        value = _json_value(value)
        if value is None:
            return
        features[name] = value
        provenance[name] = source.value

    # Direct source/master fields.
    for name in ("brand", "category", "powertrain_type"):
        put(name, motorcycle.get(name), Provenance.SOURCE_MOTORCYCLE)
    customer = context["customer"]
    if customer:
        put("customer_type", customer.get("customer_type"), Provenance.SOURCE_CUSTOMER)
        put("is_fleet_customer", customer.get("is_fleet_customer"), Provenance.SOURCE_CUSTOMER)
    model = context["model_master"]
    if model:
        put("policy_group", model.get("policy_group"), Provenance.MODEL_MASTER)
    usage = context["usage_profile"]
    if usage:
        for name in ("usage_type", "riding_intensity", "climate_zone", "storage_condition", "annual_km_baseline"):
            put(name, usage.get(name), Provenance.HISTORY_DERIVED)
    workshop = context["workshops"][0] if context["workshops"] else None
    if workshop:
        put("workshop_region", workshop.get("region"), Provenance.HISTORY_DERIVED)
        put("workshop_price_level", workshop.get("price_level"), Provenance.HISTORY_DERIVED)
        for name in ("service_bay_count", "appointment_rate", "avg_parts_lead_days", "customer_volume_index"):
            put(name, workshop.get(name), Provenance.HISTORY_DERIVED)

    registration = _date_or_none(motorcycle.get("first_registration_date"))
    if registration:
        put("production_age_days", max((request.landmark_date - registration).days, 0), Provenance.LANDMARK_DERIVED)
    ownership = _date_or_none(motorcycle.get("ownership_start_date"))
    if ownership:
        put("ownership_age_days", max((request.landmark_date - ownership).days, 0), Provenance.LANDMARK_DERIVED)
    month = request.landmark_date.month
    put("landmark_month_sin", math.sin(2.0 * math.pi * month / 12.0), Provenance.LANDMARK_DERIVED)
    put("landmark_month_cos", math.cos(2.0 * math.pi * month / 12.0), Provenance.LANDMARK_DERIVED)

    # Mileage semantics exactly mirror the monthly offline builder: current
    # closing odometer and a rolling three-source-row (90d label) km sum.
    valid_mileage: list[tuple[str, str, float]] = []
    for row in histories["mileage"]:
        odometer = _float_or_none(row.get("closing_odometer_km"))
        if odometer is not None and odometer >= 0:
            valid_mileage.append((str(row["_effective_at"]), str(row.get("timeline_id", "")), odometer))
    odometer_evidence = None
    if valid_mileage:
        odometer_date, timeline_id, odometer = max(valid_mileage, key=lambda item: (item[0], item[1]))
        put("current_odometer_km_at_landmark", odometer, Provenance.SOURCE_MILEAGE_HISTORY)
        odometer_evidence = {
            "timeline_id": timeline_id or None,
            "period_end_date": odometer_date,
            "closing_odometer_km": odometer,
        }
    if histories["mileage"]:
        last_three = histories["mileage"][-3:]
        added = [_float_or_none(row.get("km_added")) for row in last_three]
        finite_added = [value for value in added if value is not None]
        if finite_added:
            put("recent_90d_km", sum(finite_added), Provenance.SOURCE_MILEAGE_HISTORY)
    recent = _float_or_none(features["recent_90d_km"])
    annual = _float_or_none(features["annual_km_baseline"])
    if recent is not None and annual is not None and annual > 0:
        put("recent_vs_baseline_usage_ratio", (recent * (365.25 / 90.0)) / annual, Provenance.HISTORY_DERIVED)

    # Only frozen eligible statuses enter service-derived features.
    eligible_services = [
        dict(row) for row in histories["services"]
        if str(row.get("status", "")).upper() == "DELIVERED"
    ]
    eligible_services.sort(key=lambda row: (str(row.get("_effective_at", "")), str(row.get("service_id", ""))))
    service_frame = _service_frame(eligible_services)
    last_service = eligible_services[-1] if eligible_services else None
    if last_service:
        put("last_service_type_code", last_service.get("service_type_code"), Provenance.SOURCE_SERVICE_HISTORY)
        put("last_arrival_mode", last_service.get("arrival_mode"), Provenance.SOURCE_SERVICE_HISTORY)
        put("last_service_was_breakdown", _frozen_zero(last_service.get("is_breakdown")), Provenance.SOURCE_SERVICE_HISTORY)
        put("last_service_was_warranty", _frozen_zero(last_service.get("is_warranty")), Provenance.SOURCE_SERVICE_HISTORY)
        put("last_service_spend", _frozen_zero(last_service.get("grand_total")), Provenance.SOURCE_SERVICE_HISTORY)
        last_date = _date_or_none(last_service.get("_effective_at"))
        if last_date:
            days_since = (request.landmark_date - last_date).days
            put("days_since_last_service", days_since, Provenance.SOURCE_SERVICE_HISTORY)
        else:
            days_since = None
        current_odo = _float_or_none(features["current_odometer_km_at_landmark"])
        service_odo = _float_or_none(last_service.get("odometer_km"))
        if current_odo is not None and service_odo is not None:
            km_since = max(current_odo - service_odo, 0.0)
            put("km_since_last_service", km_since, Provenance.HISTORY_DERIVED)
            if days_since is not None:
                put(
                    "avg_km_per_day_since_last_service",
                    km_since / days_since if days_since > 0 else 0.0,
                    Provenance.HISTORY_DERIVED,
                )
        last_service_id = str(last_service.get("service_id", ""))
        last_task_count = sum(str(row.get("service_id", "")) == last_service_id for row in histories["tasks"])
        put("last_service_task_count", last_task_count, Provenance.SOURCE_TASK_HISTORY)

        # Reuse the offline prefix/window aggregation implementation.
        stub = pd.DataFrame({
            "motorcycle_id": [request.motorcycle_id],
            "landmark_at": [pd.Timestamp(request.landmark_date)],
        })
        aggregated = _history_features(stub, service_frame).iloc[0]
        for name in (
            "recent_service_count_90d", "recent_service_count_365d", "prior_service_count",
            "prior_periodic_service_count", "prior_breakdown_count", "prior_repair_count",
            "historical_service_delay_mean_days", "historical_on_time_rate", "cumulative_service_spend",
        ):
            put(name, aggregated[name], Provenance.SOURCE_SERVICE_HISTORY)

    # Reuse frozen primary-policy selection and due-task formulas.
    policies = context["maintenance_policies"]
    primary = None
    if model and policies:
        primary_table = _primary_policy_table(pd.DataFrame([model]), pd.DataFrame(policies))
        if not primary_table.empty:
            primary = primary_table.iloc[0]
            put("oem_interval_days", primary.get("oem_interval_days"), Provenance.POLICY_DERIVED)
            put("oem_interval_km", primary.get("oem_interval_km"), Provenance.POLICY_DERIVED)
    days_since = _float_or_none(features["days_since_last_service"])
    km_since = _float_or_none(features["km_since_last_service"])
    oem_days = _float_or_none(features["oem_interval_days"])
    oem_km = _float_or_none(features["oem_interval_km"])
    if days_since is not None and oem_days is not None and oem_days > 0:
        put("days_due_ratio", days_since / oem_days, Provenance.POLICY_DERIVED)
        put("days_overdue", max(days_since - oem_days, 0.0), Provenance.POLICY_DERIVED)
    if km_since is not None and oem_km is not None and oem_km > 0:
        put("km_due_ratio", km_since / oem_km, Provenance.POLICY_DERIVED)
        put("km_overdue", max(km_since - oem_km, 0.0), Provenance.POLICY_DERIVED)
    ratios = [
        value for value in (
            _float_or_none(features["days_due_ratio"]),
            _float_or_none(features["km_due_ratio"]),
        ) if value is not None
    ]
    if ratios:
        put("max_due_ratio", max(ratios), Provenance.POLICY_DERIVED)

    observation_start = _date_or_none(motorcycle.get("observation_start_date"))
    initial_odo = _float_or_none(motorcycle.get("initial_mileage_km"))
    current_odo = _float_or_none(features["current_odometer_km_at_landmark"])
    policy_group = features["policy_group"]
    if model and policies and observation_start and initial_odo is not None and current_odo is not None and policy_group:
        task_events = []
        services_by_id = {str(row.get("service_id")): row for row in eligible_services}
        for task in histories["tasks"]:
            if _float_or_none(task.get("completed")) != 1.0:
                continue
            service = services_by_id.get(str(task.get("service_id")))
            if not service:
                continue
            task_events.append({
                "motorcycle_id": request.motorcycle_id,
                "task_code": task.get("task_code"),
                # Frozen offline semantics anchor completed tasks to service_at.
                "task_at": pd.Timestamp(service["_effective_at"]),
                "task_odometer_km": _float_or_none(service.get("odometer_km")),
            })
        task_frame = pd.DataFrame(
            task_events,
            columns=["motorcycle_id", "task_code", "task_at", "task_odometer_km"],
        )
        due_stub = pd.DataFrame({
            "motorcycle_id": [request.motorcycle_id],
            "landmark_at": [pd.Timestamp(request.landmark_date)],
            "current_odometer_km_at_landmark": [current_odo],
            "model_id": [str(motorcycle.get("model_id"))],
            "policy_group": [str(policy_group)],
            "observation_start_date": [pd.Timestamp(observation_start)],
            # Legitimate baseline for due-task elapsed km only; never current odo.
            "initial_mileage_km": [initial_odo],
        })
        due = _due_task_features(due_stub, service_frame, task_frame, pd.DataFrame(policies)).iloc[0]
        for name in (
            "due_task_count", "critical_due_task_count", "days_until_next_scheduled_due",
            "km_until_next_scheduled_due", "maintenance_due_now",
        ):
            put(name, due[name], Provenance.POLICY_DERIVED)

    resolved = [name for name, value in features.items() if value is not None]
    missing = [name for name in FEATURE_COLUMNS if name not in resolved]
    warnings = ["Feature coverage describes source resolution, not prediction confidence."]
    if not histories["mileage"]:
        warnings.append("No mileage history at/before landmark; current odometer remains missing.")
    if not eligible_services:
        warnings.append("No eligible DELIVERED service at/before landmark; service-history features remain missing.")
    if not customer:
        warnings.append("Customer history is missing at the landmark.")
    if not usage:
        warnings.append("Usage-profile history is missing at the landmark.")
    if not workshop:
        warnings.append("Workshop master history is missing at the landmark.")
    if not model:
        warnings.append("Motorcycle model master is missing; policy features remain missing.")

    last_service_evidence = None
    if last_service:
        last_service_evidence = {
            "service_id": last_service.get("service_id"),
            "received_date": last_service.get("_effective_at"),
            "odometer_km": _json_value(last_service.get("odometer_km")),
        }

    return {
        "features": features,
        "provenance": provenance,
        "source_evidence": {
            "motorcycle_found": True,
            "customer_found": context["customer"] is not None,
            "model_master_found": context["model_master"] is not None,
            "usage_profile_found": context["usage_profile"] is not None,
            "workshop_records": len(context["workshops"]),
            "maintenance_policy_records": len(context["maintenance_policies"]),
            "eligible_service_records": len(eligible_services),
            "history_record_counts": {name: len(rows) for name, rows in histories.items()},
            "max_effective_at": {
                name: max((str(row.get("_effective_at")) for row in rows if row.get("_effective_at")), default=None)
                for name, rows in histories.items()
            },
            "current_odometer_source": odometer_evidence,
            "last_eligible_service": last_service_evidence,
            "history_source": getattr(source_adapter, "history_source", type(source_adapter).__name__),
        },
        "warnings": warnings,
        "feature_coverage": {
            "resolved_count": len(resolved),
            "contract_count": len(FEATURE_COLUMNS),
            "resolved_features": resolved,
            "missing_features": missing,
            "ratio": len(resolved) / len(FEATURE_COLUMNS),
            "is_confidence": False,
        },
        "landmark": {
            "motorcycle_id": request.motorcycle_id,
            "landmark_date": request.landmark_date.isoformat(),
            "inclusive_boundary": True,
        },
    }


def _service_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "motorcycle_id", "service_at", "service_id", "odometer_km", "service_type_code",
        "service_delay_days", "grand_total",
    ]
    built = []
    for row in rows:
        built.append({
            "motorcycle_id": row.get("motorcycle_id"),
            "service_at": pd.Timestamp(row.get("_effective_at")),
            "service_id": row.get("service_id"),
            "odometer_km": _float_or_none(row.get("odometer_km")),
            "service_type_code": row.get("service_type_code"),
            "service_delay_days": _float_or_none(row.get("service_delay_days")),
            "grand_total": _float_or_none(row.get("grand_total")),
        })
    frame = pd.DataFrame(built, columns=columns)
    for name in ("odometer_km", "service_delay_days", "grand_total"):
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    return frame


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _frozen_zero(value: Any) -> float:
    number = _float_or_none(value)
    return number if number is not None else 0.0


def _date_or_none(value: Any) -> date | None:
    if value is None or value == "" or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _json_value(value: Any) -> Any:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return value
