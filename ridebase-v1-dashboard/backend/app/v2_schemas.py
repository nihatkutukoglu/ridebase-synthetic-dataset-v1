"""V2 request schemas. Kept to typing.Optional/Dict/List for Python 3.9."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

_LEAK_TOKENS = ("duration_days", "event_observed", "next_service", "next_event", "censor",
                "future_", "survival_target", "_audit", "target_event", "days_to_event",
                "time_to_event", "is_right_censored")


def _reject_leakage(v: Dict[str, Any]) -> Dict[str, Any]:
    bad = [k for k in v if any(tok in str(k).lower() for tok in _LEAK_TOKENS)]
    if bad:
        raise ValueError(f"target/future fields are not allowed in a V2 request: {bad[:8]}")
    return v


class V2PredictRequest(BaseModel):
    features: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw snapshot feature map (canonical names from GET /api/v2/features). "
                    "Missing inputs are imputed by the frozen train-time preprocessor; "
                    "do not send 'split'.",
    )
    snapshot_date: Optional[str] = Field(
        default=None, description="ISO date of the snapshot; enables estimated_median_service_date.")
    strict: bool = Field(default=False, description="422 on any out-of-distribution / unseen value when true.")

    @field_validator("features")
    @classmethod
    def _no_leakage(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        return _reject_leakage(v)


class V2BatchPredictRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(default_factory=list, max_length=2000,
                                        description="Up to 2000 raw snapshot feature maps.")
    strict: bool = Field(default=False)

    @field_validator("items")
    @classmethod
    def _no_leakage_each(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for row in v:
            _reject_leakage(row)
        return v


class UnifiedServiceRequest(BaseModel):
    """V1 + V2 in one call. features are the union of raw snapshot fields; each model
    takes what it needs from its own frozen contract."""
    features: Dict[str, Any] = Field(default_factory=dict)
    snapshot_date: Optional[str] = None

    @field_validator("features")
    @classmethod
    def _no_leakage(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        return _reject_leakage(v)
