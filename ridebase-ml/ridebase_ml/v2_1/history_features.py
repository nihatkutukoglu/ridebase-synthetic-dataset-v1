"""Canonical V2.1 history feature-builder contract (Prompt 1 foundation).

This module intentionally implements only universally safe contract behavior:
request validation, point-in-time source reads, exact frozen-key construction,
honest missingness/provenance, calendar features, and current-odometer selection.
The complete V1.4 derivation is the gated Prompt 2 deliverable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from .adapters.base import RideBaseSourceAdapter
from .landmarks import FEATURE_COLUMNS
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
    "last_service_task_count": _mapping("service_tasks; services", "completed task count for last eligible service", "task completed_at and service received_at <= T", Provenance.SOURCE_TASK_HISTORY, "task/part-derived"),
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
    """Build the canonical result envelope without inventing source history.

    Prompt 1 freezes the contract and resolves only the two calendar terms plus
    the latest valid mileage odometer. Prompt 2 fills the remaining frozen
    feature semantics through the same envelope and adapter calls.
    """
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
    month = request.landmark_date.month
    features["landmark_month_sin"] = float(math.sin(2.0 * math.pi * month / 12.0))
    features["landmark_month_cos"] = float(math.cos(2.0 * math.pi * month / 12.0))
    provenance["landmark_month_sin"] = Provenance.LANDMARK_DERIVED.value
    provenance["landmark_month_cos"] = Provenance.LANDMARK_DERIVED.value

    valid_mileage = []
    for row in histories["mileage"]:
        try:
            odometer = float(row.get("closing_odometer_km"))
        except (TypeError, ValueError):
            continue
        if np.isfinite(odometer) and odometer >= 0:
            valid_mileage.append((str(row["_effective_at"]), odometer))
    if valid_mileage:
        _, odometer = max(valid_mileage, key=lambda item: item[0])
        features["current_odometer_km_at_landmark"] = odometer
        provenance["current_odometer_km_at_landmark"] = Provenance.SOURCE_MILEAGE_HISTORY.value

    resolved = [name for name, value in features.items() if value is not None]
    missing = [name for name in FEATURE_COLUMNS if name not in resolved]
    warnings = [
        "Prompt 1 contract foundation: full frozen-feature derivation is gated to Prompt 2.",
        "Feature coverage describes source resolution, not prediction confidence.",
    ]
    if not histories["mileage"]:
        warnings.append("No mileage history at/before landmark; current odometer remains missing.")
    if not histories["services"]:
        warnings.append("No service history at/before landmark; service-history features remain missing.")

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
            "history_record_counts": {name: len(rows) for name, rows in histories.items()},
            "max_effective_at": {
                name: max((str(row.get("_effective_at")) for row in rows if row.get("_effective_at")), default=None)
                for name, rows in histories.items()
            },
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
