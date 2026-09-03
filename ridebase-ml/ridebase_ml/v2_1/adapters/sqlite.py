"""Memory-safe, read-only adapter over the compact indexed SQLite history store."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from .base import Record, RideBaseSourceAdapter, SourceContractError, _coerce_date

DEFAULT_STORE_PATH = (
    Path(__file__).resolve().parents[3]
    / "derived_outputs"
    / "v2_1_v1_4"
    / "v2_1_history_serving.sqlite"
)


class SyntheticSQLiteSourceAdapter(RideBaseSourceAdapter):
    """Memory-safe, read-only SQLite adapter for V2.1 production history serving.

    Executes indexed point-in-time queries without loading full tables into RAM.
    Thread-safe and process-safe with zero background RAM bloat.
    """

    history_source = "SYNTHETIC_V1_4"
    adapter_type = "SQLITE"

    def __init__(self, store_path: str | Path = DEFAULT_STORE_PATH) -> None:
        self.store_path = Path(store_path).resolve()
        if not self.store_path.exists():
            raise FileNotFoundError(f"SQLite history store not found at {self.store_path}")

        self._local = threading.local()
        # Verify read access and table availability once at init
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            self._available_tables = {row[0] for row in cur.fetchall()}

        manifest_path = self.store_path.with_name("v2_1_history_store_manifest.json")
        self.manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "connection") or self._local.connection is None:
            # Read-only URI mode ensures zero disk writes and allows concurrent reads
            uri = f"file:{self.store_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            self._local.connection = conn
        return self._local.connection

    def close(self) -> None:
        if hasattr(self._local, "connection") and self._local.connection is not None:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None

    def read_table(self, table_name: str) -> Sequence[Mapping[str, Any]]:
        """Backwards-compatible full table read for testing contracts."""
        if table_name not in self._available_tables:
            raise SourceContractError(f"Table {table_name!r} not in SQLite store")
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table_name}")
        return [dict(row) for row in cur.fetchall()]

    def motorcycle_exists(self, motorcycle_id: str) -> bool:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM motorcycles WHERE motorcycle_id = ? LIMIT 1", (str(motorcycle_id),))
        return cur.fetchone() is not None

    def get_motorcycle(self, motorcycle_id: str, as_of: date) -> Record | None:
        cutoff = _coerce_date(as_of).isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM motorcycles WHERE motorcycle_id = ? AND observation_start_date <= ?",
            (str(motorcycle_id), cutoff),
        )
        rows = [dict(r) for r in cur.fetchall()]
        return self._one_or_none(rows, "motorcycle_id", motorcycle_id)

    def get_customer_for_motorcycle(self, motorcycle_id: str, as_of: date) -> Record | None:
        motorcycle = self.get_motorcycle(motorcycle_id, as_of)
        if motorcycle is None or not motorcycle.get("customer_id"):
            return None
        customer_id = str(motorcycle["customer_id"])
        cutoff = _coerce_date(as_of).isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM customers WHERE customer_id = ? AND first_seen_date <= ?",
            (customer_id, cutoff),
        )
        rows = [dict(r) for r in cur.fetchall()]
        return self._one_or_none(rows, "customer_id", customer_id)

    def get_services_before(self, motorcycle_id: str, as_of: date) -> list[Record]:
        cutoff = _coerce_date(as_of)
        cutoff_iso = cutoff.isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        # Filter where date part of received_at <= cutoff
        cur.execute(
            """SELECT * FROM services
               WHERE motorcycle_id = ? AND substr(received_at, 1, 10) <= ?
               ORDER BY received_at ASC, service_id ASC""",
            (str(motorcycle_id), cutoff_iso),
        )
        accepted: list[tuple[date, Record]] = []
        for raw in cur.fetchall():
            row = dict(raw)
            effective = self._date_value(row.get("received_at"), "services.received_at")
            if effective is not None and effective <= cutoff:
                row["_effective_at"] = effective.isoformat()
                accepted.append((effective, row))
        accepted.sort(key=lambda item: item[0])
        return [row for _, row in accepted]

    def get_mileage_before(self, motorcycle_id: str, as_of: date) -> list[Record]:
        cutoff = _coerce_date(as_of)
        cutoff_iso = cutoff.isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM mileage_timeline_monthly
               WHERE motorcycle_id = ? AND substr(period_end_date, 1, 10) <= ?
               ORDER BY period_end_date ASC, timeline_id ASC""",
            (str(motorcycle_id), cutoff_iso),
        )
        accepted: list[tuple[date, Record]] = []
        for raw in cur.fetchall():
            row = dict(raw)
            effective = self._date_value(row.get("period_end_date"), "mileage_timeline_monthly.period_end_date")
            if effective is not None and effective <= cutoff:
                row["_effective_at"] = effective.isoformat()
                accepted.append((effective, row))
        accepted.sort(key=lambda item: item[0])
        return [row for _, row in accepted]

    def get_service_tasks_before(self, motorcycle_id: str, as_of: date) -> list[Record]:
        cutoff = _coerce_date(as_of)
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM service_tasks WHERE motorcycle_id = ? ORDER BY service_task_id ASC",
            (str(motorcycle_id),),
        )
        accepted: list[tuple[date, Record]] = []
        for raw in cur.fetchall():
            row = dict(raw)
            field = "completed_at" if row.get("completed_at") not in (None, "") and not pd.isna(row.get("completed_at")) else "started_at"
            effective = self._date_value(
                row.get(field), f"service_tasks.{field}", allow_missing=True
            )
            if effective is not None and effective <= cutoff:
                row["_effective_at"] = effective.isoformat()
                accepted.append((effective, row))
        accepted.sort(key=lambda item: item[0])
        return [row for _, row in accepted]

    def get_service_parts_before(self, motorcycle_id: str, as_of: date) -> list[Record]:
        services = {
            str(row.get("service_id")): row
            for row in self.get_services_before(motorcycle_id, as_of)
        }
        tasks = {
            str(row.get("service_task_id")): row
            for row in self.get_service_tasks_before(motorcycle_id, as_of)
        }
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM service_parts WHERE motorcycle_id = ? ORDER BY service_part_id ASC",
            (str(motorcycle_id),),
        )
        out: list[Record] = []
        for raw in cur.fetchall():
            row = dict(raw)
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
        cutoff = _coerce_date(as_of)
        cutoff_iso = cutoff.isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM appointments
               WHERE motorcycle_id = ? AND substr(created_at, 1, 10) <= ?
               ORDER BY created_at ASC, appointment_id ASC""",
            (str(motorcycle_id), cutoff_iso),
        )
        accepted: list[tuple[date, Record]] = []
        for raw in cur.fetchall():
            row = dict(raw)
            effective = self._date_value(row.get("created_at"), "appointments.created_at")
            if effective is not None and effective <= cutoff:
                row["_effective_at"] = effective.isoformat()
                accepted.append((effective, row))
        accepted.sort(key=lambda item: item[0])
        return [row for _, row in accepted]

    def get_usage_profile(self, motorcycle_id: str, as_of: date) -> Record | None:
        cutoff = _coerce_date(as_of)
        cutoff_iso = cutoff.isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM usage_profiles
               WHERE motorcycle_id = ? AND profile_start_date <= ?
               ORDER BY profile_start_date ASC""",
            (str(motorcycle_id), cutoff_iso),
        )
        rows = [dict(r) for r in cur.fetchall()]
        active = []
        for row in rows:
            end = self._date_value(row.get("profile_end_date"), "usage_profiles.profile_end_date", allow_missing=True)
            if end is None or end >= cutoff:
                active.append(row)
        if len(active) > 1:
            active.sort(key=lambda r: self._date_value(r.get("profile_start_date"), "usage_profiles.profile_start_date"))
            return dict(active[-1])
        return dict(active[0]) if active else None

    def get_workshop_history(self, motorcycle_id: str, as_of: date) -> list[Record]:
        motorcycle = self.get_motorcycle(motorcycle_id, as_of)
        if motorcycle is None or not motorcycle.get("workshop_id"):
            return []
        workshop_id = str(motorcycle["workshop_id"])
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM workshops WHERE workshop_id = ?", (workshop_id,))
        return [dict(r) for r in cur.fetchall()]

    def get_model_master(self, motorcycle_id: str, as_of: date) -> Record | None:
        motorcycle = self.get_motorcycle(motorcycle_id, as_of)
        if motorcycle is None or not motorcycle.get("model_id"):
            return None
        model_id = str(motorcycle["model_id"])
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM ridebase_motorcycle_models_v1 WHERE model_id = ?", (model_id,))
        rows = [dict(r) for r in cur.fetchall()]
        return self._one_or_none(rows, "model_id", model_id)

    def get_maintenance_policy(self, motorcycle_id: str, as_of: date) -> list[Record]:
        motorcycle = self.get_motorcycle(motorcycle_id, as_of)
        model = self.get_model_master(motorcycle_id, as_of)
        if motorcycle is None or model is None:
            return []
        model_id = str(motorcycle.get("model_id", ""))
        policy_group = str(model.get("policy_group", ""))
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM maintenance_policies
               WHERE (scope_type = 'MODEL' AND model_id = ?)
                  OR (scope_type = 'GROUP' AND policy_group = ?)
               ORDER BY precedence ASC, policy_id ASC""",
            (model_id, policy_group),
        )
        return [dict(r) for r in cur.fetchall()]

    def cache_info(self) -> dict[str, Any]:
        return {
            "history_source": self.history_source,
            "adapter_type": self.adapter_type,
            "store_path": str(self.store_path),
            "store_size_bytes": self.store_path.stat().st_size if self.store_path.exists() else 0,
            "manifest_version": self.manifest.get("source_dataset_version"),
            "disk_reads": 0,
            "disk_reads_by_table": {},
        }

    @property
    def supported_motorcycle_count(self) -> int:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM motorcycles")
        row = cur.fetchone()
        return int(row[0]) if row else 0

    @property
    def supported_tables(self) -> tuple[str, ...]:
        return tuple(sorted(self._available_tables))
