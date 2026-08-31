"""Request / response schemas. The prediction request is intentionally a typed
envelope around a ``features`` map - the *authoritative* field list comes from
the frozen model metadata (``GET /api/v1/features``), not from a hand-written
column list that would drift from the artifacts.

Typing note: kept to ``typing.Optional`` / ``Dict`` / ``List`` so the models
evaluate on Python 3.9 (no ``X | None`` runtime unions).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .artifacts import DERIVED_FROM_DATE, contains_leak


class PredictRequest(BaseModel):
    features: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw snapshot feature map (canonical column names). "
                    "Missing model inputs are imputed by the frozen train-time preprocessor.",
    )
    snapshot_date: Optional[dt.date] = Field(
        default=None,
        description="Date of the snapshot. Used to derive the cyclical snapshot_* "
                    "features and to compute the absolute estimated service date.",
    )
    strict: bool = Field(default=True, description="422 on any validation error when true.")

    @field_validator("features")
    @classmethod
    def _no_target_fields(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        bad = {k: contains_leak(k) for k in v if contains_leak(k)}
        if bad:
            raise ValueError(f"target/future fields are not allowed: {bad}")
        derived = [k for k in v if k in DERIVED_FROM_DATE]
        if derived:
            raise ValueError(f"{derived} are derived from snapshot_date; send snapshot_date instead")
        return v


class BatchPredictRequest(BaseModel):
    items: List[PredictRequest] = Field(default_factory=list, max_length=200)


class Prediction(BaseModel):
    next_service_days: float
    next_service_km: float


class Derived(BaseModel):
    estimated_service_date: Optional[str] = None
    estimated_service_odometer_km: Optional[float] = None


class PredictResponse(BaseModel):
    prediction: Prediction
    derived: Derived
    typical_model_error: Dict[str, Any]
    input_diagnostics: Dict[str, Any]
    model: Dict[str, Any]
    warning: str
