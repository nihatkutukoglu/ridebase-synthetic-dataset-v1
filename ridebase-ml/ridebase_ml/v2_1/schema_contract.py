"""Immutable v1.3 source-schema contract capture and validation.

V2.1 is allowed to add derived ML tables only.  This module deliberately reads
the authoritative source CSVs without rewriting them and fails on any ordered
column, inferred dtype, primary-key, or frozen-file change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping

import pandas as pd


KEYS: Mapping[str, Dict[str, Any]] = {
    "appointments.csv": {
        "primary_key": ["appointment_id"],
        "foreign_keys": ["workshop_id", "customer_id", "motorcycle_id", "service_id"],
    },
    "customers.csv": {
        "primary_key": ["customer_id"],
        "foreign_keys": ["workshop_id"],
    },
    "maintenance_policies.csv": {
        "primary_key": ["policy_id"],
        "foreign_keys": ["model_id", "task_code"],
    },
    "maintenance_tasks.csv": {
        "primary_key": ["task_code"],
        "foreign_keys": [],
    },
    "mileage_timeline_monthly.csv": {
        "primary_key": ["timeline_id"],
        "foreign_keys": ["motorcycle_id", "workshop_id"],
    },
    "motorcycles.csv": {
        "primary_key": ["motorcycle_id"],
        "foreign_keys": ["customer_id", "workshop_id", "model_id"],
    },
    "ridebase_motorcycle_models_v1.csv": {
        "primary_key": ["model_id"],
        "foreign_keys": [],
    },
    "service_parts.csv": {
        "primary_key": ["service_part_id"],
        "foreign_keys": ["service_id", "service_task_id", "motorcycle_id", "workshop_id"],
    },
    "service_tasks.csv": {
        "primary_key": ["service_task_id"],
        "foreign_keys": ["service_id", "motorcycle_id", "workshop_id", "policy_id"],
    },
    "services.csv": {
        "primary_key": ["service_id"],
        "foreign_keys": ["workshop_id", "customer_id", "motorcycle_id", "appointment_id"],
    },
    "services_enriched.csv": {
        "primary_key": ["service_id"],
        "foreign_keys": ["workshop_id", "customer_id", "motorcycle_id", "appointment_id"],
    },
    "usage_profiles.csv": {
        "primary_key": ["usage_profile_id"],
        "foreign_keys": ["motorcycle_id", "customer_id", "workshop_id"],
    },
    "workshops.csv": {
        "primary_key": ["workshop_id"],
        "foreign_keys": [],
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _table_contract(path: Path, keys: Mapping[str, Any]) -> Dict[str, Any]:
    frame = pd.read_csv(path, low_memory=False)
    primary_key = list(keys["primary_key"])
    missing_keys = [column for column in primary_key if column not in frame.columns]
    if missing_keys:
        raise ValueError(f"{path.name}: missing primary-key columns {missing_keys}")
    if frame.duplicated(primary_key).any():
        raise ValueError(f"{path.name}: primary key is not unique: {primary_key}")
    return {
        "file": path.name,
        "ordered_columns": list(frame.columns),
        "pandas_dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()},
        "row_count": int(len(frame)),
        "primary_key": primary_key,
        "foreign_key_columns": list(keys["foreign_keys"]),
        "sha256": _sha256(path),
    }


def capture_source_schema_contract(source_dir: Path, output_path: Path) -> Dict[str, Any]:
    """Capture the frozen v1.3 source contract without changing source files."""
    source_dir = Path(source_dir)
    expected_files = set(KEYS)
    actual_files = {path.name for path in source_dir.glob("*.csv")}
    if actual_files != expected_files:
        raise ValueError(
            f"authoritative source table set differs: expected={sorted(expected_files)} "
            f"actual={sorted(actual_files)}"
        )
    contract = {
        "contract_name": "RideBase v1.3 authoritative source schema",
        "dataset_version": "1.3.0",
        "source_schema_version": "1.3.0",
        "source_layer_mutable": False,
        "table_count": len(KEYS),
        "tables": {
            name: _table_contract(source_dir / name, KEYS[name])
            for name in sorted(KEYS)
        },
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n")
    return contract


def assert_source_schema_contract(source_dir: Path, contract_path: Path) -> Dict[str, Any]:
    """Fail if the authoritative v1.3 source tables differ from the contract."""
    expected = json.loads(Path(contract_path).read_text())
    current_tables = {
        name: _table_contract(Path(source_dir) / name, KEYS[name])
        for name in sorted(KEYS)
    }
    if set(current_tables) != set(expected["tables"]):
        raise AssertionError("source table set changed")
    errors = []
    for name, current in current_tables.items():
        baseline = expected["tables"][name]
        for field in ("ordered_columns", "pandas_dtypes", "primary_key", "foreign_key_columns"):
            if current[field] != baseline[field]:
                errors.append(f"{name}: {field} changed")
        if current["sha256"] != baseline["sha256"]:
            errors.append(f"{name}: frozen v1.3 file content changed")
    if errors:
        raise AssertionError("; ".join(errors))
    return {
        "status": "PASS",
        "source_schema_version": expected["source_schema_version"],
        "table_count": len(current_tables),
        "source_columns_changed": False,
        "frozen_source_files_changed": False,
    }


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    source = repo_root / "ridebase_v1_3" / "source_tables"
    contract_file = repo_root / "ridebase-ml" / "config" / "source_schema_contract_v1_3.json"
    if contract_file.exists():
        print(json.dumps(assert_source_schema_contract(source, contract_file), indent=2))
    else:
        captured = capture_source_schema_contract(source, contract_file)
        print(json.dumps({"status": "CAPTURED", "tables": captured["table_count"]}, indent=2))
