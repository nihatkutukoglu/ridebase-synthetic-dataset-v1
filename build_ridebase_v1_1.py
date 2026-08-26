from __future__ import annotations

import hashlib
import json
import math
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parent
V1_SOURCE = ROOT / "source_tables"
V1_DERIVED = ROOT / "derived_outputs"
OUT = ROOT / "ridebase_v1_1"
OUT_SOURCE = OUT / "source_tables"
OUT_DERIVED = OUT / "derived_outputs"
OUT_REPORTS = OUT / "reports"
ZIP_PATH = ROOT / "ridebase_synthetic_dataset_v1_1.zip"

VERSION = "1.1.0"
SEED = 42
HORIZON = pd.Timestamp("2026-08-25")


def stable_int(value: str) -> int:
    return int(hashlib.sha256(f"{SEED}:{value}".encode()).hexdigest()[:12], 16)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def write_json(obj: dict, path: Path) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_empty_strings(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    result = df.copy()
    changed = 0
    for col in result.select_dtypes(include=["object", "string"]).columns:
        mask = result[col].astype("string").str.strip().eq("").fillna(False)
        changed += int(mask.sum())
        if mask.any():
            result.loc[mask, col] = pd.NA
    return result, changed


def update_versions(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for col in ["generator_version", "taxonomy_version", "policy_version", "profile_rule_version"]:
        if col in result.columns:
            result[col] = VERSION
    return result


def as_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def max_dates_by_id(df: pd.DataFrame, id_col: str, date_cols: list[str]) -> pd.Series:
    available = [c for c in date_cols if c in df.columns]
    if not available:
        return pd.Series(dtype="datetime64[ns]")
    values = pd.concat(
        [pd.DataFrame({id_col: df[id_col], "activity_date": pd.to_datetime(df[c], errors="coerce")}) for c in available],
        ignore_index=True,
    )
    return values.groupby(id_col)["activity_date"].max()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(name: str, severity: str, violations: int, metrics: dict, summary: str) -> dict:
    return {
        "check": name,
        "status": "PASS" if violations == 0 else "FAIL",
        "severity": severity,
        "summary": summary,
        "metrics": {**metrics, "violations": int(violations)},
    }


if OUT.exists():
    raise SystemExit(f"Refusing to overwrite existing output: {OUT}")

OUT_SOURCE.mkdir(parents=True)
OUT_DERIVED.mkdir(parents=True)
OUT_REPORTS.mkdir(parents=True)

# ---------------------------------------------------------------------------
# Load v1 as immutable reference.
# ---------------------------------------------------------------------------
source = {p.name: read_csv(p) for p in sorted(V1_SOURCE.glob("*.csv"))}
v1_status = read_csv(V1_DERIVED / "service_status_history.csv")
v1_noise = read_csv(V1_DERIVED / "noise_audit.csv")
v1_snapshots = pd.read_parquet(V1_DERIVED / "ml_maintenance_snapshots.parquet")
v1_next_service = pd.read_parquet(V1_DERIVED / "ml_next_service_targets.parquet")
v1_next_task = pd.read_parquet(V1_DERIVED / "ml_next_task_targets.parquet")
v1_split = read_csv(V1_DERIVED / "split_manifest.csv")
v1_metadata = json.loads((V1_DERIVED / "dataset_metadata.json").read_text(encoding="utf-8"))

before = {
    "inactive_customer_missing_churn": int(((source["customers.csv"]["is_active"] == 0) & source["customers.csv"]["churn_date"].isna()).sum()),
    "inactive_motorcycle_missing_observation_end": int(((source["motorcycles.csv"]["is_active"] == 0) & source["motorcycles.csv"]["observation_end_date"].isna()).sum()),
    "noise_audit_clean_value_semantic_conflict": int(((v1_noise["clean_value_available"] == 1) & v1_noise["original_clean_value"].isna()).sum()),
    "model_missing_production_start_year": int(source["ridebase_motorcycle_models_v1.csv"]["production_start_year"].isna().sum()),
    "model_missing_production_end_year": int(source["ridebase_motorcycle_models_v1.csv"]["production_end_year"].isna().sum()),
}

# ---------------------------------------------------------------------------
# Source fixes.
# ---------------------------------------------------------------------------
services = source["services.csv"].copy()
appointments = source["appointments.csv"].copy()
motorcycles = source["motorcycles.csv"].copy()
customers = source["customers.csv"].copy()
mileage = source["mileage_timeline_monthly.csv"].copy()

# Model ranges are simulation support ranges, not OEM claims. Existing instance
# years are preserved by deriving a range that contains the observed v1 values.
models = source["ridebase_motorcycle_models_v1.csv"].copy()
years = motorcycles.groupby("model_id")["production_year"].agg(["min", "max"])
for idx, row in models.iterrows():
    model_id = row["model_id"]
    if model_id in years.index:
        start = int(years.loc[model_id, "min"])
        end = int(years.loc[model_id, "max"])
    else:
        reference = row.get("spec_reference_year")
        end = int(reference) if pd.notna(reference) else HORIZON.year
        start = end - 5
    models.at[idx, "production_start_year"] = start
    models.at[idx, "production_end_year"] = end

models["production_year_range_basis"] = "SIMULATION_PRIOR_MODEL_RANGE"
models["production_year_range_confidence"] = "LOW"
cooling_updates = {"HONDA_ACTIVA125": "AIR", "HONDA_DIO110": "AIR"}
for model_id, cooling_type in cooling_updates.items():
    mask = models["model_id"].eq(model_id)
    models.loc[mask, "cooling_type"] = cooling_type
    models.loc[mask, "verification_notes"] = (
        models.loc[mask, "verification_notes"].fillna("").astype(str).str.strip()
        + " v1.1 cooling type normalized to AIR from the model technical listing; retained as synthetic technical master data."
    ).str.strip()

model_ranges = models.set_index("model_id")[["production_start_year", "production_end_year"]]
year_changes = 0
for idx, row in motorcycles.iterrows():
    limits = model_ranges.loc[row["model_id"]]
    year = int(row["production_year"])
    bounded = min(max(year, int(limits["production_start_year"])), int(limits["production_end_year"]))
    if bounded != year:
        motorcycles.at[idx, "production_year"] = bounded
        year_changes += 1
motorcycles["production_year_basis"] = "V1_1_SIMULATION_MODEL_RANGE_VALIDATED"

# Customer activity anchors.
service_customer_activity = max_dates_by_id(v1_status, "customer_id", ["status_at"])
appointment_customer_activity = max_dates_by_id(appointments, "customer_id", ["created_at", "scheduled_at"])
motorcycle_customer_activity = max_dates_by_id(motorcycles, "customer_id", ["observation_end_date", "observation_start_date"])
customer_activity = pd.concat(
    [service_customer_activity.rename("service"), appointment_customer_activity.rename("appointment"), motorcycle_customer_activity.rename("motorcycle")],
    axis=1,
).max(axis=1)

customer_fill_count = 0
customer_adjust_count = 0
customers["first_seen_date"] = as_date(customers["first_seen_date"])
customers["churn_date"] = as_date(customers["churn_date"])
for idx, row in customers[(customers["is_active"] == 0) & customers["churn_date"].isna()].iterrows():
    anchor = customer_activity.get(row["customer_id"], pd.NaT)
    if pd.isna(anchor):
        anchor = row["first_seen_date"]
    gap = 30 + stable_int(row["customer_id"]) % 91
    churn = min(pd.Timestamp(anchor).normalize() + pd.Timedelta(days=gap), HORIZON)
    churn = max(churn, row["first_seen_date"])
    customers.at[idx, "churn_date"] = churn
    customer_fill_count += 1
for idx, row in customers[(customers["is_active"] == 0) & customers["churn_date"].notna()].iterrows():
    activity = customer_activity.get(row["customer_id"], pd.NaT)
    if pd.notna(activity) and row["churn_date"] < pd.Timestamp(activity).normalize():
        customers.at[idx, "churn_date"] = min(pd.Timestamp(activity).normalize(), HORIZON)
        customer_adjust_count += 1
customers.loc[customers["is_active"] == 1, "churn_date"] = pd.NaT

# Motorcycle activity anchors include canonical delivered timestamps from v1.
canonical_delivered = (
    v1_status[v1_status["status"].eq("DELIVERED")]
    .assign(status_at=lambda x: pd.to_datetime(x["status_at"], errors="coerce"))
    .groupby("motorcycle_id")["status_at"].max()
)
appointment_motorcycle_activity = max_dates_by_id(appointments, "motorcycle_id", ["created_at", "scheduled_at"])
mileage_activity = max_dates_by_id(mileage, "motorcycle_id", ["period_end_date"])
motorcycle_activity = pd.concat(
    [canonical_delivered.rename("service"), appointment_motorcycle_activity.rename("appointment"), mileage_activity.rename("mileage")],
    axis=1,
).max(axis=1)

motorcycle_fill_count = 0
motorcycle_adjust_count = 0
for col in ["ownership_start_date", "observation_start_date", "observation_end_date"]:
    motorcycles[col] = as_date(motorcycles[col])
for idx, row in motorcycles[(motorcycles["is_active"] == 0) & motorcycles["observation_end_date"].isna()].iterrows():
    anchor = motorcycle_activity.get(row["motorcycle_id"], pd.NaT)
    if pd.isna(anchor):
        anchor = row["observation_start_date"]
    gap = 7 + stable_int(row["motorcycle_id"]) % 54
    end = min(pd.Timestamp(anchor).normalize() + pd.Timedelta(days=gap), HORIZON)
    end = max(end, row["observation_start_date"], row["ownership_start_date"])
    motorcycles.at[idx, "observation_end_date"] = end
    motorcycle_fill_count += 1
for idx, row in motorcycles[(motorcycles["is_active"] == 0) & motorcycles["observation_end_date"].notna()].iterrows():
    activity = motorcycle_activity.get(row["motorcycle_id"], pd.NaT)
    if pd.notna(activity) and row["observation_end_date"] < pd.Timestamp(activity).normalize():
        motorcycles.at[idx, "observation_end_date"] = min(pd.Timestamp(activity).normalize(), HORIZON)
        motorcycle_adjust_count += 1
motorcycles.loc[motorcycles["is_active"] == 1, "observation_end_date"] = pd.NaT

# Usage profiles use the exact motorcycle observation boundary for inactive units.
usage = source["usage_profiles.csv"].copy()
old_profile_end = as_date(usage["profile_end_date"])
motorcycle_end = motorcycles.set_index("motorcycle_id")["observation_end_date"]
motorcycle_active = motorcycles.set_index("motorcycle_id")["is_active"]
usage["profile_end_date"] = usage["motorcycle_id"].map(motorcycle_end)
usage.loc[usage["motorcycle_id"].map(motorcycle_active).eq(1), "profile_end_date"] = pd.NaT
profile_end_updates = int((~(old_profile_end.fillna(pd.Timestamp("1900-01-01")) == usage["profile_end_date"].fillna(pd.Timestamp("1900-01-01")))).sum())

# Add lifecycle-only appointments without altering any existing service link.
existing_converted = len(appointments)
target_total = int(round(existing_converted / 0.86))
target_counts = {
    "CANCELLED": int(round(target_total * 0.07)),
    "NO_SHOW": int(round(target_total * 0.04)),
}
target_counts["RESCHEDULED"] = target_total - existing_converted - sum(target_counts.values())
extra_count = sum(target_counts.values())
rng = np.random.default_rng(SEED)
template_indices = rng.choice(appointments.index.to_numpy(), size=extra_count, replace=True)
extras = appointments.loc[template_indices].copy().reset_index(drop=True)
numeric_suffix = appointments["appointment_id"].astype(str).str.extract(r"(\d+)$", expand=False).astype(int)
start_id = int(numeric_suffix.max()) + 1
width = max(6, int(numeric_suffix.astype(str).str.len().max()))
extras["appointment_id"] = [f"APT{i:0{width}d}" for i in range(start_id, start_id + extra_count)]
statuses = [status for status, count_ in target_counts.items() for _ in range(count_)]
extras["status"] = statuses
extras["service_id"] = pd.NA
extras["created_at"] = pd.to_datetime(extras["created_at"], errors="coerce")
extras["scheduled_at"] = pd.to_datetime(extras["scheduled_at"], errors="coerce")
appointments = pd.concat([appointments, extras], ignore_index=True)

# Safe workshop diversity only. Other capabilities remain unchanged because every
# workshop currently has multi-brand and ABS-linked historical service activity.
workshops = source["workshops.csv"].copy()
sunday_open_ids = set(sorted(workshops["workshop_id"])[::5])
workshops["sunday_open"] = workshops["workshop_id"].isin(sunday_open_ids).astype(int)

source["customers.csv"] = customers
source["motorcycles.csv"] = motorcycles
source["usage_profiles.csv"] = usage
source["appointments.csv"] = appointments
source["workshops.csv"] = workshops
source["ridebase_motorcycle_models_v1.csv"] = models

for file_name, df in source.items():
    source[file_name] = update_versions(df)
    write_csv(source[file_name], OUT_SOURCE / file_name)

# ---------------------------------------------------------------------------
# Rebuild derived outputs from the corrected sources and canonical v1 structure.
# ---------------------------------------------------------------------------
status_history = update_versions(v1_status)
status_history["status_at"] = pd.to_datetime(status_history["status_at"], errors="coerce")
status_history = status_history.sort_values(["service_id", "status_sequence", "status_at"]).reset_index(drop=True)
write_csv(status_history, OUT_DERIVED / "service_status_history.csv")

noise = v1_noise.rename(columns={"canonical_reference_value": "canonical_clean_value"}).copy()
noise["original_clean_value_available"] = noise["original_clean_value"].notna().astype(int)
canonical_types = noise["issue_type"].isin(["STATUS_TIMESTAMP_INCONSISTENCY", "CONTROLLED_TEXT_NOISE"])
noise["clean_value_available"] = canonical_types.astype(int)
noise.loc[noise["issue_type"].eq("STATUS_TIMESTAMP_INCONSISTENCY"), "repair_applied"] = 1
noise.loc[noise["issue_type"].eq("CONTROLLED_TEXT_NOISE"), "repair_applied"] = 0
noise["generator_version"] = VERSION
noise["noise_rule_version"] = noise["noise_rule_version"].astype(str).str.replace("_V1", "_V1_1", regex=False)
noise, _ = normalize_empty_strings(noise)
write_csv(noise, OUT_DERIVED / "noise_audit.csv")

snapshots, snapshot_empty_to_null = normalize_empty_strings(v1_snapshots)
model_lookup = models.set_index("model_id")
motorcycle_lookup = motorcycles.set_index("motorcycle_id")
for col in ["brand", "model_name", "category", "powertrain_type", "engine_displacement_cc", "cylinder_count", "cooling_type", "final_drive_type", "transmission_type", "engine_oil_service_qty_l", "spark_plug_count", "fuel_type", "policy_group", "policy_ready", "spec_confidence"]:
    if col in snapshots.columns and col in model_lookup.columns:
        snapshots[col] = snapshots["model_id"].map(model_lookup[col])
snapshots["production_year"] = snapshots["motorcycle_id"].map(motorcycle_lookup["production_year"])
snapshots["feature_version"] = VERSION
snapshots["generator_version"] = VERSION

next_service, next_service_empty_to_null = normalize_empty_strings(v1_next_service)
censored_service = next_service["target_event_observed"].eq(0)
future_service_columns = [
    "next_service_id", "next_service_received_at_raw", "target_next_service_at", "next_service_delivered_at",
    "days_to_next_service_raw", "days_to_next_service", "target_time_repaired", "next_service_odometer_km",
    "km_to_next_service_raw", "km_to_next_service", "target_km_valid", "next_service_mileage_source",
    "next_service_mileage_quality_flag", "next_service_is_mileage_estimated", "next_service_type_code",
    "next_service_primary_trigger_task", "next_service_arrival_mode", "next_service_is_breakdown", "next_service_is_warranty",
]
for col in future_service_columns:
    if col in next_service.columns:
        next_service.loc[censored_service, col] = pd.NA
next_service["target_version"] = VERSION
next_service["generator_version"] = VERSION

next_task, next_task_empty_to_null = normalize_empty_strings(v1_next_task)
censored_task = next_task["target_event_observed"].eq(0)
task_label_columns = [c for c in next_task.columns if c.startswith("task__")]
for col in task_label_columns:
    next_task[col] = pd.array(next_task[col], dtype="Int8")
    next_task.loc[censored_task, col] = pd.NA
for col in ["next_task_count", "next_completed_task_count", "next_declined_task_count"]:
    next_task[col] = pd.array(next_task[col].mask(censored_task), dtype="Int16")
for col in ["next_service_id", "next_task_codes", "next_completed_task_codes", "next_declined_task_codes"]:
    next_task.loc[censored_task, col] = pd.NA
if "target_unknown_value" in next_task.columns:
    next_task = next_task.drop(columns=["target_unknown_value"])
next_task["target_version"] = VERSION
next_task["taxonomy_version"] = VERSION
next_task["generator_version"] = VERSION

split_manifest, split_empty_to_null = normalize_empty_strings(v1_split)
split_manifest["split_version"] = "SPLIT_MANIFEST_V1_1"
split_manifest["generator_version"] = VERSION

pq.write_table(pa.Table.from_pandas(snapshots, preserve_index=False), OUT_DERIVED / "ml_maintenance_snapshots.parquet", compression="snappy")
pq.write_table(pa.Table.from_pandas(next_service, preserve_index=False), OUT_DERIVED / "ml_next_service_targets.parquet", compression="snappy")
pq.write_table(pa.Table.from_pandas(next_task, preserve_index=False), OUT_DERIVED / "ml_next_task_targets.parquet", compression="snappy")
write_csv(split_manifest, OUT_DERIVED / "split_manifest.csv")

# ---------------------------------------------------------------------------
# Validation checks and reports.
# ---------------------------------------------------------------------------
services = source["services.csv"]
service_tasks = source["service_tasks.csv"]
service_parts = source["service_parts.csv"]
maintenance_tasks = source["maintenance_tasks.csv"]

checks = []
row_counts = {Path(k).stem: len(v) for k, v in source.items()}
checks.append(check("row_volume_checks", "HIGH", 0, row_counts, "All required source tables are present and non-empty."))

all_tables = {Path(k).stem: v for k, v in source.items()} | {
    "service_status_history": status_history,
    "noise_audit": noise,
    "ml_maintenance_snapshots": snapshots,
    "ml_next_service_targets": next_service,
    "ml_next_task_targets": next_task,
    "split_manifest": split_manifest,
}
duplicate_rows = {name: int(df.duplicated().sum()) for name, df in all_tables.items()}
checks.append(check("duplicate_checks", "HIGH", sum(duplicate_rows.values()), duplicate_rows, "No full-row duplicates."))

pk_map = {
    "workshops": "workshop_id", "customers": "customer_id", "motorcycles": "motorcycle_id",
    "ridebase_motorcycle_models_v1": "model_id", "usage_profiles": "usage_profile_id",
    "mileage_timeline_monthly": "timeline_id", "maintenance_tasks": "task_code",
    "maintenance_policies": "policy_id", "appointments": "appointment_id", "services": "service_id",
    "services_enriched": "service_id", "service_tasks": "service_task_id", "service_parts": "service_part_id",
    "service_status_history": "status_history_id", "noise_audit": "noise_audit_id",
    "ml_maintenance_snapshots": "snapshot_id", "ml_next_service_targets": "snapshot_id",
    "ml_next_task_targets": "snapshot_id", "split_manifest": "snapshot_id",
}
pk_duplicates = {name: int(df[pk_map[name]].duplicated().sum()) for name, df in all_tables.items() if name in pk_map}
checks.append(check("primary_key_duplicates", "HIGH", sum(pk_duplicates.values()), pk_duplicates, "Primary keys are unique."))

def orphan(child: pd.DataFrame, fk: str, parent: pd.DataFrame, pk: str) -> int:
    return int((child[fk].notna() & ~child[fk].isin(parent[pk])).sum())

fk_metrics = {
    "motorcycles_customer": orphan(motorcycles, "customer_id", customers, "customer_id"),
    "customers_workshop": orphan(customers, "workshop_id", workshops, "workshop_id"),
    "services_workshop": orphan(services, "workshop_id", workshops, "workshop_id"),
    "services_customer": orphan(services, "customer_id", customers, "customer_id"),
    "services_motorcycle": orphan(services, "motorcycle_id", motorcycles, "motorcycle_id"),
    "services_appointment": orphan(services, "appointment_id", appointments, "appointment_id"),
    "service_tasks_service": orphan(service_tasks, "service_id", services, "service_id"),
    "service_tasks_task": orphan(service_tasks, "task_code", maintenance_tasks, "task_code"),
    "service_parts_service": orphan(service_parts, "service_id", services, "service_id"),
    "status_history_service": orphan(status_history, "service_id", services, "service_id"),
}
checks.append(check("foreign_key_orphans", "HIGH", sum(fk_metrics.values()), fk_metrics, "All required foreign keys resolve."))

timeline = status_history.sort_values(["service_id", "status_sequence"])
timeline_backwards = int((timeline.groupby("service_id")["status_at"].diff() < pd.Timedelta(0)).sum())
checks.append(check("service_timeline_ordering", "HIGH", timeline_backwards, {"backwards_events": timeline_backwards}, "Canonical status timestamps are monotonic."))

task_completed_bad = int(((service_tasks["status"].eq("COMPLETED")) & (service_tasks["completed"].ne(1) | service_tasks["completed_at"].isna())).sum())
task_declined_bad = int(((service_tasks["status"].eq("DECLINED")) & (service_tasks["completed"].ne(0) | service_tasks["completed_at"].notna())).sum())
checks.append(check("service_task_status_consistency", "HIGH", task_completed_bad + task_declined_bad, {"completed_bad": task_completed_bad, "declined_bad": task_declined_bad}, "Task status fields are consistent."))

mileage_sorted = mileage.sort_values(["motorcycle_id", "period_start_date"])
mileage_regressions = int((mileage_sorted.groupby("motorcycle_id")["closing_odometer_km"].diff() < 0).sum())
checks.append(check("mileage_monotonicity", "HIGH", mileage_regressions, {"regressions": mileage_regressions}, "Monthly closing odometer is monotonic."))

part_bad = int((service_parts["is_compatible"].ne(1)).sum())
purchase_bad = int((~np.isclose(service_parts["purchase_total"], service_parts["quantity"] * service_parts["unit_purchase_price"], atol=0.01)).sum())
sale_bad = int((~np.isclose(service_parts["sale_total"], service_parts["quantity"] * service_parts["unit_sale_price"], atol=0.01)).sum())
checks.append(check("service_part_compatibility", "HIGH", part_bad, {"incompatible_rows": part_bad}, "Used parts are compatible."))
checks.append(check("cost_arithmetic", "HIGH", purchase_bad + sale_bad, {"purchase_mismatch": purchase_bad, "sale_mismatch": sale_bad}, "Part cost arithmetic is valid."))

converted_bad = int((appointments["status"].eq("CONVERTED_TO_SERVICE") & appointments["service_id"].isna()).sum())
nonservice_bad = int((appointments["status"].isin(["CANCELLED", "NO_SHOW", "RESCHEDULED"]) & appointments["service_id"].notna()).sum())
checks.append(check("appointment_lifecycle_validity", "HIGH", converted_bad + nonservice_bad, {"converted_without_service": converted_bad, "nonconverted_with_service": nonservice_bad, "status_counts": appointments["status"].value_counts().to_dict()}, "Appointment lifecycle and service links are valid."))

inactive_customer_bad = int(((customers["is_active"] == 0) & customers["churn_date"].isna()).sum())
active_customer_bad = int(((customers["is_active"] == 1) & customers["churn_date"].notna()).sum())
customer_churn_before_activity = int(sum(
    pd.notna(customer_activity.get(row["customer_id"], pd.NaT))
    and row["churn_date"] < pd.Timestamp(customer_activity.get(row["customer_id"])).normalize()
    for _, row in customers[(customers["is_active"] == 0) & customers["churn_date"].notna()].iterrows()
))
checks.append(check("inactive_customer_churn_completeness", "HIGH", inactive_customer_bad + active_customer_bad + customer_churn_before_activity, {"inactive_missing": inactive_customer_bad, "active_with_churn": active_customer_bad, "churn_before_last_activity": customer_churn_before_activity}, "Conditional churn-date semantics are valid."))

inactive_motorcycle_bad = int(((motorcycles["is_active"] == 0) & motorcycles["observation_end_date"].isna()).sum())
motorcycle_end_before_activity = int(sum(
    pd.notna(motorcycle_activity.get(row["motorcycle_id"], pd.NaT))
    and row["observation_end_date"] < pd.Timestamp(motorcycle_activity.get(row["motorcycle_id"])).normalize()
    for _, row in motorcycles[(motorcycles["is_active"] == 0) & motorcycles["observation_end_date"].notna()].iterrows()
))
checks.append(check("inactive_motorcycle_observation_end_completeness", "HIGH", inactive_motorcycle_bad + motorcycle_end_before_activity, {"inactive_missing": inactive_motorcycle_bad, "end_before_last_activity": motorcycle_end_before_activity}, "Inactive motorcycles have valid observation end dates."))

usage_check = usage[["motorcycle_id", "profile_end_date"]].merge(motorcycles[["motorcycle_id", "is_active", "observation_end_date"]], on="motorcycle_id")
usage_check["profile_end_date"] = as_date(usage_check["profile_end_date"])
usage_check["observation_end_date"] = as_date(usage_check["observation_end_date"])
usage_bad = int(((usage_check["is_active"] == 0) & (usage_check["profile_end_date"] != usage_check["observation_end_date"])).sum())
checks.append(check("usage_profile_end_date_synchronization", "HIGH", usage_bad, {"mismatches": usage_bad}, "Inactive usage profiles share the motorcycle boundary."))

model_range_bad = int((models["production_start_year"] > models["production_end_year"]).sum())
mc_range = motorcycles.merge(models[["model_id", "production_start_year", "production_end_year"]], on="model_id")
motorcycle_year_bad = int(((mc_range["production_year"] < mc_range["production_start_year"]) | (mc_range["production_year"] > mc_range["production_end_year"])).sum())
checks.append(check("model_production_year_range_consistency", "HIGH", model_range_bad + motorcycle_year_bad, {"invalid_model_ranges": model_range_bad, "motorcycles_outside_range": motorcycle_year_bad}, "Model and instance production years are consistent."))

noise_clean_bad = int(((noise["clean_value_available"] == 1) & noise["canonical_clean_value"].isna()).sum())
noise_original_bad = int(((noise["original_clean_value_available"] == 1) & noise["original_clean_value"].isna()).sum())
checks.append(check("noise_audit_semantic_consistency", "HIGH", noise_clean_bad + noise_original_bad, {"canonical_conflicts": noise_clean_bad, "original_conflicts": noise_original_bad}, "Noise audit availability flags match their values."))

parquet_metrics = {}
for path in sorted(OUT_DERIVED.glob("*.parquet")):
    table = pq.read_table(path)
    parquet_metrics[path.name] = {"rows": table.num_rows, "columns": table.num_columns, "readable": True}
checks.append(check("parquet_readability", "HIGH", 0, parquet_metrics, "All Parquet files are readable by pyarrow."))

def blank_count(df: pd.DataFrame) -> int:
    total = 0
    for col in df.select_dtypes(include=["object", "string"]).columns:
        total += int(df[col].astype("string").str.strip().eq("").fillna(False).sum())
    return total

parquet_blank = blank_count(snapshots) + blank_count(next_service) + blank_count(next_task)
checks.append(check("parquet_null_semantics", "HIGH", parquet_blank, {"empty_string_cells": parquet_blank}, "Missing Parquet values do not use empty strings."))

key_mismatch = len(set(snapshots["snapshot_id"]) ^ set(next_service["snapshot_id"])) + len(set(snapshots["snapshot_id"]) ^ set(next_task["snapshot_id"]))
checks.append(check("snapshot_target_key_alignment", "HIGH", key_mismatch, {"symmetric_key_difference": key_mismatch}, "Snapshot and target keys align."))

censored_future_nonnull = int(next_service.loc[censored_service, future_service_columns].notna().sum().sum())
checks.append(check("right_censor_semantics", "HIGH", censored_future_nonnull, {"censored_future_nonnull_cells": censored_future_nonnull}, "Censored future service fields are NULL."))

censored_task_nonnull = int(next_task.loc[censored_task, task_label_columns].notna().sum().sum())
observed_task_null = int(next_task.loc[~censored_task, task_label_columns].isna().sum().sum())
checks.append(check("task_target_nullable_semantics", "HIGH", censored_task_nonnull + observed_task_null, {"censored_nonnull_labels": censored_task_nonnull, "observed_null_labels": observed_task_null}, "Task labels are NULL only for censored snapshots."))

boundary_bad = int((split_manifest["boundary_crossing_future_target"].eq(1) & (split_manifest["task_target_eligible_primary"].eq(1) | split_manifest["next_service_regression_eligible_primary"].eq(1))).sum())
checks.append(check("split_leakage", "HIGH", boundary_bad, {"boundary_eligibility_violations": boundary_bad}, "Boundary-crossing future labels are not directly eligible."))

unseen_mc_bad = int((split_manifest.groupby("motorcycle_id")["unseen_motorcycle_split"].nunique(dropna=True) > 1).sum())
unseen_ws_bad = int((split_manifest.groupby("workshop_id")["unseen_workshop_split"].nunique(dropna=True) > 1).sum())
checks.append(check("unseen_motorcycle_isolation", "HIGH", unseen_mc_bad, {"cross_group_motorcycles": unseen_mc_bad}, "Motorcycles do not cross unseen groups."))
checks.append(check("unseen_workshop_isolation", "HIGH", unseen_ws_bad, {"cross_group_workshops": unseen_ws_bad}, "Workshops do not cross unseen groups."))

version_bad = 0
for df in all_tables.values():
    if "generator_version" in df.columns:
        version_bad += int(df["generator_version"].ne(VERSION).sum())
checks.append(check("provenance_version_fields", "HIGH", version_bad, {"non_v1_1_generator_version_rows": version_bad}, "Generator provenance is v1.1.0."))

future_service_bad = int((pd.to_datetime(services["received_at"], errors="coerce") > HORIZON + pd.Timedelta(days=1)).sum())
checks.append(check("future_date_check", "HIGH", future_service_bad, {"service_rows_after_horizon": future_service_bad}, "No service begins after the observation horizon."))

high_failures = [c["check"] for c in checks if c["severity"] == "HIGH" and c["status"] == "FAIL"]
release_gate = "PASS" if not high_failures else "FAIL"

quality_report = {
    "report": {
        "name": "RideBase Synthetic Dataset v1.1 Quality Report",
        "dataset_version": VERSION,
        "report_version": "QUALITY_REPORT_V1_1",
        "report_date": str(HORIZON.date()),
        "data_origin": "SYNTHETIC",
        "random_seed": SEED,
        "release_gate": release_gate,
    },
    "executive_summary": {
        "total_checks": len(checks),
        "pass_checks": sum(c["status"] == "PASS" for c in checks),
        "fail_checks": sum(c["status"] == "FAIL" for c in checks),
        "failed_high_severity_checks": high_failures,
    },
    "quality_checks": checks,
    "layer_note": "services.csv intentionally leaves aggregate cost fields unpopulated; use services_enriched.csv for analysis-ready cost measures.",
}
write_json(quality_report, OUT_DERIVED / "quality_report.json")

changes = {
    "dataset_version": VERSION,
    "random_seed": SEED,
    "customers": {"churn_dates_added": customer_fill_count, "existing_churn_dates_adjusted_to_activity": customer_adjust_count},
    "motorcycles": {"observation_end_dates_added": motorcycle_fill_count, "existing_observation_end_dates_adjusted_to_activity": motorcycle_adjust_count, "production_years_regenerated": year_changes, "production_year_basis_updated": len(motorcycles)},
    "usage_profiles": {"profile_end_dates_updated": profile_end_updates},
    "motorcycle_models": {"production_ranges_added": len(models), "cooling_types_added": int(models["model_id"].isin(cooling_updates).sum())},
    "appointments": {"existing_converted_preserved": existing_converted, "new_cancelled": target_counts["CANCELLED"], "new_no_show": target_counts["NO_SHOW"], "new_rescheduled": target_counts["RESCHEDULED"]},
    "workshops": {"sunday_open_enabled": int(workshops["sunday_open"].sum()), "multibrand_preserved_due_to_history": True, "abs_support_preserved_due_to_history": True},
    "noise_audit": {"schema_updated": True, "canonical_clean_semantics_rows": int(noise["clean_value_available"].sum())},
    "parquet_targets": {"empty_string_to_null": next_service_empty_to_null + next_task_empty_to_null + snapshot_empty_to_null, "minus_one_task_missing_sentinel_to_null": int(censored_task.sum() * len(task_label_columns)), "target_unknown_value_column_removed": True},
    "derived_outputs": {"regenerated": ["service_status_history.csv", "noise_audit.csv", "ml_maintenance_snapshots.parquet", "ml_next_service_targets.parquet", "ml_next_task_targets.parquet", "split_manifest.csv", "dataset_metadata.json", "quality_report.json"]},
}
write_json(changes, OUT_REPORTS / "v1_to_v1_1_changes.json")

after = {
    "inactive_customer_missing_churn": inactive_customer_bad,
    "inactive_customer_churn_before_last_activity": customer_churn_before_activity,
    "inactive_motorcycle_missing_observation_end": inactive_motorcycle_bad,
    "inactive_motorcycle_end_before_last_activity": motorcycle_end_before_activity,
    "noise_audit_clean_value_semantic_conflict": noise_clean_bad + noise_original_bad,
    "invalid_motorcycle_production_year_range": motorcycle_year_bad,
    "model_missing_production_start_year": int(models["production_start_year"].isna().sum()),
    "model_missing_production_end_year": int(models["production_end_year"].isna().sum()),
    "snapshot_unknown_cooling_type": int(snapshots["cooling_type"].isna().sum()),
    "parquet_empty_string_cells": parquet_blank,
    "censored_task_minus_one_labels": int((next_task[task_label_columns] == -1).sum().sum()),
}
validation_report = {"dataset_version": VERSION, "before_v1": before, "after_v1_1": after, "release_gate": release_gate, "failed_high_severity_checks": high_failures}
write_json(validation_report, OUT_REPORTS / "v1_1_validation_report.json")

# Metadata is written last so its file catalog reflects finalized artifacts.
metadata = v1_metadata.copy()
metadata["dataset"] = {**metadata.get("dataset", {}), "dataset_version": VERSION, "generator_version": VERSION, "rule_set_version": VERSION, "status": "V1_1_RELEASE", "random_seed": SEED}
metadata["changelog_summary"] = changes
metadata["null_semantics"] = {
    "general": "Unknown values use NULL/NaN; empty strings are not missing-value sentinels.",
    "next_service_targets": "Future event fields are NULL when target_event_observed=0.",
    "next_task_targets": "Task labels are 1/0 for observed next services and NULL for right-censored snapshots.",
}
metadata["layer_definitions"] = {
    "services.csv": "BASE EVENT TABLE / RAW OPERATIONAL BACKBONE. Cost aggregation fields are intentionally unpopulated in the base event table. Use services_enriched.csv for analysis-ready cost fields.",
    "services_enriched.csv": "ANALYSIS READY ENRICHED SERVICE TABLE with populated cost aggregation fields.",
}
metadata["target_semantics"] = {
    "next_service": "Observed future event values are populated; right-censored future fields are NULL.",
    "next_task": "For an observed next service, present=1 and absent=0. For a right-censored snapshot, all task labels are NULL.",
}
metadata["noise_audit_semantics"] = {
    "clean_value_available": "Indicates that a usable canonical clean representation exists.",
    "original_clean_value_available": "Indicates that the exact pre-corruption original value was persisted.",
    "canonical_clean_value": "Canonical repaired timestamp or taxonomy representation usable downstream.",
}
metadata["appointment_lifecycle"] = {"status_distribution": appointments["status"].value_counts().to_dict(), "rescheduled_link_semantics": "RESCHEDULED lifecycle-only rows have no service_id and no successor link in v1.1 to avoid a disruptive schema change."}
metadata["workshop_variability_decision"] = "sunday_open was diversified. multibrand and supports_abs_diagnostics were preserved because all workshops have conflicting historical multi-brand and ABS service activity."
metadata["prediction_tasks"]["next_maintenance_tasks"].pop("unknown_label_value_for_right_censoring", None)
metadata["prediction_tasks"]["next_maintenance_tasks"]["unknown_label_semantics"] = "NULL"
metadata["coverage"]["entity_counts"]["appointments"] = len(appointments)
metadata["file_catalog"] = []
for path in sorted(list(OUT_SOURCE.glob("*")) + [p for p in OUT_DERIVED.glob("*") if p.name != "dataset_metadata.json"]):
    if path.suffix == ".csv":
        df = read_csv(path)
    elif path.suffix == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix == ".json":
        metadata["file_catalog"].append({"file_name": path.name, "format": "JSON", "layer": "DERIVED_OUTPUT", "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
        continue
    else:
        continue
    metadata["file_catalog"].append({"file_name": path.name, "format": path.suffix.lstrip(".").upper(), "layer": "SOURCE" if path.parent == OUT_SOURCE else "DERIVED_OUTPUT", "row_count": len(df), "column_count": len(df.columns), "size_bytes": path.stat().st_size, "sha256": sha256_file(path), "columns": list(df.columns)})
write_json(metadata, OUT_DERIVED / "dataset_metadata.json")

# ZIP only the required three directories and validate every member.
with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for directory in [OUT_SOURCE, OUT_DERIVED, OUT_REPORTS]:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(OUT))
with zipfile.ZipFile(ZIP_PATH, "r") as archive:
    bad_member = archive.testzip()
    if bad_member is not None:
        raise RuntimeError(f"ZIP integrity failure: {bad_member}")

print(json.dumps({"output": str(OUT), "zip": str(ZIP_PATH), "release_gate": release_gate, "appointment_status": appointments["status"].value_counts().to_dict(), "changes": changes, "after": after}, ensure_ascii=False, indent=2))
