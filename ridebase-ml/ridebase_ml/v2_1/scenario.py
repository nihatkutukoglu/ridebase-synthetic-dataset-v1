"""Honest partial-scenario feature derivation for V2.1.

Given natural product inputs (brand / model / year / current odometer / annual km /
usage / last service date+odometer) this resolves only what is genuinely knowable:

  MODEL_MASTER     brand, category, powertrain_type, policy_group      (model catalog)
  POLICY_DERIVED   oem_interval_days/km + the due ratios/overdue        (maintenance_policies)
  USER_INPUT       current odometer, annual km, usage_type, intensity
  LANDMARK_DERIVED days/km since last service, avg km/day, month sin/cos, production age

Everything else in the 54-feature contract is left MISSING for the frozen
preprocessor to impute — no demo-sample overlay, no invented history.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .landmarks import _primary_policy_table

_DEFAULT_SOURCES = Path(__file__).resolve().parents[2].parent / "ridebase_v1_4" / "source_tables"
_YEAR_DAYS = 365.25


def _sources(source_dir: Path | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = Path(source_dir or _DEFAULT_SOURCES)
    models = pd.read_csv(d / "ridebase_motorcycle_models_v1.csv")
    policies = pd.read_csv(d / "maintenance_policies.csv")
    return models, policies


class ScenarioInputError(ValueError):
    """Raised for a scenario that cannot be resolved (unknown model, bad dates)."""


def derive(scenario: dict[str, Any], source_dir: Path | None = None) -> dict[str, Any]:
    models, policies = _sources(source_dir)
    model_id = str(scenario.get("model_id", "")).strip()
    row = models.loc[models["model_id"] == model_id]
    if row.empty:
        raise ScenarioInputError(f"unknown model_id {model_id!r}")
    row = row.iloc[0]

    landmark_date = _as_date(scenario.get("landmark_date"), "landmark_date")
    features: dict[str, Any] = {}
    provenance: dict[str, str] = {}

    def put(name: str, value: Any, source: str) -> None:
        if value is None or (isinstance(value, float) and not np.isfinite(value)):
            return
        features[name] = value
        provenance[name] = source

    # --- model master -------------------------------------------------------
    put("brand", str(row["brand"]), "MODEL_MASTER")
    put("category", str(row["category"]), "MODEL_MASTER")
    put("powertrain_type", str(row["powertrain_type"]), "MODEL_MASTER")
    put("policy_group", str(row["policy_group"]), "MODEL_MASTER")

    # --- user input -------------------------------------------------------
    odo = _as_float(scenario.get("current_odometer_km"))
    put("current_odometer_km_at_landmark", odo, "USER_INPUT")  # NEVER initial_mileage_km
    annual = _as_float(scenario.get("annual_km_baseline"))
    put("annual_km_baseline", annual, "USER_INPUT")
    put("usage_type", _clean(scenario.get("usage_type")), "USER_INPUT")
    put("riding_intensity", _clean(scenario.get("riding_intensity")), "USER_INPUT")

    # --- landmark-derived ------------------------------------------------
    month = landmark_date.month
    put("landmark_month_sin", float(np.sin(2 * np.pi * month / 12)), "LANDMARK_DERIVED")
    put("landmark_month_cos", float(np.cos(2 * np.pi * month / 12)), "LANDMARK_DERIVED")
    prod_year = _as_float(scenario.get("production_year")) or _as_float(row.get("production_start_year"))
    if prod_year:
        age_days = (landmark_date - date(int(prod_year), 1, 1)).days
        put("production_age_days", float(max(age_days, 0)), "LANDMARK_DERIVED")

    last_date = _as_date(scenario.get("last_service_date"), "last_service_date", required=False)
    last_odo = _as_float(scenario.get("last_service_odometer_km"))
    days_since = km_since = None
    if last_date is not None:
        days_since = (landmark_date - last_date).days
        if days_since < 0:
            raise ScenarioInputError("last_service_date is after the landmark date")
        put("days_since_last_service", float(days_since), "LANDMARK_DERIVED")
    if odo is not None and last_odo is not None:
        km_since = odo - last_odo
        if km_since < 0:
            raise ScenarioInputError("current odometer is below the last-service odometer")
        put("km_since_last_service", float(km_since), "LANDMARK_DERIVED")
    if days_since and days_since > 0 and km_since is not None:
        put("avg_km_per_day_since_last_service", float(km_since / days_since), "LANDMARK_DERIVED")

    # --- policy-derived --------------------------------------------------
    primary = _primary_policy_table(pd.DataFrame([row]), policies)
    if not primary.empty:
        oem_km = _as_float(primary.iloc[0].get("oem_interval_km"))
        oem_days = _as_float(primary.iloc[0].get("oem_interval_days"))
        put("oem_interval_km", oem_km, "POLICY_DERIVED")
        put("oem_interval_days", oem_days, "POLICY_DERIVED")
        d_ratio = k_ratio = None
        if oem_days and days_since is not None:
            d_ratio = days_since / oem_days
            put("days_due_ratio", float(d_ratio), "POLICY_DERIVED")
            put("days_overdue", float(max(days_since - oem_days, 0.0)), "POLICY_DERIVED")
        if oem_km and km_since is not None:
            k_ratio = km_since / oem_km
            put("km_due_ratio", float(k_ratio), "POLICY_DERIVED")
            put("km_overdue", float(max(km_since - oem_km, 0.0)), "POLICY_DERIVED")
        ratios = [r for r in (d_ratio, k_ratio) if r is not None]
        if ratios:
            mx = max(ratios)
            put("max_due_ratio", float(mx), "POLICY_DERIVED")
            put("maintenance_due_now", int(mx >= 1.0), "POLICY_DERIVED")

    return {"features": features, "provenance": provenance, "landmark_date": landmark_date.isoformat()}


def _as_float(v: Any) -> float | None:
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _clean(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _as_date(v: Any, name: str, required: bool = True) -> date | None:
    if v is None or v == "":
        if required:
            raise ScenarioInputError(f"{name} is required")
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ScenarioInputError(f"{name} must be an ISO date (YYYY-MM-DD)")
