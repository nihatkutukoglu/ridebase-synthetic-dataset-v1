"""Request models for /api/v3/*."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .v3_service import MAX_BATCH

TOP_K_FIELD = Field(3, ge=1, le=10, description="how many ranked tasks to return")


class V3PredictRequest(BaseModel):
    features: Dict[str, Any] = Field(..., description="complete frozen V3 feature row")
    motorcycle_id: Optional[str] = Field(
        None, description="optional; enables the hardware applicability mask")
    landmark_date: Optional[str] = None
    top_k: int = TOP_K_FIELD
    include_hidden: bool = Field(
        False, description="also rank HIDDEN_BY_DEFAULT labels (random-event tasks)")


class V3BatchPredictRequest(BaseModel):
    rows: List[Dict[str, Any]] = Field(..., min_length=1, max_length=MAX_BATCH)
    motorcycle_ids: Optional[List[str]] = None
    top_k: int = TOP_K_FIELD
    include_hidden: bool = False


class V3ByMotorcycleRequest(BaseModel):
    motorcycle_id: str = Field(..., min_length=1)
    landmark_date: str = Field(..., description="YYYY-MM-DD")
    top_k: int = TOP_K_FIELD
    include_hidden: bool = False


class V3MotorcycleContext(BaseModel):
    """Product-safe subject identity and PIT context for a V3 prediction."""

    model_config = ConfigDict(extra="forbid")

    motorcycle_id: str
    landmark_date: str
    source: str = "SYNTHETIC_HISTORY_V1_4"
    brand: Optional[str] = None
    model: Optional[str] = None
    model_year: Optional[int] = None
    category: Optional[str] = None
    current_odometer_km: Optional[float] = None
    last_service_date: Optional[str] = None
    last_service_odometer_km: Optional[float] = None
    km_since_last_service: Optional[float] = None
    days_since_last_service: Optional[int] = None
    annual_usage_km: Optional[float] = None
