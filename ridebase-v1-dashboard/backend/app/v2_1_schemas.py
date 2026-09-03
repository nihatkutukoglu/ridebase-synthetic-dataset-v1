"""V2.1 request schemas. typing.Optional/Dict/List for Python 3.9."""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_LEAK_TOKENS = ("duration_days", "event_observed", "next_service", "administrative_cutoff",
                "event_within_", "censor", "future_", "primary_split", "modeling_role",
                "is_unseen_motorcycle_holdout", "snapshot_year", "days_observed")


def _reject_leakage(v: Dict[str, Any]) -> Dict[str, Any]:
    bad = [k for k in v if any(tok in str(k).lower() for tok in _LEAK_TOKENS)]
    if bad:
        raise ValueError(f"target/censoring/future fields are not allowed in a V2.1 request: {bad[:8]}")
    return v


class V21PredictRequest(BaseModel):
    features: Dict[str, Any] = Field(
        default_factory=dict,
        description="Landmark feature map (canonical names from GET /api/v2_1/features). "
                    "Missing inputs are imputed by the frozen train-time preprocessor.",
    )
    strict: bool = Field(default=False, description="422 on any unknown feature key when true.")

    @field_validator("features")
    @classmethod
    def _no_leakage(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        return _reject_leakage(v)


class V21BatchPredictRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(default_factory=list, max_length=2000)
    strict: bool = Field(default=False)

    @field_validator("items")
    @classmethod
    def _no_leakage_each(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for row in v:
            _reject_leakage(row)
        return v


class V21ScenarioRequest(BaseModel):
    """Natural product inputs for an honest partial-scenario prediction. No free-form
    feature map: the server resolves model-master + deterministic landmark/policy
    features; every other frozen V2.1 input stays genuinely missing."""

    model_config = ConfigDict(extra="forbid")

    brand: str = Field(min_length=1, max_length=80)
    model_id: str = Field(min_length=1, max_length=120)
    production_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    landmark_date: dt.date = Field(description="The 'today' the prediction is anchored to.")
    current_odometer_km: Optional[float] = Field(default=None, ge=0, le=2_000_000)
    annual_km_baseline: Optional[float] = Field(default=None, ge=0, le=200_000)
    usage_type: Optional[str] = Field(default=None, max_length=80)
    riding_intensity: Optional[str] = Field(default=None, max_length=80)
    last_service_date: Optional[dt.date] = None
    last_service_odometer_km: Optional[float] = Field(default=None, ge=0, le=2_000_000)


class V21ByMotorcycleRequest(BaseModel):
    """Canonical production-style history input; no manual feature overrides."""

    model_config = ConfigDict(extra="forbid")

    motorcycle_id: str = Field(min_length=1, max_length=120)
    landmark_date: dt.date
