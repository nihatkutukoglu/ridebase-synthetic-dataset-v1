"""Request models for /api/v3/*."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

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
