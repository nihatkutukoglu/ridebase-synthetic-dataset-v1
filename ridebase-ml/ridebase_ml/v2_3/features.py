"""Point-in-time V2.3 observable behavior-state feature definitions."""

from __future__ import annotations

from ridebase_ml.v2_2.landmarks import FEATURE_COLUMNS as EXTENDED60


GROUPS = {
    "appointment": [
        "appointments_180d", "attended_appointment_count", "no_show_rate",
        "cancellation_rate", "successful_appointment_rate", "rebook_after_no_show_rate",
        "days_since_last_appointment", "known_open_appointment_count",
        "recent_no_show_without_rebook",
    ],
    "adherence": [
        "overdue_service_share", "prior_service_delay_median", "prior_service_delay_p90",
        "last3_service_delay_trend", "interservice_days_cv", "interservice_km_cv",
        "recency_weighted_adherence_score", "service_gap_acceleration",
    ],
    "engagement": [
        "days_since_last_any_interaction", "interaction_count_90d",
        "interaction_count_180d", "appointment_frequency_365d",
    ],
    "workshop": [
        "distinct_workshops_before_landmark", "dominant_workshop_share", "same_workshop_streak",
    ],
    "usage": [
        "recent_30d_km", "recent_180d_km", "usage_velocity_ratio_30_vs_180",
        "usage_volatility_6m", "odometer_observation_recency_days", "km_growth_slope_6m",
    ],
    "breakdown": [
        "breakdown_count_90d", "repair_count_90d", "safety_critical_repair_recent",
        "days_since_last_breakdown", "repeated_breakdown_flag",
    ],
}

NEW_FEATURES = [name for values in GROUPS.values() for name in values]
FEATURE_COLUMNS = list(EXTENDED60) + NEW_FEATURES
CATEGORICAL_FEATURES = [name for name in FEATURE_COLUMNS if name in {
    "brand", "category", "powertrain_type", "policy_group", "customer_type", "usage_type",
    "riding_intensity", "climate_zone", "storage_condition", "workshop_region",
    "workshop_price_level", "last_service_type_code", "last_arrival_mode",
}]
NUMERIC_FEATURES = [name for name in FEATURE_COLUMNS if name not in CATEGORICAL_FEATURES]

SOURCE = {
    "appointment": "appointments.csv",
    "adherence": "services.csv",
    "engagement": "appointments.csv + services.csv",
    "workshop": "services.csv",
    "usage": "mileage_timeline_monthly.csv",
    "breakdown": "services.csv",
}

MISSING = {
    "days_since_last_appointment": "NaN when no prior scheduled appointment",
    "days_since_last_any_interaction": "NaN when no prior appointment creation or completed service",
    "days_since_last_breakdown": "NaN when no prior completed breakdown",
    "odometer_observation_recency_days": "NaN when no completed monthly observation",
}

FORMULAS = {
    "appointments_180d": "count scheduled appointments in [landmark-179d, landmark] created by landmark",
    "attended_appointment_count": "count prior appointments converted to service",
    "no_show_rate": "prior no-show count / prior completed appointment count; 0 with no history",
    "cancellation_rate": "prior cancellation count / prior completed appointment count; 0 with no history",
    "successful_appointment_rate": "prior converted count / prior completed appointment count; 0 with no history",
    "rebook_after_no_show_rate": "prior no-shows followed by a new appointment creation by landmark / prior no-shows",
    "days_since_last_appointment": "landmark minus latest prior scheduled appointment date",
    "known_open_appointment_count": "created by landmark and scheduled after landmark; outcome ignored",
    "recent_no_show_without_rebook": "1 when a no-show in prior 180d has no later creation by landmark",
    "overdue_service_share": "share of completed services with positive recorded pre-service overdue days or km",
    "prior_service_delay_median": "median service_delay_days over completed prior services",
    "prior_service_delay_p90": "90th percentile service_delay_days over completed prior services",
    "last3_service_delay_trend": "OLS slope by order over the last three completed service delays",
    "interservice_days_cv": "coefficient of variation of completed-service date gaps; 0 with <3 services",
    "interservice_km_cv": "coefficient of variation of positive odometer gaps; 0 with <3 services",
    "recency_weighted_adherence_score": "exp(-age/365)-weighted share with delay <= 0; 0.5 with no history",
    "service_gap_acceleration": "last completed-service day gap / prior-gap mean - 1; 0 with <3 services",
    "days_since_last_any_interaction": "landmark minus latest appointment creation or service delivery",
    "interaction_count_90d": "appointment creations plus service deliveries in prior 90d",
    "interaction_count_180d": "appointment creations plus service deliveries in prior 180d",
    "appointment_frequency_365d": "appointment creations in prior 365d",
    "distinct_workshops_before_landmark": "distinct workshops across completed prior services",
    "dominant_workshop_share": "largest completed-service workshop share; 0 with no history",
    "same_workshop_streak": "consecutive completed services at the most recent workshop",
    "recent_30d_km": "sum monthly km_added for observations ending in prior 30d",
    "recent_180d_km": "sum monthly km_added for observations ending in prior 180d",
    "usage_velocity_ratio_30_vs_180": "30d daily km / 180d daily km; 0 when 180d km is zero",
    "usage_volatility_6m": "coefficient of variation of last six observed monthly km values",
    "odometer_observation_recency_days": "landmark minus latest completed mileage period end",
    "km_growth_slope_6m": "OLS slope per observation over last six monthly km values",
    "breakdown_count_90d": "completed breakdown services in prior 90d",
    "repair_count_90d": "completed REPAIR services in prior 90d",
    "safety_critical_repair_recent": "1 for HIGH/CRITICAL completed failure in prior 180d",
    "days_since_last_breakdown": "landmark minus latest completed breakdown",
    "repeated_breakdown_flag": "1 for at least two completed breakdowns in prior 365d",
}


def contract_rows() -> list[dict]:
    rows = []
    for group, names in GROUPS.items():
        for name in names:
            rows.append({
                "name": name,
                "group": group,
                "source": SOURCE[group],
                "formula": FORMULAS[name],
                "landmark_cutoff": "only records whose effective/known timestamp is <= landmark_at",
                "missing_semantics": MISSING.get(name, "0 means no qualifying observed history"),
                "provenance": "raw V1.5 source history",
                "production_derivable": True,
                "leakage_risk": "LOW_WITH_ENFORCED_CUTOFF",
                "keep": True,
            })
    return rows
