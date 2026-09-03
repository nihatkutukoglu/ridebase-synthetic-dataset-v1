"""Cached read-only adapter over RideBase Synthetic Dataset V1.4 CSV tables."""

from __future__ import annotations

import json
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from ..schema_contract import KEYS
from .base import Record, RideBaseSourceAdapter, SourceContractError

DEFAULT_SOURCE_DIR = Path(__file__).resolve().parents[4] / "ridebase_v1_4" / "source_tables"
DEFAULT_SCHEMA_CONTRACT = Path(__file__).resolve().parents[3] / "config" / "source_schema_contract_v1_3.json"


class SyntheticRideBaseSourceAdapter(RideBaseSourceAdapter):
    """Lazy, process-local cache for the immutable V1.4 source release.

    Each CSV is read at most once per adapter instance. Lookup indexes are also
    cached, so repeated feature builds never rescan a full source table.
    """

    history_source = "SYNTHETIC_V1_4"

    def __init__(
        self,
        source_dir: str | Path = DEFAULT_SOURCE_DIR,
        schema_contract_path: str | Path = DEFAULT_SCHEMA_CONTRACT,
    ) -> None:
        self.source_dir = Path(source_dir).resolve()
        self.schema_contract_path = Path(schema_contract_path).resolve()
        self._frames: dict[str, pd.DataFrame] = {}
        self._records: dict[str, tuple[Record, ...]] = {}
        self._indexes: dict[tuple[str, str], dict[str, tuple[int, ...]]] = {}
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
                self._records[table_name] = tuple(self._frame(table_name).to_dict("records"))
            return [dict(row) for row in self._records[table_name]]

    def _matching(self, table: str, key: str, value: str) -> list[Record]:
        self._validate_table_name(table)
        frame = self._frame(table)
        if key not in frame.columns:
            raise SourceContractError(f"{table}.{key} is not present in the frozen source schema")
        index_key = (table, key)
        with self._lock:
            if index_key not in self._indexes:
                groups: dict[str, list[int]] = {}
                for position, raw in enumerate(frame[key].tolist()):
                    if pd.isna(raw):
                        continue
                    groups.setdefault(str(raw), []).append(position)
                self._indexes[index_key] = {
                    group: tuple(positions) for group, positions in groups.items()
                }
            positions = self._indexes[index_key].get(str(value), ())
        if not positions:
            return []
        return frame.iloc[list(positions)].to_dict("records")

    def cache_info(self) -> dict[str, Any]:
        """Non-sensitive cache diagnostics used by performance/regression gates."""
        return {
            "history_source": self.history_source,
            "loaded_tables": sorted(self._frames),
            "disk_reads": int(sum(self._disk_reads.values())),
            "disk_reads_by_table": dict(sorted(self._disk_reads.items())),
            "cached_indexes": sorted(f"{table}.{key}" for table, key in self._indexes),
        }

    @property
    def supported_motorcycle_count(self) -> int:
        return int(len(self._frame("motorcycles")))

    @property
    def supported_tables(self) -> tuple[str, ...]:
        return tuple(sorted(Path(name).stem for name in self._contract["tables"]))

    def _frame(self, table_name: str) -> pd.DataFrame:
        self._validate_table_name(table_name)
        with self._lock:
            if table_name in self._frames:
                return self._frames[table_name]
            path = self.source_dir / f"{table_name}.csv"
            frame = pd.read_csv(path, low_memory=False)
            baseline = self._contract["tables"][f"{table_name}.csv"]
            if list(frame.columns) != baseline["ordered_columns"]:
                raise SourceContractError(f"{table_name}: ordered source columns changed")
            primary_key = list(KEYS[f"{table_name}.csv"]["primary_key"])
            if frame.duplicated(primary_key).any():
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
