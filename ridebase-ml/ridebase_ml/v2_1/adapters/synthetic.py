"""Cached read-only adapter over RideBase Synthetic Dataset V1.4 CSV tables."""

from __future__ import annotations

import json
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from ..schema_contract import KEYS
from .base import Record, RideBaseSourceAdapter, SourceContractError

DEFAULT_SOURCE_DIR = Path(__file__).resolve().parents[4] / "ridebase_v1_4" / "source_tables"
DEFAULT_SCHEMA_CONTRACT = Path(__file__).resolve().parents[3] / "config" / "source_schema_contract_v1_3.json"

# Only source columns used by the frozen contract are held in memory. Tables
# not used by the builder remain lazy and load all columns only if explicitly
# requested through read_table.
FEATURE_COLUMNS_BY_TABLE: dict[str, list[str]] = {
    "motorcycles": [
        "motorcycle_id", "customer_id", "workshop_id", "model_id", "brand", "category",
        "powertrain_type", "first_registration_date", "ownership_start_date",
        "initial_mileage_km", "observation_start_date",
    ],
    "customers": ["customer_id", "customer_type", "first_seen_date", "is_fleet_customer"],
    "services": [
        "service_id", "motorcycle_id", "service_type_code", "service_delay_days",
        "arrival_mode", "received_at", "odometer_km", "status", "grand_total",
        "is_breakdown", "is_warranty",
    ],
    "mileage_timeline_monthly": [
        "timeline_id", "motorcycle_id", "period_end_date", "closing_odometer_km", "km_added",
    ],
    "service_tasks": [
        "service_task_id", "service_id", "motorcycle_id", "task_code", "status", "completed",
        "started_at", "completed_at",
    ],
    "service_parts": ["service_part_id", "service_id", "service_task_id", "motorcycle_id"],
    "appointments": ["appointment_id", "motorcycle_id", "created_at"],
    "usage_profiles": [
        "usage_profile_id", "motorcycle_id", "usage_type", "annual_km_baseline",
        "riding_intensity", "climate_zone", "storage_condition", "profile_start_date",
        "profile_end_date",
    ],
    "workshops": [
        "workshop_id", "region", "price_level", "service_bay_count", "appointment_rate",
        "avg_parts_lead_days", "customer_volume_index",
    ],
    "ridebase_motorcycle_models_v1": [
        "model_id", "brand", "category", "powertrain_type", "policy_group",
    ],
    "maintenance_policies": [
        "policy_id", "scope_type", "model_id", "policy_group", "task_code", "policy_kind",
        "initial_trigger_km", "recurring_km", "initial_trigger_months", "recurring_months",
        "trigger_mode", "precedence", "evidence_level", "is_generator_active",
    ],
}

class SyntheticRideBaseSourceAdapter(RideBaseSourceAdapter):
    """Lazy, process-local cache for the immutable V1.4 source release.

    Each CSV is read at most once into a compact Arrow table. Per-key lookup
    results are cached, so repeated feature builds do not rescan or reread it.
    """

    history_source = "SYNTHETIC_V1_4"

    def __init__(
        self,
        source_dir: str | Path = DEFAULT_SOURCE_DIR,
        schema_contract_path: str | Path = DEFAULT_SCHEMA_CONTRACT,
    ) -> None:
        self.source_dir = Path(source_dir).resolve()
        self.schema_contract_path = Path(schema_contract_path).resolve()
        self._frames: dict[str, pa.Table] = {}
        self._records: dict[str, tuple[Record, ...]] = {}
        self._lookups: dict[tuple[str, str, str], tuple[Record, ...]] = {}
        self._disk_reads: Counter[str] = Counter()
        self._lock = threading.RLock()
        self._contract = self._load_contract()
        expected = {Path(name).stem for name in self._contract["tables"]}
        actual = {path.stem for path in self.source_dir.glob("*.csv")}
        if actual != expected:
            raise SourceContractError(
                f"V1.4 source table set changed: expected={sorted(expected)} actual={sorted(actual)}"
            )

    def read_table(self, table_name: str) -> Sequence[Mapping[str, Any]]:
        self._validate_table_name(table_name)
        with self._lock:
            if table_name not in self._records:
                self._records[table_name] = tuple(self._frame(table_name).to_pylist())
            return [dict(row) for row in self._records[table_name]]

    def _matching(self, table: str, key: str, value: str) -> list[Record]:
        self._validate_table_name(table)
        frame = self._frame(table)
        if key not in frame.column_names:
            raise SourceContractError(f"{table}.{key} is not present in the frozen source schema")
        lookup_key = (table, key, str(value))
        with self._lock:
            if lookup_key not in self._lookups:
                column = frame[key]
                try:
                    mask = pc.equal(column, pa.scalar(str(value), type=column.type))
                except (pa.ArrowInvalid, TypeError) as exc:
                    raise SourceContractError(
                        f"{table}.{key} cannot be matched to {value!r}"
                    ) from exc
                self._lookups[lookup_key] = tuple(frame.filter(mask).to_pylist())
            return [dict(row) for row in self._lookups[lookup_key]]

    def cache_info(self) -> dict[str, Any]:
        """Non-sensitive cache diagnostics used by performance/regression gates."""
        return {
            "history_source": self.history_source,
            "loaded_tables": sorted(self._frames),
            "disk_reads": int(sum(self._disk_reads.values())),
            "disk_reads_by_table": dict(sorted(self._disk_reads.items())),
            "cached_indexes": sorted({f"{table}.{key}" for table, key, _ in self._lookups}),
            "cached_lookup_count": len(self._lookups),
        }

    @property
    def supported_motorcycle_count(self) -> int:
        return int(self._frame("motorcycles").num_rows)

    @property
    def supported_tables(self) -> tuple[str, ...]:
        return tuple(sorted(Path(name).stem for name in self._contract["tables"]))

    def _frame(self, table_name: str) -> pa.Table:
        self._validate_table_name(table_name)
        with self._lock:
            if table_name in self._frames:
                return self._frames[table_name]
            path = self.source_dir / f"{table_name}.csv"
            usecols = FEATURE_COLUMNS_BY_TABLE.get(table_name)
            frame = pacsv.read_csv(
                path,
                convert_options=pacsv.ConvertOptions(
                    include_columns=usecols,
                    strings_can_be_null=True,
                ),
            )
            baseline = self._contract["tables"][f"{table_name}.csv"]
            expected_columns = baseline["ordered_columns"] if usecols is None else usecols
            if set(frame.column_names) != set(expected_columns):
                raise SourceContractError(f"{table_name}: required source columns changed")
            primary_key = list(KEYS[f"{table_name}.csv"]["primary_key"])
            if len(primary_key) == 1 and primary_key[0] in frame.column_names:
                distinct = pc.count_distinct(frame[primary_key[0]]).as_py()
                if distinct != frame.num_rows:
                    raise SourceContractError(f"{table_name}: primary key is not unique")
            self._frames[table_name] = frame
            self._disk_reads[table_name] += 1
            return frame

    def _load_contract(self) -> dict[str, Any]:
        try:
            return json.loads(self.schema_contract_path.read_text())
        except (OSError, ValueError) as exc:
            raise SourceContractError(
                f"cannot load frozen source schema contract: {self.schema_contract_path}"
            ) from exc

    def _validate_table_name(self, table_name: str) -> None:
        filename = f"{table_name}.csv"
        if filename not in self._contract.get("tables", {}):
            raise SourceContractError(f"unknown source table {table_name!r}")
