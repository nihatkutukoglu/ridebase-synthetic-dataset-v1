"""Point-in-time-safe, read-only source adapter contract.

Concrete adapters only implement :meth:`read_table`.  The public query methods
below own the cutoff semantics so a file, database, or API implementation cannot
silently give the feature builder records strictly after the landmark date.

The canonical landmark is a calendar date.  A timestamp on that date is included;
the comparison is therefore ``record_timestamp.date() <= landmark_date``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

Record = dict[str, Any]


class SourceContractError(ValueError):
    """A source row cannot be interpreted safely under the point-in-time contract."""


class RideBaseSourceAdapter(ABC):
    """Read-only source interface used by the canonical history feature builder.

    ``read_table`` must return detached mappings and must never modify its source.
    Implementations may cache/index internally.  Public methods return new dicts.
    """

    @abstractmethod
    def read_table(self, table_name: str) -> Sequence[Mapping[str, Any]]:
        """Read rows from a source table without mutating source state."""

    def motorcycle_exists(self, motorcycle_id: str) -> bool:
        """Return whether the identifier exists, independent of landmark eligibility."""
        return bool(self._matching("motorcycles", "motorcycle_id", motorcycle_id))

    def get_motorcycle(self, motorcycle_id: str, as_of: date) -> Record | None:
        rows = self._matching("motorcycles", "motorcycle_id", motorcycle_id)
        rows = self._at_or_before(rows, as_of, "observation_start_date", "motorcycles")
        return self._one_or_none(rows, "motorcycle_id", motorcycle_id)

    def get_customer_for_motorcycle(self, motorcycle_id: str, as_of: date) -> Record | None:
        motorcycle = self.get_motorcycle(motorcycle_id, as_of)
        if motorcycle is None or not motorcycle.get("customer_id"):
            return None
        customer_id = str(motorcycle["customer_id"])
        rows = self._matching("customers", "customer_id", customer_id)
        rows = self._at_or_before(rows, as_of, "first_seen_date", "customers")
        return self._one_or_none(rows, "customer_id", customer_id)

    def get_services_before(self, motorcycle_id: str, as_of: date) -> list[Record]:
        rows = self._matching("services", "motorcycle_id", motorcycle_id)
        return self._at_or_before(rows, as_of, "received_at", "services")

    def get_mileage_before(self, motorcycle_id: str, as_of: date) -> list[Record]:
        rows = self._matching("mileage_timeline_monthly", "motorcycle_id", motorcycle_id)
        return self._at_or_before(rows, as_of, "period_end_date", "mileage_timeline_monthly")

    def get_service_tasks_before(self, motorcycle_id: str, as_of: date) -> list[Record]:
        rows = self._matching("service_tasks", "motorcycle_id", motorcycle_id)
        cutoff = _coerce_date(as_of)
        accepted: list[tuple[date, Record]] = []
        for raw in rows:
            # Completed-task semantics use completed_at. Declined tasks have no
            # completed_at but are known once started and count in the frozen
            # last-service task-count feature.
            field = "completed_at" if raw.get("completed_at") not in (None, "") and not pd.isna(raw.get("completed_at")) else "started_at"
            effective = self._date_value(
                raw.get(field), f"service_tasks.{field}", allow_missing=True
            )
            if effective is not None and effective <= cutoff:
                row = dict(raw)
                row["_effective_at"] = effective.isoformat()
                accepted.append((effective, row))
        accepted.sort(key=lambda item: item[0])
        return [row for _, row in accepted]

    def get_service_parts_before(self, motorcycle_id: str, as_of: date) -> list[Record]:
        """Filter timestamp-less part rows through their point-in-time-safe parents.

        ``service_parts`` has no own event/insert timestamp. A row is eligible only
        when its service is eligible and, when present, its task is also eligible.
        This does not solve historical updates to an already-eligible row; that
        source-schema limitation is explicitly documented.
        """
        rows = self._matching("service_parts", "motorcycle_id", motorcycle_id)
        services = {
            str(row.get("service_id")): row
            for row in self.get_services_before(motorcycle_id, as_of)
        }
        tasks = {
            str(row.get("service_task_id")): row
            for row in self.get_service_tasks_before(motorcycle_id, as_of)
        }
        out: list[Record] = []
        for row in rows:
            service_id = str(row.get("service_id"))
            task_id = row.get("service_task_id")
            if service_id not in services:
                continue
            if task_id not in (None, "") and str(task_id) not in tasks:
                continue
            copied = dict(row)
            parent = tasks[str(task_id)] if task_id not in (None, "") else services[service_id]
            copied["_effective_at"] = parent.get("_effective_at")
            out.append(copied)
        return out

    def get_appointments_before(self, motorcycle_id: str, as_of: date) -> list[Record]:
        rows = self._matching("appointments", "motorcycle_id", motorcycle_id)
        return self._at_or_before(rows, as_of, "created_at", "appointments")

    def get_usage_profile(self, motorcycle_id: str, as_of: date) -> Record | None:
        rows = self._matching("usage_profiles", "motorcycle_id", motorcycle_id)
        rows = self._at_or_before(rows, as_of, "profile_start_date", "usage_profiles")
        active = []
        for row in rows:
            end = self._date_value(row.get("profile_end_date"), "usage_profiles.profile_end_date", allow_missing=True)
            if end is None or end >= as_of:
                active.append(row)
        if len(active) > 1:
            active.sort(key=lambda r: self._date_value(r.get("profile_start_date"), "usage_profiles.profile_start_date"))
            return dict(active[-1])
        return dict(active[0]) if active else None

    def get_workshop_history(self, motorcycle_id: str, as_of: date) -> list[Record]:
        motorcycle = self.get_motorcycle(motorcycle_id, as_of)
        if motorcycle is None or not motorcycle.get("workshop_id"):
            return []
        # The current schema is an unversioned workshop master. Returning the
        # matching row is allowed, but historical mutability remains documented.
        return self._matching("workshops", "workshop_id", str(motorcycle["workshop_id"]))

    def get_model_master(self, motorcycle_id: str, as_of: date) -> Record | None:
        motorcycle = self.get_motorcycle(motorcycle_id, as_of)
        if motorcycle is None or not motorcycle.get("model_id"):
            return None
        model_id = str(motorcycle["model_id"])
        return self._one_or_none(
            self._matching("ridebase_motorcycle_models_v1", "model_id", model_id),
            "model_id", model_id,
        )

    def get_maintenance_policy(self, motorcycle_id: str, as_of: date) -> list[Record]:
        motorcycle = self.get_motorcycle(motorcycle_id, as_of)
        model = self.get_model_master(motorcycle_id, as_of)
        if motorcycle is None or model is None:
            return []
        model_id = str(motorcycle.get("model_id", ""))
        policy_group = str(model.get("policy_group", ""))
        rows = [dict(r) for r in self.read_table("maintenance_policies")]
        return [
            row for row in rows
            if ((str(row.get("scope_type")) == "MODEL" and str(row.get("model_id")) == model_id)
                or (str(row.get("scope_type")) == "GROUP" and str(row.get("policy_group")) == policy_group))
        ]

    def _matching(self, table: str, key: str, value: str) -> list[Record]:
        return [dict(row) for row in self.read_table(table) if str(row.get(key)) == str(value)]

    def _at_or_before(
        self,
        rows: Iterable[Mapping[str, Any]],
        as_of: date,
        timestamp_field: str,
        table: str,
        *,
        allow_missing: bool = False,
    ) -> list[Record]:
        cutoff = _coerce_date(as_of)
        accepted: list[tuple[date, Record]] = []
        for raw in rows:
            effective = self._date_value(
                raw.get(timestamp_field), f"{table}.{timestamp_field}", allow_missing=allow_missing
            )
            if effective is not None and effective <= cutoff:
                row = dict(raw)
                row["_effective_at"] = effective.isoformat()
                accepted.append((effective, row))
        accepted.sort(key=lambda item: item[0])
        return [row for _, row in accepted]

    @staticmethod
    def _date_value(value: Any, label: str, *, allow_missing: bool = False) -> date | None:
        if value is None or value == "" or pd.isna(value):
            if allow_missing:
                return None
            raise SourceContractError(f"{label} is required for point-in-time filtering")
        try:
            return pd.Timestamp(value).date()
        except (TypeError, ValueError, OverflowError) as exc:
            raise SourceContractError(f"{label} is not a valid timestamp: {value!r}") from exc

    @staticmethod
    def _one_or_none(rows: Sequence[Mapping[str, Any]], key: str, value: str) -> Record | None:
        if len(rows) > 1:
            raise SourceContractError(f"expected one {key}={value!r}, found {len(rows)}")
        return dict(rows[0]) if rows else None


def _coerce_date(value: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise SourceContractError(f"as_of must be a date, got {value!r}")
