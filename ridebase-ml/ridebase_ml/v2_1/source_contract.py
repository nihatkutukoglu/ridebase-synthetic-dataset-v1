"""Canonical input/output and provenance vocabulary for history inference."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any


class Provenance(str, Enum):
    SOURCE_MOTORCYCLE = "SOURCE_MOTORCYCLE"
    SOURCE_CUSTOMER = "SOURCE_CUSTOMER"
    SOURCE_SERVICE_HISTORY = "SOURCE_SERVICE_HISTORY"
    SOURCE_MILEAGE_HISTORY = "SOURCE_MILEAGE_HISTORY"
    SOURCE_TASK_HISTORY = "SOURCE_TASK_HISTORY"
    SOURCE_PART_HISTORY = "SOURCE_PART_HISTORY"
    SOURCE_APPOINTMENT_HISTORY = "SOURCE_APPOINTMENT_HISTORY"
    MODEL_MASTER = "MODEL_MASTER"
    POLICY_DERIVED = "POLICY_DERIVED"
    LANDMARK_DERIVED = "LANDMARK_DERIVED"
    HISTORY_DERIVED = "HISTORY_DERIVED"
    MISSING_HISTORY = "MISSING_HISTORY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class UnknownMotorcycleError(LookupError):
    """The requested motorcycle is not present/observable at the landmark."""


class HistoryInputError(ValueError):
    """The canonical motorcycle/date request is invalid."""


@dataclass(frozen=True)
class HistoryFeatureRequest:
    motorcycle_id: str
    landmark_date: date

    @classmethod
    def parse(cls, motorcycle_id: Any, landmark_date: Any) -> "HistoryFeatureRequest":
        identifier = str(motorcycle_id or "").strip()
        if not identifier:
            raise HistoryInputError("motorcycle_id is required")
        if isinstance(landmark_date, date):
            parsed = landmark_date
        else:
            try:
                parsed = date.fromisoformat(str(landmark_date))
            except (TypeError, ValueError) as exc:
                raise HistoryInputError("landmark_date must be YYYY-MM-DD") from exc
        return cls(identifier, parsed)


HistoryFeaturePayload = dict[str, Any]
