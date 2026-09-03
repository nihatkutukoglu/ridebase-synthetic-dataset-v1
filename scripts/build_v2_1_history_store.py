"""Build compact, indexed SQLite serving store from RideBase V1.4 source tables.

This offline build utility produces:
- v2_1_history_serving.sqlite (~66 MB)
- v2_1_history_store_manifest.json

Only columns required by the frozen 54-feature contract are included.
Indexes are built for point-in-time lookup by motorcycle_id, dates, and IDs.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = REPO_ROOT / "ridebase_v1_4" / "source_tables"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "ridebase-ml" / "derived_outputs" / "v2_1_v1_4"
FEATURE_LIST_PATH = REPO_ROOT / "ridebase-ml" / "models" / "v2_1_v1_4" / "feature_list.json"

TABLE_SCHEMAS: dict[str, dict[str, str]] = {
    "motorcycles": {
        "motorcycle_id": "TEXT",
        "customer_id": "TEXT",
        "workshop_id": "TEXT",
        "model_id": "TEXT",
        "brand": "TEXT",
        "category": "TEXT",
        "powertrain_type": "TEXT",
        "first_registration_date": "TEXT",
        "ownership_start_date": "TEXT",
        "initial_mileage_km": "REAL",
        "observation_start_date": "TEXT",
    },
    "customers": {
        "customer_id": "TEXT",
        "customer_type": "TEXT",
        "first_seen_date": "TEXT",
        "is_fleet_customer": "INTEGER",
    },
    "services": {
        "service_id": "TEXT",
        "motorcycle_id": "TEXT",
        "service_type_code": "TEXT",
        "service_delay_days": "REAL",
        "arrival_mode": "TEXT",
        "received_at": "TEXT",
        "odometer_km": "REAL",
        "status": "TEXT",
        "grand_total": "REAL",
        "is_breakdown": "INTEGER",
        "is_warranty": "INTEGER",
    },
    "mileage_timeline_monthly": {
        "timeline_id": "TEXT",
        "motorcycle_id": "TEXT",
        "period_end_date": "TEXT",
        "closing_odometer_km": "REAL",
        "km_added": "REAL",
    },
    "service_tasks": {
        "service_task_id": "TEXT",
        "service_id": "TEXT",
        "motorcycle_id": "TEXT",
        "task_code": "TEXT",
        "status": "TEXT",
        "completed": "REAL",
        "started_at": "TEXT",
        "completed_at": "TEXT",
    },
    "service_parts": {
        "service_part_id": "TEXT",
        "service_id": "TEXT",
        "service_task_id": "TEXT",
        "motorcycle_id": "TEXT",
    },
    "appointments": {
        "appointment_id": "TEXT",
        "motorcycle_id": "TEXT",
        "created_at": "TEXT",
    },
    "usage_profiles": {
        "usage_profile_id": "TEXT",
        "motorcycle_id": "TEXT",
        "usage_type": "TEXT",
        "annual_km_baseline": "REAL",
        "riding_intensity": "TEXT",
        "climate_zone": "TEXT",
        "storage_condition": "TEXT",
        "profile_start_date": "TEXT",
        "profile_end_date": "TEXT",
    },
    "workshops": {
        "workshop_id": "TEXT",
        "region": "TEXT",
        "price_level": "TEXT",
        "service_bay_count": "INTEGER",
        "appointment_rate": "REAL",
        "avg_parts_lead_days": "REAL",
        "customer_volume_index": "REAL",
    },
    "ridebase_motorcycle_models_v1": {
        "model_id": "TEXT",
        "brand": "TEXT",
        "category": "TEXT",
        "powertrain_type": "TEXT",
        "policy_group": "TEXT",
    },
    "maintenance_policies": {
        "policy_id": "TEXT",
        "scope_type": "TEXT",
        "model_id": "TEXT",
        "policy_group": "TEXT",
        "task_code": "TEXT",
        "policy_kind": "TEXT",
        "initial_trigger_km": "REAL",
        "recurring_km": "REAL",
        "initial_trigger_months": "REAL",
        "recurring_months": "REAL",
        "trigger_mode": "TEXT",
        "precedence": "INTEGER",
        "evidence_level": "TEXT",
        "is_generator_active": "INTEGER",
    },
    "maintenance_tasks": {
        "task_code": "TEXT",
        "task_name": "TEXT",
        "category": "TEXT",
    },
}

TABLE_INDEXES: dict[str, list[str]] = {
    "motorcycles": [
        "CREATE INDEX IF NOT EXISTS idx_motorcycles_id ON motorcycles(motorcycle_id);",
        "CREATE INDEX IF NOT EXISTS idx_motorcycles_obs ON motorcycles(motorcycle_id, observation_start_date);",
    ],
    "customers": [
        "CREATE INDEX IF NOT EXISTS idx_customers_id ON customers(customer_id);",
    ],
    "services": [
        "CREATE INDEX IF NOT EXISTS idx_services_moto_received ON services(motorcycle_id, received_at);",
    ],
    "mileage_timeline_monthly": [
        "CREATE INDEX IF NOT EXISTS idx_mileage_moto_period ON mileage_timeline_monthly(motorcycle_id, period_end_date);",
    ],
    "service_tasks": [
        "CREATE INDEX IF NOT EXISTS idx_service_tasks_moto ON service_tasks(motorcycle_id);",
    ],
    "service_parts": [
        "CREATE INDEX IF NOT EXISTS idx_service_parts_moto ON service_parts(motorcycle_id);",
    ],
    "appointments": [
        "CREATE INDEX IF NOT EXISTS idx_appointments_moto_created ON appointments(motorcycle_id, created_at);",
    ],
    "usage_profiles": [
        "CREATE INDEX IF NOT EXISTS idx_usage_profiles_moto ON usage_profiles(motorcycle_id, profile_start_date);",
    ],
    "workshops": [
        "CREATE INDEX IF NOT EXISTS idx_workshops_id ON workshops(workshop_id);",
    ],
    "ridebase_motorcycle_models_v1": [
        "CREATE INDEX IF NOT EXISTS idx_model_master_id ON ridebase_motorcycle_models_v1(model_id);",
    ],
    "maintenance_policies": [
        "CREATE INDEX IF NOT EXISTS idx_policies_lookup ON maintenance_policies(scope_type, model_id, policy_group);",
    ],
}


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _coerce(val: str, col_type: str) -> Any:
    if val is None or val == "":
        return None
    if "INTEGER" in col_type:
        try:
            return int(round(float(val)))
        except (ValueError, TypeError):
            return None
    if "REAL" in col_type:
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    return val


def build_store(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = output_dir / "v2_1_history_serving.sqlite"
    manifest_path = output_dir / "v2_1_history_store_manifest.json"

    if sqlite_path.exists():
        sqlite_path.unlink()

    conn = sqlite3.connect(sqlite_path)
    conn.execute("PRAGMA journal_mode = OFF;")
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA page_size = 4096;")
    conn.execute("PRAGMA cache_size = 10000;")

    cursor = conn.cursor()

    row_counts: dict[str, int] = {}
    source_hashes: dict[str, str] = {}
    table_semantic_hashes: dict[str, str] = {}

    for table_name, schema in TABLE_SCHEMAS.items():
        csv_file = source_dir / f"{table_name}.csv"
        if not csv_file.exists():
            raise FileNotFoundError(f"Missing source CSV: {csv_file}")

        source_hashes[f"{table_name}.csv"] = _file_sha256(csv_file)

        # Create table
        cols_def = ", ".join(f"{col} {col_type}" for col, col_type in schema.items())
        cursor.execute(f"CREATE TABLE {table_name} ({cols_def});")

        # Load CSV and populate
        cols = list(schema.keys())
        placeholders = ", ".join("?" for _ in cols)
        insert_sql = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders});"

        count = 0
        semantic_hasher = hashlib.sha256()

        with csv_file.open(mode="r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            batch = []
            for row in reader:
                record = tuple(_coerce(row.get(col, ""), schema[col]) for col in cols)
                batch.append(record)
                # Compute semantic hash of row
                semantic_hasher.update(repr(record).encode("utf-8"))
                count += 1
                if len(batch) >= 10000:
                    cursor.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                cursor.executemany(insert_sql, batch)

        row_counts[table_name] = count
        table_semantic_hashes[table_name] = semantic_hasher.hexdigest()

        # Create targeted indexes for this table
        for idx_sql in TABLE_INDEXES.get(table_name, []):
            cursor.execute(idx_sql)

    conn.commit()
    conn.execute("VACUUM;")
    conn.close()

    try:
        commit_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        commit_hash = "unknown"

    feature_contract_hash = _file_sha256(FEATURE_LIST_PATH) if FEATURE_LIST_PATH.exists() else "unknown"
    sqlite_hash = _file_sha256(sqlite_path)
    sqlite_size_bytes = sqlite_path.stat().st_size

    manifest = {
        "manifest_name": "v2_1_history_store_manifest",
        "source_dataset_version": "1.4.0",
        "build_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "build_commit": commit_hash,
        "sqlite_file": sqlite_path.name,
        "sqlite_sha256": sqlite_hash,
        "sqlite_size_bytes": sqlite_size_bytes,
        "sqlite_size_mb": round(sqlite_size_bytes / (1024 * 1024), 2),
        "row_counts": row_counts,
        "table_semantic_hashes": table_semantic_hashes,
        "source_table_hashes": source_hashes,
        "frozen_54_feature_contract_hash": feature_contract_hash,
        "schema_summary": {t: list(s.keys()) for t, s in TABLE_SCHEMAS.items()},
        "indexes": TABLE_INDEXES,
    }

    manifest_path.write_text(json.dumps(manifest, indent=2))
    return sqlite_path, manifest_path


if __name__ == "__main__":
    t0 = time.perf_counter()
    sq, mf = build_store()
    elapsed = time.perf_counter() - t0
    manifest = json.loads(mf.read_text())
    print(f"Store built successfully in {elapsed:.2f}s!")
    print(f"SQLite Store: {sq} ({manifest['sqlite_size_mb']} MB)")
    print(f"Manifest: {mf}")
    print("Row counts:", manifest["row_counts"])
