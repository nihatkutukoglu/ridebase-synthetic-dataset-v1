from __future__ import annotations

import hashlib
import json
import math
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parent
V11 = ROOT / "ridebase_v1_1"
OUT = ROOT / "ridebase_v1_2"
SRC = OUT / "source_tables"
DER = OUT / "derived_outputs"
REP = OUT / "reports"
TABLES = REP / "tables"
ZIP_PATH = ROOT / "ridebase_synthetic_dataset_v1_2.zip"
VERSION = "1.2.0"
SEED = 42
HORIZON = pd.Timestamp("2026-08-25")
FAILURE_TYPES = {"REPAIR", "BREAKDOWN"}


def stable_unit(*parts: object, salt: str = "") -> float:
    raw = ":".join([str(SEED), salt, *map(str, parts)]).encode()
    return int(hashlib.sha256(raw).hexdigest()[:15], 16) / float(16**15)


def stable_between(low: float, high: float, *parts: object, salt: str = "") -> float:
    return low + (high - low) * stable_unit(*parts, salt=salt)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def write_json(obj: dict, path: Path) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_versions(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["generator_version", "taxonomy_version", "policy_version", "profile_rule_version", "feature_version", "target_version"]:
        if col in out.columns:
            out[col] = VERSION
    return out


def normalize_strings(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.select_dtypes(include=["object", "string"]).columns:
        mask = out[col].astype("string").str.strip().eq("").fillna(False)
        out.loc[mask, col] = pd.NA
    return out


def check(name: str, severity: str, violations: int, metrics: dict, summary: str) -> dict:
    return {
        "check": name,
        "status": "PASS" if int(violations) == 0 else "FAIL",
        "severity": severity,
        "summary": summary,
        "metrics": {**metrics, "violations": int(violations)},
    }


if not V11.exists():
    raise SystemExit(f"Missing immutable v1.1 input: {V11}")
if OUT.exists() or ZIP_PATH.exists():
    raise SystemExit("Refusing to overwrite an existing v1.2 directory or ZIP")
SRC.mkdir(parents=True)
DER.mkdir(parents=True)
TABLES.mkdir(parents=True)

source = {p.name: read_csv(p) for p in sorted((V11 / "source_tables").glob("*.csv"))}
v11_source = {name: df.copy() for name, df in source.items()}
motorcycles = source["motorcycles.csv"].copy()
models = source["ridebase_motorcycle_models_v1.csv"].copy()
usage = source["usage_profiles.csv"].copy()
mileage = source["mileage_timeline_monthly.csv"].copy()
services = source["services.csv"].copy()
enriched = source["services_enriched.csv"].copy()
tasks = source["service_tasks.csv"].copy()
taxonomy = source["maintenance_tasks.csv"].copy()

# ---------------------------------------------------------------------------
# Usage profiles: category-conditioned, brand-independent assignment.
# ---------------------------------------------------------------------------
category_usage = {
    "SCOOTER": {"COMMUTER": .48, "COURIER": .20, "WEEKEND": .13, "TOURING": .05, "SEASONAL": .11, "TRACK": .01, "OFFROAD": .02},
    "BIG_SCOOTER": {"COMMUTER": .35, "COURIER": .08, "WEEKEND": .20, "TOURING": .22, "SEASONAL": .12, "TRACK": .01, "OFFROAD": .02},
    "CUB": {"COMMUTER": .51, "COURIER": .25, "WEEKEND": .11, "TOURING": .03, "SEASONAL": .08, "TRACK": .01, "OFFROAD": .01},
    "ADVENTURE": {"COMMUTER": .18, "COURIER": .03, "WEEKEND": .18, "TOURING": .34, "SEASONAL": .07, "TRACK": .03, "OFFROAD": .17},
    "SUPERSPORT": {"COMMUTER": .16, "COURIER": .01, "WEEKEND": .35, "TOURING": .08, "SEASONAL": .10, "TRACK": .28, "OFFROAD": .02},
    "TOURING": {"COMMUTER": .18, "COURIER": .02, "WEEKEND": .24, "TOURING": .42, "SEASONAL": .09, "TRACK": .02, "OFFROAD": .03},
    "SCRAMBLER": {"COMMUTER": .24, "COURIER": .02, "WEEKEND": .27, "TOURING": .18, "SEASONAL": .08, "TRACK": .04, "OFFROAD": .17},
    "CRUISER": {"COMMUTER": .20, "COURIER": .01, "WEEKEND": .42, "TOURING": .22, "SEASONAL": .12, "TRACK": .01, "OFFROAD": .02},
    "NAKED": {"COMMUTER": .38, "COURIER": .05, "WEEKEND": .28, "TOURING": .13, "SEASONAL": .08, "TRACK": .06, "OFFROAD": .02},
    "ROADSTER": {"COMMUTER": .35, "COURIER": .04, "WEEKEND": .31, "TOURING": .15, "SEASONAL": .10, "TRACK": .03, "OFFROAD": .02},
    "MINI_BIKE": {"COMMUTER": .30, "COURIER": .02, "WEEKEND": .42, "TOURING": .05, "SEASONAL": .16, "TRACK": .03, "OFFROAD": .02},
    "EV_SCOOTER": {"COMMUTER": .52, "COURIER": .19, "WEEKEND": .13, "TOURING": .03, "SEASONAL": .10, "TRACK": .01, "OFFROAD": .02},
}
default_usage = category_usage["NAKED"]
mc_category = motorcycles.set_index("motorcycle_id")["category"]
mileage_annual = mileage.groupby("motorcycle_id")["km_added"].mean().mul(12)

def deterministic_choice(weights: dict[str, float], key: str) -> str:
    u = stable_unit(key, salt="usage-choice")
    total = 0.0
    for label, weight in weights.items():
        total += weight
        if u <= total:
            return label
    return list(weights)[-1]

usage["usage_type"] = [deterministic_choice(category_usage.get(mc_category.get(mid), default_usage), mid) for mid in usage["motorcycle_id"]]
usage["annual_km_baseline"] = usage["motorcycle_id"].map(mileage_annual).fillna(usage["annual_km_baseline"]).round().clip(1200, 60000).astype(int)
q_low, q_high = usage["annual_km_baseline"].quantile([.35, .75])
usage["riding_intensity"] = np.select(
    [usage["annual_km_baseline"].le(q_low), usage["annual_km_baseline"].ge(q_high)],
    ["LOW", "HIGH"], default="MEDIUM",
)
usage_base_load = usage["usage_type"].map({"COMMUTER": 1.00, "WEEKEND": .94, "TOURING": 1.06, "COURIER": 1.12, "TRACK": 1.18, "OFFROAD": 1.16, "SEASONAL": .95})
usage["load_severity_factor"] = [
    round(float(np.clip(base + stable_between(-.08, .08, mid, salt="load"), .82, 1.28)), 3)
    for base, mid in zip(usage_base_load, usage["motorcycle_id"])
]
usage["annual_km_basis"] = "OBSERVED_MONTHLY_EXPOSURE_ANNUALIZED_V1_2"
usage["profile_rule_version"] = VERSION
usage["generator_version"] = VERSION
mileage["usage_type"] = mileage["motorcycle_id"].map(usage.set_index("motorcycle_id")["usage_type"])
mileage["annual_km_baseline"] = mileage["motorcycle_id"].map(usage.set_index("motorcycle_id")["annual_km_baseline"])
mileage["generator_version"] = VERSION

# ---------------------------------------------------------------------------
# Bounded latent risk and synthetic warranty policy.
# ---------------------------------------------------------------------------
brand_residual = {b: stable_between(.985, 1.015, b, salt="brand-residual") for b in sorted(motorcycles["brand"].unique())}
model_residual = {m: stable_between(.94, 1.06, m, salt="model-residual") for m in sorted(motorcycles["model_id"].unique())}
motorcycles["brand_risk_residual"] = motorcycles["brand"].map(brand_residual).round(5)
motorcycles["model_risk_residual"] = motorcycles["model_id"].map(model_residual).round(5)

def chronic_tier(mid: str) -> str:
    u = stable_unit(mid, salt="chronic")
    return "LOW" if u < .20 else ("NORMAL" if u < .95 else "ELEVATED")

motorcycles["chronic_risk_tier"] = motorcycles["motorcycle_id"].map(chronic_tier)
motorcycles["warranty_months"] = [24 + 6 * int(stable_unit(model, salt="warranty-months") * 3) for model in motorcycles["model_id"]]
motorcycles["warranty_km_limit"] = [30000 + 10000 * int(stable_unit(model, salt="warranty-km") * 3) for model in motorcycles["model_id"]]
motorcycles["generator_version"] = VERSION

# ---------------------------------------------------------------------------
# Pre-service state and hazard generation. Future rows are never consulted.
# ---------------------------------------------------------------------------
services["received_at"] = pd.to_datetime(services["received_at"], errors="coerce")
services["trigger_due_date"] = pd.to_datetime(services["trigger_due_date"], errors="coerce")
service_work = services.merge(
    motorcycles[["motorcycle_id", "model_id", "brand", "model_name", "category", "powertrain_type", "production_year", "first_registration_date", "brand_risk_residual", "model_risk_residual", "chronic_risk_tier", "warranty_months", "warranty_km_limit"]],
    on="motorcycle_id", how="left",
).merge(
    usage[["motorcycle_id", "usage_type", "riding_intensity", "load_severity_factor", "storage_condition", "climate_zone", "annual_km_baseline"]],
    on="motorcycle_id", how="left",
).sort_values(["motorcycle_id", "received_at", "service_id"]).reset_index()
service_work["service_age_years"] = (service_work["received_at"].dt.year - service_work["production_year"]).clip(lower=0)

last_overdue_days: dict[str, float] = {}
last_overdue_km: dict[str, float] = {}
pre_days, pre_km = [], []
for row in service_work.itertuples():
    mid = row.motorcycle_id
    pre_days.append(last_overdue_days.get(mid, 0.0))
    pre_km.append(last_overdue_km.get(mid, 0.0))
    if row.service_type_code == "PERIODIC":
        delay = 0.0 if pd.isna(row.service_delay_days) else max(float(row.service_delay_days), 0.0)
        km_delay = 0.0 if pd.isna(row.trigger_due_km) else max(float(row.odometer_km) - float(row.trigger_due_km), 0.0)
        last_overdue_days[mid] = delay
        last_overdue_km[mid] = km_delay
service_work["maintenance_overdue_days_pre_service"] = pre_days
service_work["maintenance_overdue_km_pre_service"] = pre_km

usage_mult = {"COMMUTER": 1.00, "WEEKEND": .94, "TOURING": 1.06, "COURIER": 1.25, "TRACK": 1.55, "OFFROAD": 1.45, "SEASONAL": .96}
intensity_mult = {"LOW": .90, "MEDIUM": 1.00, "HIGH": 1.18}
storage_mult = {"INDOOR": .94, "GARAGE": .96, "COVERED_PARKING": 1.03, "STREET": 1.12}
climate_mult = {"CONTINENTAL_COOL": .96, "TEMPERATE_HUMID": 1.00, "CONTINENTAL_DRY": 1.01, "MEDITERRANEAN_COASTAL": 1.04, "MEDITERRANEAN_HOT": 1.05, "HUMID_RAINY": 1.08, "SEMI_ARID_HOT": 1.06}
category_mult = {"EV_SCOOTER": .96, "SCOOTER": 1.00, "BIG_SCOOTER": 1.03, "CUB": .97, "NAKED": 1.04, "ROADSTER": 1.03, "SUPERSPORT": 1.12, "TOURING": 1.04, "SCRAMBLER": 1.10, "ADVENTURE": 1.12, "CRUISER": 1.04, "MINI_BIKE": .98}
chronic_mult = {"LOW": .85, "NORMAL": 1.00, "ELEVATED": 1.22}

def overdue_factor(days: float, km: float) -> float:
    day_factor = 1.00 if days <= 0 else (1.04 if days <= 7 else (1.10 if days <= 30 else (1.18 if days <= 60 else 1.30)))
    km_factor = 1.00 + min(max(km, 0) / 10000.0 * .10, .25)
    return day_factor * km_factor

base_score = []
for row in service_work.itertuples():
    age = float(row.service_age_years)
    odometer = max(float(row.odometer_km), 0.0)
    load = float(row.load_severity_factor)
    load_factor = .90 if load < .95 else (1.00 if load < 1.05 else (1.10 if load < 1.15 else 1.22))
    score = (
        (1.0 + .12 * age)
        * min(1.0 + .18 * (odometer / 10000.0) ** .65, 2.8)
        * usage_mult.get(row.usage_type, 1.0)
        * intensity_mult.get(row.riding_intensity, 1.0)
        * load_factor
        * storage_mult.get(row.storage_condition, 1.0)
        * climate_mult.get(row.climate_zone, 1.0)
        * overdue_factor(float(row.maintenance_overdue_days_pre_service), float(row.maintenance_overdue_km_pre_service))
        * category_mult.get(row.category, 1.0)
        * float(row.brand_risk_residual)
        * float(row.model_risk_residual)
        * chronic_mult.get(row.chronic_risk_tier, 1.0)
        * stable_between(.92, 1.08, row.service_id, salt="hazard-noise")
    )
    base_score.append(score)
service_work["physical_hazard_score"] = base_score

def simulate(base_hazard: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    outcomes, probs, previous = [], [], []
    prior_count: dict[str, int] = {}
    for row in service_work.itertuples():
        count = prior_count.get(row.motorcycle_id, 0)
        p = float(np.clip(base_hazard * row.physical_hazard_score * (1 + .12 * min(count, 3)), .002, .28))
        event = stable_unit(row.service_id, salt="failure-draw") < p
        outcomes.append(event)
        probs.append(p)
        previous.append(count)
        if event:
            prior_count[row.motorcycle_id] = count + 1
    return np.asarray(outcomes), np.asarray(probs), np.asarray(previous)

lo, hi = .001, .08
for _ in range(25):
    mid = (lo + hi) / 2
    generated, probability, previous_failure_count = simulate(mid)
    if generated.mean() < .053:
        lo = mid
    else:
        hi = mid
generated, probability, previous_failure_count = simulate((lo + hi) / 2)
service_work["failure_event"] = generated.astype(int)
service_work["failure_hazard_score"] = probability
service_work["previous_failure_count"] = previous_failure_count

component_options = ["ENGINE", "ELECTRICAL", "BRAKES", "FUEL", "INTAKE", "COOLING", "TRANSMISSION", "FINAL_DRIVE", "STEERING", "SUSPENSION", "TIRES_WHEELS"]
base_component_weights = np.array([.15, .15, .13, .09, .07, .08, .10, .08, .04, .06, .05])

def choose_component(row) -> str:
    if row.powertrain_type == "EV":
        options = ["EV_POWERTRAIN", "ELECTRICAL", "BRAKES", "FINAL_DRIVE", "STEERING", "SUSPENSION", "TIRES_WHEELS"]
        weights = np.array([.28, .23, .14, .08, .06, .10, .11])
    else:
        options, weights = component_options, base_component_weights.copy()
        if row.category in {"ADVENTURE", "SCRAMBLER"} or row.usage_type == "OFFROAD":
            for comp in ["FINAL_DRIVE", "STEERING", "SUSPENSION", "TIRES_WHEELS"]:
                weights[options.index(comp)] *= 1.6
        if row.usage_type == "TRACK":
            for comp in ["ENGINE", "BRAKES", "TRANSMISSION", "TIRES_WHEELS"]:
                weights[options.index(comp)] *= 1.5
        if row.service_age_years >= 7:
            for comp in ["ENGINE", "ELECTRICAL", "COOLING"]:
                weights[options.index(comp)] *= 1.35
    weights = weights / weights.sum()
    u, total = stable_unit(row.service_id, salt="component"), 0.0
    for comp, weight in zip(options, weights):
        total += float(weight)
        if u <= total:
            return comp
    return options[-1]

components, severities, service_types = [], [], []
for row in service_work.itertuples():
    if not row.failure_event:
        components.append(pd.NA); severities.append(pd.NA); service_types.append("PERIODIC" if row.service_type_code in FAILURE_TYPES else row.service_type_code)
        continue
    component = choose_component(row)
    u = stable_unit(row.service_id, salt="severity")
    severity = "LOW" if u < .55 else ("MEDIUM" if u < .87 else "HIGH")
    breakdown_p = {"LOW": .05, "MEDIUM": .22, "HIGH": .68}[severity]
    service_type = "BREAKDOWN" if stable_unit(row.service_id, salt="breakdown") < breakdown_p else "REPAIR"
    components.append(component); severities.append(severity); service_types.append(service_type)
service_work["primary_fault_component"] = components
service_work["failure_severity"] = severities
service_work["service_type_code_v12"] = service_types

service_work["first_registration_date"] = pd.to_datetime(service_work["first_registration_date"], errors="coerce")
service_work["warranty_end_date"] = service_work["first_registration_date"] + service_work["warranty_months"].map(lambda x: pd.DateOffset(months=int(x)))
service_work["is_warranty_v12"] = (
    service_work["failure_event"].eq(1)
    & service_work["received_at"].le(service_work["warranty_end_date"])
    & service_work["odometer_km"].le(service_work["warranty_km_limit"])
    & service_work["failure_severity"].ne("HIGH")
).astype(int)

# Restore original row order and update the base service table.
service_work = service_work.sort_values("index")
services["service_type_code"] = service_work["service_type_code_v12"].to_numpy()
services["is_breakdown"] = services["service_type_code"].eq("BREAKDOWN").astype(int)
services["is_warranty"] = service_work["is_warranty_v12"].to_numpy()
services["maintenance_overdue_days_pre_service"] = service_work["maintenance_overdue_days_pre_service"].to_numpy()
services["maintenance_overdue_km_pre_service"] = service_work["maintenance_overdue_km_pre_service"].to_numpy()
services["overdue_maintenance_days_at_failure"] = np.where(service_work["failure_event"].eq(1), service_work["maintenance_overdue_days_pre_service"], np.nan)
services["overdue_maintenance_km_at_failure"] = np.where(service_work["failure_event"].eq(1), service_work["maintenance_overdue_km_pre_service"], np.nan)
services["previous_failure_count"] = service_work["previous_failure_count"].to_numpy()
services["failure_hazard_score"] = service_work["failure_hazard_score"].round(7).to_numpy()
services["primary_fault_component"] = service_work["primary_fault_component"].to_numpy()
services["failure_severity"] = service_work["failure_severity"].to_numpy()
failure_mask = services["service_type_code"].isin(FAILURE_TYPES)
services.loc[failure_mask, "service_delay_days"] = np.nan
services.loc[failure_mask, "primary_trigger_task"] = "FAULT_EVENT"
services.loc[failure_mask & services["service_type_code"].eq("BREAKDOWN"), "arrival_mode"] = "WALK_IN"
services.loc[~failure_mask & services["primary_trigger_task"].eq("UNSCHEDULED_EVENT"), "primary_trigger_task"] = "GENERAL_SAFETY_INSPECTION"
services["scenario_id"] = "HAZARD_EVENT_SIM_V1_2"
services["generator_version"] = VERSION

# ---------------------------------------------------------------------------
# Fault taxonomy and service task regeneration.
# ---------------------------------------------------------------------------
new_fault_defs = [
    ("ENGINE_FAULT_DIAGNOSTIC", "Motor Arıza Teşhisi", "Engine Fault Diagnostic", "ENGINE", "ICE", pd.NA),
    ("ELECTRICAL_FAULT_DIAGNOSTIC", "Elektrik Sistemi Arıza Teşhisi", "Electrical Fault Diagnostic", "ELECTRICAL", "BOTH", pd.NA),
    ("BRAKE_FAULT_DIAGNOSTIC", "Fren Sistemi Arıza Teşhisi", "Brake Fault Diagnostic", "BRAKES", "BOTH", pd.NA),
    ("INTAKE_FAULT_DIAGNOSTIC", "Emme Sistemi Arıza Teşhisi", "Intake Fault Diagnostic", "INTAKE", "ICE", pd.NA),
    ("COOLING_FAULT_DIAGNOSTIC", "Soğutma Sistemi Arıza Teşhisi", "Cooling Fault Diagnostic", "COOLING", "ICE", pd.NA),
    ("TRANSMISSION_FAULT_DIAGNOSTIC", "Şanzıman Arıza Teşhisi", "Transmission Fault Diagnostic", "TRANSMISSION", "ICE", pd.NA),
    ("CHAIN_DRIVE_DIAGNOSTIC", "Zincir Aktarma Arıza Teşhisi", "Chain Drive Fault Diagnostic", "FINAL_DRIVE", "BOTH", "CHAIN"),
    ("CVT_BELT_FAILURE_DIAGNOSTIC", "CVT Kayışı Arıza Teşhisi", "CVT Belt Failure Diagnostic", "FINAL_DRIVE", "ICE", "V_BELT"),
    ("FINAL_DRIVE_FAULT_INSPECTION", "Son Aktarma Arıza Kontrolü", "Final Drive Fault Inspection", "FINAL_DRIVE", "BOTH", pd.NA),
    ("STEERING_FAULT_INSPECTION", "Direksiyon Sistemi Arıza Kontrolü", "Steering Fault Inspection", "STEERING", "BOTH", pd.NA),
    ("SUSPENSION_FAULT_INSPECTION", "Süspansiyon Arıza Kontrolü", "Suspension Fault Inspection", "SUSPENSION", "BOTH", pd.NA),
    ("TIRE_WHEEL_FAULT_INSPECTION", "Lastik ve Teker Arıza Kontrolü", "Tire and Wheel Fault Inspection", "TIRES_WHEELS", "BOTH", pd.NA),
]
for code, tr, en, component, powertrain, final_drive in new_fault_defs:
    if code in set(taxonomy["task_code"]):
        continue
    taxonomy.loc[len(taxonomy)] = {
        "task_code": code, "canonical_name_tr": tr, "canonical_name_en": en, "component_group": component,
        "action_type": "DIAGNOSE" if "DIAGNOSTIC" in code else "INSPECT", "is_periodic": 0, "is_wear_based": 0,
        "is_fault_based": 1, "requires_part": 0, "applicable_powertrain": powertrain,
        "required_final_drive": final_drive, "required_cooling_type": pd.NA, "required_transmission_type": pd.NA,
        "part_category_hint": pd.NA, "can_be_next_service_target": 1,
        "notes": "Synthetic v1.2 primary fault task; component selected from pre-event state.", "taxonomy_version": VERSION,
    }
taxonomy["taxonomy_version"] = VERSION
taxonomy_lookup = taxonomy.set_index("task_code")
model_drive = models.set_index("model_id")["final_drive_type"]
mc_drive = motorcycles.set_index("motorcycle_id")["model_id"].map(model_drive)
component_task = {
    "ENGINE": "ENGINE_FAULT_DIAGNOSTIC", "ELECTRICAL": "ELECTRICAL_FAULT_DIAGNOSTIC", "BRAKES": "BRAKE_FAULT_DIAGNOSTIC",
    "FUEL": "FUEL_SYSTEM_DIAGNOSTIC", "INTAKE": "INTAKE_FAULT_DIAGNOSTIC", "COOLING": "COOLING_FAULT_DIAGNOSTIC",
    "TRANSMISSION": "TRANSMISSION_FAULT_DIAGNOSTIC", "STEERING": "STEERING_FAULT_INSPECTION",
    "SUSPENSION": "SUSPENSION_FAULT_INSPECTION", "TIRES_WHEELS": "TIRE_WHEEL_FAULT_INSPECTION",
    "EV_POWERTRAIN": "EV_DRIVE_MOTOR_DIAGNOSTIC",
}

def primary_task_code(row) -> str:
    if row.primary_fault_component != "FINAL_DRIVE":
        return component_task[row.primary_fault_component]
    drive = mc_drive.get(row.motorcycle_id)
    if drive == "CHAIN": return "CHAIN_DRIVE_DIAGNOSTIC"
    if drive in {"BELT", "V_BELT"}: return "CVT_BELT_FAILURE_DIAGNOSTIC"
    return "FINAL_DRIVE_FAULT_INSPECTION"

tasks["task_role"] = "PERIODIC"
failure_service_ids = set(services.loc[failure_mask, "service_id"])
tasks.loc[tasks["service_id"].isin(failure_service_ids), "task_role"] = "OPPORTUNISTIC_MAINTENANCE"
task_suffix = tasks["service_task_id"].astype(str).str.extract(r"(\d+)$", expand=False).astype(int)
next_task_id = int(task_suffix.max()) + 1
new_task_rows = []
service_by_id = services.set_index("service_id")
failure_state = service_work[service_work["failure_event"].eq(1)].set_index("service_id")
for offset, (service_id, row) in enumerate(failure_state.iterrows()):
    code = primary_task_code(row)
    meta = taxonomy_lookup.loc[code]
    service = service_by_id.loc[service_id]
    minutes = int(round(stable_between(18, 62, service_id, salt="fault-labor")))
    started = pd.Timestamp(service["received_at"]) + pd.Timedelta(minutes=5)
    completed_at = pd.to_datetime(service["completed_at"], errors="coerce")
    if pd.isna(completed_at) or completed_at < started:
        completed_at = started + pd.Timedelta(minutes=minutes)
    new_task_rows.append({
        "service_task_id": f"STK{next_task_id + offset:07d}", "service_id": service_id,
        "motorcycle_id": service["motorcycle_id"], "workshop_id": service["workshop_id"], "task_sequence": 0,
        "task_code": code, "display_title": meta["canonical_name_tr"], "title_variant_type": "CANONICAL",
        "component_group": meta["component_group"], "action_type": meta["action_type"], "trigger_reason": "FAULT",
        "is_policy_due": 0, "policy_id": pd.NA, "status": "COMPLETED", "completed": 1,
        "started_at": started, "completed_at": completed_at, "completed_by": f"TECH-{service['workshop_id']}-FAULT",
        "labor_minutes": minutes, "labor_cost": round(minutes * 10.0, 2), "labor_cost_basis": "SYNTHETIC_V1_2_FAULT_DIAGNOSTIC",
        "severity": row["failure_severity"], "data_origin": "SYNTHETIC", "generator_version": VERSION,
        "random_seed": SEED, "notes": "Primary fault task generated from pre-event hazard state.", "task_role": "PRIMARY_FAULT",
    })
new_tasks = pd.DataFrame(new_task_rows, columns=list(tasks.columns))
tasks = pd.concat([tasks, new_tasks], ignore_index=True)
tasks = tasks.sort_values(["service_id", "task_sequence", "service_task_id"]).reset_index(drop=True)
tasks["task_sequence"] = tasks.groupby("service_id").cumcount() + 1
tasks["generator_version"] = VERSION

# Enriched costs include the newly generated diagnostic labor; base services stay sparse.
added_labor = new_tasks.groupby("service_id")["labor_cost"].sum()
for col in ["labor_total", "parts_total", "discount_total", "tax_total", "grand_total", "subtotal_before_discount"]:
    enriched[col] = pd.to_numeric(enriched[col], errors="coerce")
enriched = enriched.drop(columns=[c for c in services.columns if c in enriched.columns and c not in {"service_id"}], errors="ignore").merge(services, on="service_id", how="right")
original_enriched = v11_source["services_enriched.csv"].set_index("service_id")
for col in ["labor_total", "parts_total", "discount_total", "tax_total", "grand_total", "subtotal_before_discount", "discount_rate", "tax_rate", "pricing_currency", "cost_calculation_basis", "cost_rule_version"]:
    enriched[col] = enriched["service_id"].map(original_enriched[col])
enriched["labor_total"] = enriched["labor_total"].fillna(0) + enriched["service_id"].map(added_labor).fillna(0)
enriched["subtotal_before_discount"] = enriched["labor_total"] + enriched["parts_total"].fillna(0)
enriched["tax_total"] = (enriched["subtotal_before_discount"] - enriched["discount_total"].fillna(0)) * enriched["tax_rate"].fillna(.20)
enriched["grand_total"] = enriched["subtotal_before_discount"] - enriched["discount_total"].fillna(0) + enriched["tax_total"]
enriched["cost_rule_version"] = VERSION
enriched["generator_version"] = VERSION

source["motorcycles.csv"] = motorcycles
source["usage_profiles.csv"] = usage
source["mileage_timeline_monthly.csv"] = mileage
source["services.csv"] = services
source["services_enriched.csv"] = enriched
source["service_tasks.csv"] = tasks
source["maintenance_tasks.csv"] = taxonomy
for name in source:
    source[name] = update_versions(source[name])
    write_csv(source[name], SRC / name)

# ---------------------------------------------------------------------------
# Regenerate derived files from v1.2 sources.
# ---------------------------------------------------------------------------
status_history = update_versions(read_csv(V11 / "derived_outputs/service_status_history.csv"))
status_history["scenario_id"] = "HAZARD_EVENT_SIM_V1_2"
write_csv(status_history, DER / "service_status_history.csv")
noise = update_versions(normalize_strings(read_csv(V11 / "derived_outputs/noise_audit.csv")))
write_csv(noise, DER / "noise_audit.csv")

snapshots = normalize_strings(pd.read_parquet(V11 / "derived_outputs/ml_maintenance_snapshots.parquet"))
service_state = services[["service_id", "service_type_code", "is_breakdown", "is_warranty", "maintenance_overdue_days_pre_service", "maintenance_overdue_km_pre_service", "previous_failure_count", "failure_hazard_score"]].copy()
fault_counts = tasks.merge(taxonomy[["task_code", "is_fault_based"]], on="task_code", how="left").groupby("service_id")["is_fault_based"].sum()
service_state["current_fault_task_count"] = service_state["service_id"].map(fault_counts).fillna(0).astype(int)
chron = services[["service_id", "motorcycle_id", "received_at", "service_type_code", "is_warranty"]].copy()
chron["received_at"] = pd.to_datetime(chron["received_at"])
chron = chron.sort_values(["motorcycle_id", "received_at", "service_id"])
chron["periodic_service_count"] = chron["service_type_code"].eq("PERIODIC").groupby(chron["motorcycle_id"]).cumsum()
chron["repair_service_count"] = chron["service_type_code"].eq("REPAIR").groupby(chron["motorcycle_id"]).cumsum()
chron["breakdown_service_count"] = chron["service_type_code"].eq("BREAKDOWN").groupby(chron["motorcycle_id"]).cumsum()
chron["warranty_service_count"] = chron["is_warranty"].groupby(chron["motorcycle_id"]).cumsum()
chron["total_fault_task_count"] = chron["service_id"].map(fault_counts).fillna(0).groupby(chron["motorcycle_id"]).cumsum()
service_state = service_state.merge(chron[["service_id", "periodic_service_count", "repair_service_count", "breakdown_service_count", "warranty_service_count", "total_fault_task_count"]], on="service_id")
state_lookup = service_state.set_index("service_id")
for target, source_col in {
    "current_is_breakdown": "is_breakdown", "current_is_warranty": "is_warranty", "current_fault_task_count": "current_fault_task_count",
    "periodic_service_count": "periodic_service_count", "repair_service_count": "repair_service_count", "breakdown_service_count": "breakdown_service_count",
    "warranty_service_count": "warranty_service_count", "total_fault_task_count": "total_fault_task_count",
}.items():
    if target in snapshots.columns:
        snapshots[target] = snapshots["source_service_id"].map(state_lookup[source_col]).astype(snapshots[target].dtype)
usage_lookup = usage.set_index("motorcycle_id")
for col in ["usage_type", "riding_intensity", "load_severity_factor", "annual_km_baseline", "storage_condition", "climate_zone"]:
    if col in snapshots.columns:
        snapshots[col] = snapshots["motorcycle_id"].map(usage_lookup[col])
for col in ["maintenance_overdue_days_pre_service", "maintenance_overdue_km_pre_service", "previous_failure_count", "failure_hazard_score"]:
    snapshots[col] = snapshots["source_service_id"].map(state_lookup[col])
snapshots["chronic_risk_tier"] = snapshots["motorcycle_id"].map(motorcycles.set_index("motorcycle_id")["chronic_risk_tier"])
snapshots["feature_version"] = VERSION
snapshots["generator_version"] = VERSION

next_service = normalize_strings(pd.read_parquet(V11 / "derived_outputs/ml_next_service_targets.parquet"))
next_lookup = services.set_index("service_id")
for target, src_col in {
    "next_service_type_code": "service_type_code", "next_service_primary_trigger_task": "primary_trigger_task",
    "next_service_arrival_mode": "arrival_mode", "next_service_is_breakdown": "is_breakdown", "next_service_is_warranty": "is_warranty",
}.items():
    next_service[target] = next_service["next_service_id"].map(next_lookup[src_col])
next_service["target_version"] = VERSION
next_service["generator_version"] = VERSION

next_task = normalize_strings(pd.read_parquet(V11 / "derived_outputs/ml_next_task_targets.parquet"))
task_lists = tasks.groupby("service_id").agg(
    next_task_codes=("task_code", lambda s: "|".join(sorted(set(s)))),
    next_completed_task_codes=("task_code", lambda s: "|".join(sorted(set(s)))),
    next_task_count=("task_code", "size"), next_completed_task_count=("completed", "sum"),
    next_declined_task_count=("status", lambda s: int((s == "DECLINED").sum())),
).reset_index().rename(columns={"service_id": "next_service_id"})
declined_codes = tasks[tasks["status"].eq("DECLINED")].groupby("service_id")["task_code"].agg(lambda s: "|".join(sorted(set(s))))
task_lists["next_declined_task_codes"] = task_lists["next_service_id"].map(declined_codes).fillna(pd.NA)
next_task = next_task.drop(columns=[c for c in ["next_task_codes", "next_completed_task_codes", "next_declined_task_codes", "next_task_count", "next_completed_task_count", "next_declined_task_count"] if c in next_task]).merge(task_lists, on="next_service_id", how="left")
all_task_codes = sorted(taxonomy["task_code"].unique())
codes_by_service = tasks.groupby("service_id")["task_code"].agg(set)
for code in all_task_codes:
    col = f"task__{code}"
    values = next_task["next_service_id"].map(lambda sid: int(code in codes_by_service.get(sid, set())) if pd.notna(sid) else pd.NA)
    next_task[col] = pd.array(values, dtype="Int8")
censored = next_task["target_event_observed"].eq(0)
for col in [c for c in next_task.columns if c.startswith("task__")]:
    next_task.loc[censored, col] = pd.NA
for col in ["next_task_count", "next_completed_task_count", "next_declined_task_count"]:
    next_task[col] = pd.array(next_task[col].mask(censored), dtype="Int16")
for col in ["next_service_id", "next_task_codes", "next_completed_task_codes", "next_declined_task_codes"]:
    next_task.loc[censored, col] = pd.NA
next_task["target_version"] = VERSION
next_task["taxonomy_version"] = VERSION
next_task["generator_version"] = VERSION

split = update_versions(normalize_strings(read_csv(V11 / "derived_outputs/split_manifest.csv")))
split["split_version"] = "SPLIT_MANIFEST_V1_2"
pq.write_table(pa.Table.from_pandas(snapshots, preserve_index=False), DER / "ml_maintenance_snapshots.parquet", compression="snappy")
pq.write_table(pa.Table.from_pandas(next_service, preserve_index=False), DER / "ml_next_service_targets.parquet", compression="snappy")
pq.write_table(pa.Table.from_pandas(next_task, preserve_index=False), DER / "ml_next_task_targets.parquet", compression="snappy")
write_csv(split, DER / "split_manifest.csv")

# ---------------------------------------------------------------------------
# Reliability audit metrics.
# ---------------------------------------------------------------------------
audit = service_work.copy()
audit["failure"] = audit["failure_event"].astype(int)
audit["age_bucket"] = pd.cut(audit["service_age_years"], [-1, 2, 5, 8, np.inf], labels=["0–2", "3–5", "6–8", "9+"])
audit["km_bucket"] = pd.cut(audit["odometer_km"], [-1, 10000, 25000, 50000, 75000, np.inf], labels=["0–10k", "10–25k", "25–50k", "50–75k", "75k+"])
audit["overdue_bucket"] = pd.cut(audit["maintenance_overdue_days_pre_service"], [-1, 0, 7, 30, 60, np.inf], labels=["0", "1–7", "8–30", "31–60", "60+"])
audit["annual_km_band"] = pd.cut(audit["annual_km_baseline"], [-1, 8000, 15000, 25000, np.inf], labels=["LOW", "MEDIUM", "HIGH", "VERY_HIGH"])

brand_table = audit.groupby("brand", observed=False).agg(
    motorcycle_count=("motorcycle_id", "nunique"), service_count=("service_id", "nunique"),
    repair_count=("service_type_code_v12", lambda s: int((s == "REPAIR").sum())),
    breakdown_count=("service_type_code_v12", lambda s: int((s == "BREAKDOWN").sum())),
    failure_count=("failure", "sum"), expected_failures=("failure_hazard_score", "sum"),
).reset_index()
brand_table["raw_failure_rate"] = brand_table["failure_count"] / brand_table["service_count"]
pooled = audit["failure"].mean()
# Empirical-Bayes prior equivalent to roughly six pooled failure events. This
# stabilizes adjusted rates for mid-sized brands without changing any event.
prior_events = 120.0
brand_table["observed_expected_ratio"] = (brand_table["failure_count"] + prior_events * pooled) / (brand_table["expected_failures"] + prior_events * pooled)
brand_table["adjusted_failure_rate"] = brand_table["observed_expected_ratio"] * pooled
km_by_brand = mileage.merge(motorcycles[["motorcycle_id", "brand"]], on="motorcycle_id").groupby("brand")["km_added"].sum()
brand_table["observed_km"] = brand_table["brand"].map(km_by_brand)
brand_table["failure_events_per_10000_km"] = brand_table["failure_count"] / brand_table["observed_km"] * 10000
write_csv(brand_table.sort_values("raw_failure_rate", ascending=False), TABLES / "brand_failure_audit_v1_2.csv")

model_table = audit.groupby(["brand", "model_id", "model_name"], observed=False).agg(
    motorcycle_count=("motorcycle_id", "nunique"), service_count=("service_id", "nunique"),
    failure_count=("failure", "sum"), expected_failures=("failure_hazard_score", "sum"),
).reset_index()
model_table["failure_rate"] = model_table["failure_count"] / model_table["service_count"]
model_table["observed_expected_ratio"] = (model_table["failure_count"] + 15 * pooled) / (model_table["expected_failures"] + 15 * pooled)
write_csv(model_table.sort_values("failure_rate", ascending=False), TABLES / "model_failure_audit_v1_2.csv")

def rate_table(group: str) -> pd.DataFrame:
    return audit.groupby(group, observed=False).agg(service_count=("service_id", "size"), failure_count=("failure", "sum")).assign(failure_rate=lambda d: d.failure_count / d.service_count).reset_index()

age_rates = rate_table("age_bucket")
km_rates = rate_table("km_bucket")
usage_rates = rate_table("usage_type")
intensity_rates = rate_table("riding_intensity")
load_rates = rate_table(pd.cut(audit["load_severity_factor"], [-np.inf, .95, 1.05, 1.15, np.inf], labels=["<0.95", "0.95–1.05", "1.05–1.15", "1.15+"]).rename("load_band"))
overdue_rates = rate_table("overdue_bucket")
annual_rates = rate_table("annual_km_band")
warranty = audit.copy()
warranty["registration_age"] = (warranty["received_at"] - pd.to_datetime(warranty["first_registration_date"])).dt.days / 365.25
warranty["warranty_age_bucket"] = pd.cut(warranty["registration_age"], [-np.inf, 2, 5, 8, np.inf], labels=["0–2", "3–5", "6–8", "9+"])
warranty_rates = warranty.groupby("warranty_age_bucket", observed=False).agg(service_count=("service_id", "size"), warranty_count=("is_warranty_v12", "sum")).assign(warranty_rate=lambda d: d.warranty_count / d.service_count).reset_index()
component_rates = audit[audit["failure"].eq(1)].groupby("primary_fault_component").size().rename("failure_count").reset_index()
final_drive_count = int(component_rates.loc[component_rates["primary_fault_component"].eq("FINAL_DRIVE"), "failure_count"].sum())
repeat_failure = audit.groupby("motorcycle_id")["failure"].sum()

big = brand_table.query("service_count >= 300")
adjusted_ratio = float(big["adjusted_failure_rate"].max() / big["adjusted_failure_rate"].min())
brand_adj = brand_table.set_index("brand")["adjusted_failure_rate"].to_dict()
honda_km = audit.groupby(["brand", "km_bucket"], observed=False).agg(n=("service_id", "size"), rate=("failure", "mean")).reset_index()
honda_wins = 0; honda_comparisons = 0
for bucket in audit["km_bucket"].cat.categories:
    h = honda_km[(honda_km.brand == "Honda") & (honda_km.km_bucket == bucket)]
    for other in ["RKS", "Mondial", "Kuba"]:
        o = honda_km[(honda_km.brand == other) & (honda_km.km_bucket == bucket)]
        if len(h) and len(o) and h.iloc[0].n >= 30 and o.iloc[0].n >= 30:
            honda_comparisons += 1
            honda_wins += int(h.iloc[0].rate > o.iloc[0].rate)

failure_ids = set(services.loc[failure_mask, "service_id"])
primary_fault_coverage = tasks[tasks["task_role"].eq("PRIMARY_FAULT")]["service_id"].nunique()
failure_without_primary = len(failure_ids - set(tasks.loc[tasks["task_role"].eq("PRIMARY_FAULT"), "service_id"]))
fault_tax = set(taxonomy.loc[taxonomy["is_fault_based"].eq(1), "task_code"])
failure_without_fault = sum(not bool(set(group) & fault_tax) for _, group in tasks[tasks["service_id"].isin(failure_ids)].groupby("service_id")["task_code"])

def monotonic_non_decreasing(values: list[float], tolerance: float = .002) -> bool:
    return all(b + tolerance >= a for a, b in zip(values, values[1:]))

def monotonic_non_increasing(values: list[float], tolerance: float = .001) -> bool:
    return all(b <= a + tolerance for a, b in zip(values, values[1:]))

intensity_map = intensity_rates.set_index("riding_intensity")["failure_rate"]
load_values = load_rates["failure_rate"].fillna(0).tolist()
overdue_values = overdue_rates.loc[overdue_rates["service_count"].ge(30), "failure_rate"].tolist()
warranty_values = warranty_rates["warranty_rate"].fillna(0).tolist()

# ---------------------------------------------------------------------------
# Quality and critical release gates.
# ---------------------------------------------------------------------------
all_source = {Path(k).stem: v for k, v in source.items()}
all_derived = {"service_status_history": status_history, "noise_audit": noise, "ml_maintenance_snapshots": snapshots, "ml_next_service_targets": next_service, "ml_next_task_targets": next_task, "split_manifest": split}
checks = []
duplicate_rows = {name: int(df.duplicated().sum()) for name, df in {**all_source, **all_derived}.items()}
checks.append(check("full_row_duplicates", "HIGH", sum(duplicate_rows.values()), duplicate_rows, "No full-row duplicates are present."))
pk_map = {"workshops": "workshop_id", "customers": "customer_id", "motorcycles": "motorcycle_id", "ridebase_motorcycle_models_v1": "model_id", "usage_profiles": "usage_profile_id", "mileage_timeline_monthly": "timeline_id", "maintenance_tasks": "task_code", "maintenance_policies": "policy_id", "appointments": "appointment_id", "services": "service_id", "services_enriched": "service_id", "service_tasks": "service_task_id", "service_parts": "service_part_id", "service_status_history": "status_history_id", "noise_audit": "noise_audit_id", "ml_maintenance_snapshots": "snapshot_id", "ml_next_service_targets": "snapshot_id", "ml_next_task_targets": "snapshot_id", "split_manifest": "snapshot_id"}
pk_bad = {n: int(d[pk_map[n]].duplicated().sum()) for n, d in {**all_source, **all_derived}.items() if n in pk_map}
checks.append(check("primary_key_duplicates", "HIGH", sum(pk_bad.values()), pk_bad, "All primary keys are unique."))

def orphan(child, fk, parent, pk):
    return int((child[fk].notna() & ~child[fk].isin(parent[pk])).sum())

fk = {
    "motorcycle_customer": orphan(motorcycles, "customer_id", source["customers.csv"], "customer_id"),
    "service_motorcycle": orphan(services, "motorcycle_id", motorcycles, "motorcycle_id"),
    "service_customer": orphan(services, "customer_id", source["customers.csv"], "customer_id"),
    "service_workshop": orphan(services, "workshop_id", source["workshops.csv"], "workshop_id"),
    "service_appointment": orphan(services, "appointment_id", source["appointments.csv"], "appointment_id"),
    "task_service": orphan(tasks, "service_id", services, "service_id"), "task_taxonomy": orphan(tasks, "task_code", taxonomy, "task_code"),
    "part_service": orphan(source["service_parts.csv"], "service_id", services, "service_id"),
    "part_task": orphan(source["service_parts.csv"], "service_task_id", tasks, "service_task_id"),
    "status_service": orphan(status_history, "service_id", services, "service_id"),
}
checks.append(check("foreign_key_orphans", "HIGH", sum(fk.values()), fk, "All required foreign keys resolve."))
timeline = status_history.assign(status_at=lambda d: pd.to_datetime(d.status_at, errors="coerce")).sort_values(["service_id", "status_sequence", "status_at"])
backwards = int((timeline.groupby("service_id")["status_at"].diff() < pd.Timedelta(0)).sum())
checks.append(check("canonical_timeline_monotonicity", "HIGH", backwards, {"backwards_events": backwards}, "Canonical service timelines are monotonic."))
task_completed_bad = int((tasks["status"].eq("COMPLETED") & (tasks["completed"].ne(1) | tasks["completed_at"].isna())).sum())
task_declined_bad = int((tasks["status"].eq("DECLINED") & (tasks["completed"].ne(0) | tasks["completed_at"].notna())).sum())
checks.append(check("service_task_status_consistency", "HIGH", task_completed_bad + task_declined_bad, {"completed_bad": task_completed_bad, "declined_bad": task_declined_bad}, "Task completion fields match task status."))
mileage_check = mileage.assign(period_start_date=lambda d: pd.to_datetime(d.period_start_date, errors="coerce")).sort_values(["motorcycle_id", "period_start_date"])
mileage_regressions = int((mileage_check.groupby("motorcycle_id")["closing_odometer_km"].diff() < 0).sum())
checks.append(check("mileage_monotonicity", "HIGH", mileage_regressions, {"regressions": mileage_regressions}, "Monthly odometer is monotonic."))
parts = source["service_parts.csv"]
part_incompatible = int(parts["is_compatible"].ne(1).sum())
purchase_bad = int((~np.isclose(parts["purchase_total"], parts["quantity"] * parts["unit_purchase_price"], atol=.01)).sum())
sale_bad = int((~np.isclose(parts["sale_total"], parts["quantity"] * parts["unit_sale_price"], atol=.01)).sum())
checks.append(check("service_part_compatibility", "HIGH", part_incompatible, {"incompatible_rows": part_incompatible}, "Installed service parts remain compatible."))
checks.append(check("service_part_cost_arithmetic", "HIGH", purchase_bad + sale_bad, {"purchase_mismatch": purchase_bad, "sale_mismatch": sale_bad}, "Part cost arithmetic reconciles."))
appointments = source["appointments.csv"]
converted_bad = int((appointments["status"].eq("CONVERTED_TO_SERVICE") & appointments["service_id"].isna()).sum())
nonservice_bad = int((appointments["status"].isin(["CANCELLED", "NO_SHOW", "RESCHEDULED"]) & appointments["service_id"].notna()).sum())
checks.append(check("appointment_lifecycle_validity", "HIGH", converted_bad + nonservice_bad, {"converted_without_service": converted_bad, "nonconverted_with_service": nonservice_bad}, "Appointment lifecycle semantics remain valid."))
parquet_info = {}
for path in sorted(DER.glob("*.parquet")):
    table = pq.read_table(path); parquet_info[path.name] = {"rows": table.num_rows, "columns": table.num_columns}
checks.append(check("parquet_readability", "HIGH", 0, parquet_info, "All Parquets are readable with pyarrow."))
key_diff = len(set(snapshots.snapshot_id) ^ set(next_service.snapshot_id)) + len(set(snapshots.snapshot_id) ^ set(next_task.snapshot_id))
checks.append(check("snapshot_target_alignment", "HIGH", key_diff, {"key_difference": key_diff}, "Snapshot and target keys align exactly."))
censored_bad = int(next_service.loc[next_service.target_event_observed.eq(0), [c for c in next_service if c.startswith("next_service_")]].notna().sum().sum())
task_censored_bad = int(next_task.loc[next_task.target_event_observed.eq(0), [c for c in next_task if c.startswith("task__")]].notna().sum().sum())
checks.append(check("censored_null_semantics", "HIGH", censored_bad + task_censored_bad, {"next_service_nonnull": censored_bad, "next_task_nonnull": task_censored_bad}, "Censored targets remain NULL."))
task_label_columns = [c for c in next_task if c.startswith("task__")]
minus_one_sentinels = int((next_task[task_label_columns] == -1).sum().sum())
empty_string_cells = 0
for frame in [snapshots, next_service, next_task]:
    for col in frame.select_dtypes(include=["object", "string"]).columns:
        empty_string_cells += int(frame[col].astype("string").str.strip().eq("").fillna(False).sum())
checks.append(check("parquet_null_sentinel_semantics", "HIGH", minus_one_sentinels + empty_string_cells, {"minus_one_task_labels": minus_one_sentinels, "empty_string_cells": empty_string_cells}, "Parquet missing values do not use -1 or empty-string sentinels."))
split_boundary_bad = int((split["boundary_crossing_future_target"].eq(1) & (split["task_target_eligible_primary"].eq(1) | split["next_service_regression_eligible_primary"].eq(1))).sum())
checks.append(check("split_leakage", "HIGH", split_boundary_bad, {"boundary_eligibility_violations": split_boundary_bad}, "Boundary-crossing future targets are ineligible."))
checks.append(check("warranty_monotonicity", "HIGH", 0 if monotonic_non_increasing(warranty_values) else 1, {"rates": warranty_rates.set_index("warranty_age_bucket")["warranty_rate"].fillna(0).to_dict()}, "Warranty generally falls with registration age."))
checks.append(check("riding_intensity_direction", "HIGH", 0 if intensity_map.get("LOW", 0) <= intensity_map.get("MEDIUM", 1) <= intensity_map.get("HIGH", 1) else 1, {"rates": intensity_map.to_dict()}, "LOW <= MEDIUM <= HIGH failure risk."))
checks.append(check("load_failure_direction", "HIGH", 0 if monotonic_non_decreasing(load_values) else 1, {"rates": load_rates.set_index("load_band")["failure_rate"].to_dict()}, "Load severity does not show a strong inverse pattern."))
checks.append(check("maintenance_overdue_direction", "HIGH", 0 if monotonic_non_decreasing(overdue_values, .004) else 1, {"rates": overdue_rates.set_index("overdue_bucket")["failure_rate"].to_dict()}, "Overdue maintenance has a non-decreasing general risk trend."))
checks.append(check("fault_task_coverage", "HIGH", failure_without_primary + failure_without_fault, {"failure_services": len(failure_ids), "primary_fault_covered": primary_fault_coverage, "without_primary": failure_without_primary, "without_fault_task": failure_without_fault}, "Every failure service has a primary fault-based task."))
checks.append(check("final_drive_fault_presence", "HIGH", 0 if final_drive_count > 0 else 1, {"final_drive_failure_count": final_drive_count}, "FINAL_DRIVE fault channel is present."))
checks.append(check("brand_adjusted_spread", "HIGH", 0 if adjusted_ratio <= 1.35 else 1, {"adjusted_max_min_ratio": adjusted_ratio}, "Adjusted big-brand spread is <= 1.35x."))
checks.append(check("honda_same_km_bias", "HIGH", 0 if honda_wins < honda_comparisons else 1, {"honda_higher": honda_wins, "comparisons": honda_comparisons}, "Honda is not higher in every same-km comparison."))
failure_delay_nonnull = int(services.loc[failure_mask, "service_delay_days"].notna().sum())
checks.append(check("failure_service_delay_semantics", "HIGH", failure_delay_nonnull, {"failure_nonnull_delay": failure_delay_nonnull}, "Failure services do not carry fake planned-maintenance delay zeroes."))
overall_rate = float(failure_mask.mean())
checks.append(check("overall_failure_rate_band", "HIGH", 0 if .04 <= overall_rate <= .07 else 1, {"overall_failure_rate": overall_rate}, "Overall failure rate remains in the broad realism band."))
version_bad = sum(int(d["generator_version"].ne(VERSION).sum()) for d in {**all_source, **all_derived}.values() if "generator_version" in d)
checks.append(check("version_provenance", "HIGH", version_bad, {"non_v1_2_rows": version_bad}, "Generator version is 1.2.0."))

high_failures = [c["check"] for c in checks if c["severity"] == "HIGH" and c["status"] == "FAIL"]
release_gate = "PASS" if not high_failures else "FAIL"
quality_report = {
    "report": {"name": "RideBase Synthetic Dataset v1.2 Quality Report", "dataset_version": VERSION, "report_version": "QUALITY_REPORT_V1_2", "report_date": str(HORIZON.date()), "random_seed": SEED, "release_gate": release_gate},
    "executive_summary": {"total_checks": len(checks), "pass_checks": sum(c["status"] == "PASS" for c in checks), "fail_checks": sum(c["status"] == "FAIL" for c in checks), "failed_high_severity_checks": high_failures},
    "reliability_realism_checks": {c["check"]: {"status": c["status"], **c["metrics"]} for c in checks if c["check"] in {"brand_adjusted_spread", "warranty_monotonicity", "riding_intensity_direction", "load_failure_direction", "maintenance_overdue_direction", "fault_task_coverage", "final_drive_fault_presence", "honda_same_km_bias"}},
    "quality_checks": checks,
}
write_json(quality_report, DER / "quality_report.json")

v11_services = v11_source["services.csv"]
v11_tasks = v11_source["service_tasks.csv"]
changed_services = int((services.set_index("service_id")["service_type_code"] != v11_services.set_index("service_id")["service_type_code"]).sum())
changes = {
    "dataset_version": VERSION, "random_seed": SEED,
    "usage_profiles_changed": int((usage.set_index("motorcycle_id")["usage_type"] != v11_source["usage_profiles.csv"].set_index("motorcycle_id")["usage_type"]).sum()),
    "services_regenerated": True, "service_rows_changed": changed_services,
    "repair_count_before": int(v11_services.service_type_code.eq("REPAIR").sum()), "repair_count_after": int(services.service_type_code.eq("REPAIR").sum()),
    "breakdown_count_before": int(v11_services.service_type_code.eq("BREAKDOWN").sum()), "breakdown_count_after": int(services.service_type_code.eq("BREAKDOWN").sum()),
    "warranty_rows_changed": int((services.set_index("service_id")["is_warranty"] != v11_services.set_index("service_id")["is_warranty"]).sum()),
    "service_delay_semantic_changes": int(v11_services.set_index("service_id").loc[list(failure_ids), "service_delay_days"].notna().sum()),
    "overdue_fields_added": ["maintenance_overdue_days_pre_service", "maintenance_overdue_km_pre_service", "overdue_maintenance_days_at_failure", "overdue_maintenance_km_at_failure"],
    "task_rows_before": len(v11_tasks), "task_rows_after": len(tasks), "task_rows_added": len(new_tasks), "task_role_added": True,
    "final_drive_failure_tasks_added": final_drive_count,
    "brand_risk_coefficients_range": [min(brand_residual.values()), max(brand_residual.values())],
    "model_residual_coefficients_range": [min(model_residual.values()), max(model_residual.values())],
    "chronic_risk_distribution": motorcycles.chronic_risk_tier.value_counts().to_dict(),
    "derived_files_regenerated": ["service_status_history.csv", "noise_audit.csv", "ml_maintenance_snapshots.parquet", "ml_next_service_targets.parquet", "ml_next_task_targets.parquet", "split_manifest.csv", "dataset_metadata.json", "quality_report.json"],
}
write_json(changes, REP / "v1_1_to_v1_2_changes.json")

def md_table(df: pd.DataFrame, percent_cols: set[str] | None = None) -> str:
    percent_cols = percent_cols or set()
    show = df.copy()
    for col in percent_cols & set(show.columns):
        show[col] = show[col].map(lambda x: f"{x:.2%}" if pd.notna(x) else "NULL")
    return show.to_markdown(index=False)

audit_md = f"""# RideBase Synthetic Dataset v1.2 — Reliability Realism Audit

**Kapsam:** Generator iç gerçekçiliği; gerçek marka güvenilirliği iddiası değildir. Failure = `REPAIR` veya `BREAKDOWN`.

- Motosiklet: **{len(motorcycles):,}**
- Servis: **{len(services):,}**
- REPAIR: **{services.service_type_code.eq('REPAIR').sum():,}**
- BREAKDOWN: **{services.service_type_code.eq('BREAKDOWN').sum():,}**
- Overall failure: **{overall_rate:.2%}**
- Adjusted big-brand max/min: **{adjusted_ratio:.3f}x**
- Release gate: **{release_gate}**

## 1. Raw ve adjusted marka failure oranları

{md_table(brand_table[['brand','motorcycle_count','service_count','failure_count','raw_failure_rate','adjusted_failure_rate','observed_expected_ratio']], {'raw_failure_rate','adjusted_failure_rate'})}

## 2. 10.000 km başına failure

{md_table(brand_table[['brand','observed_km','failure_count','failure_events_per_10000_km']])}

## 3. Model observed/expected

Minimum karşılaştırma desteği: 50 motosiklet ve 150 servis.

{md_table(model_table.query('motorcycle_count >= 50 and service_count >= 150')[['brand','model_name','motorcycle_count','service_count','failure_count','failure_rate','observed_expected_ratio']].sort_values('observed_expected_ratio', ascending=False), {'failure_rate'})}

## 4. Failure by age

{md_table(age_rates, {'failure_rate'})}

## 5. Failure by odometer band

{md_table(km_rates, {'failure_rate'})}

## 6. Failure by usage type

{md_table(usage_rates, {'failure_rate'})}

## 7. Riding intensity

{md_table(intensity_rates, {'failure_rate'})}

## 8. Load severity

{md_table(load_rates, {'failure_rate'})}

## 9. Annual km exposure

{md_table(annual_rates, {'failure_rate'})}

## 10. Overdue maintenance

{md_table(overdue_rates, {'failure_rate'})}

## 11. Warranty by registration age

{md_table(warranty_rates, {'warranty_rate'})}

## 12. Repeat failure

- En az bir failure yaşayan motosiklet: **{int((repeat_failure >= 1).sum()):,}**
- Tekrar failure yaşayan motosiklet: **{int((repeat_failure >= 2).sum()):,}**
- 3+ failure: **{int((repeat_failure >= 3).sum()):,}**

## 13. Fault component distribution

{md_table(component_rates.sort_values('failure_count', ascending=False))}

## 14. FINAL_DRIVE

- FINAL_DRIVE failure event: **{final_drive_count:,}**
- Failure service primary fault task coverage: **{primary_fault_coverage:,}/{len(failure_ids):,}**

## 15. Declined task rates

- Tüm task decline: **{tasks.status.eq('DECLINED').mean():.2%}**
- ENGINE_OIL_CHANGE decline: **{tasks.loc[tasks.task_code.eq('ENGINE_OIL_CHANGE'), 'status'].eq('DECLINED').mean():.2%}**

## 16. Honda vs RKS/Mondial/Kuba

- Honda adjusted: **{brand_adj.get('Honda', math.nan):.2%}**
- RKS adjusted: **{brand_adj.get('RKS', math.nan):.2%}**
- Mondial adjusted: **{brand_adj.get('Mondial', math.nan):.2%}**
- Kuba adjusted: **{brand_adj.get('Kuba', math.nan):.2%}**
- Aynı-km karşılaştırmalarında Honda daha yüksek: **{honda_wins}/{honda_comparisons}** (v1.1: 15/15)

## Gate sonucu

**{release_gate}** — başarısız yüksek önem kontrolleri: {high_failures or 'yok'}
"""
(REP / "reliability_realism_audit_v1_2.md").write_text(audit_md, encoding="utf-8")

v11_brand = read_csv(V11 / "reports/tables/brand_failure_audit.csv")
v11_adj = {"Honda": .0575, "RKS": .0557, "Mondial": .0393, "Kuba": .0404}
comparison_md = f"""# RideBase v1.1 → v1.2 Reliability Comparison

| Metrik | v1.1 | v1.2 |
|---|---:|---:|
| Overall failure rate | 5.18% | {overall_rate:.2%} |
| Adjusted max/min ratio (büyük markalar) | 1.83x | {adjusted_ratio:.3f}x |
| Honda adjusted | {v11_adj['Honda']:.2%} | {brand_adj.get('Honda', math.nan):.2%} |
| RKS adjusted | {v11_adj['RKS']:.2%} | {brand_adj.get('RKS', math.nan):.2%} |
| Mondial adjusted | {v11_adj['Mondial']:.2%} | {brand_adj.get('Mondial', math.nan):.2%} |
| Kuba adjusted | {v11_adj['Kuba']:.2%} | {brand_adj.get('Kuba', math.nan):.2%} |
| Honda same-km higher | 15/15 | {honda_wins}/{honda_comparisons} |
| FINAL_DRIVE fault count | 0 | {final_drive_count} |
| Failure service delay non-NULL | 2,152 | {failure_delay_nonnull} |
| Failure fault-task coverage | eksik | {primary_fault_coverage}/{len(failure_ids)} |

## Riding intensity

{md_table(intensity_rates, {'failure_rate'})}

## Load severity

{md_table(load_rates, {'failure_rate'})}

## Warranty age trend

{md_table(warranty_rates, {'warranty_rate'})}

## Overdue maintenance trend

{md_table(overdue_rates, {'failure_rate'})}

## Raw brand rates side-by-side

{md_table(v11_brand[['brand','raw_failure_service_rate']].merge(brand_table[['brand','raw_failure_rate','adjusted_failure_rate']], on='brand', how='outer'), {'raw_failure_service_rate','raw_failure_rate','adjusted_failure_rate'})}
"""
(REP / "v1_1_to_v1_2_reliability_comparison.md").write_text(comparison_md, encoding="utf-8")

metadata = json.loads((V11 / "derived_outputs/dataset_metadata.json").read_text(encoding="utf-8"))
metadata["dataset"] = {**metadata.get("dataset", {}), "dataset_version": VERSION, "generator_version": VERSION, "rule_set_version": VERSION, "status": f"V1_2_RELEASE_{release_gate}", "random_seed": SEED}
metadata["failure_generation_model"] = {
    "method": "hazard-based service-event windows", "age_exposure": True, "km_exposure": True,
    "usage_severity": True, "maintenance_overdue": True, "previous_failure_history": True,
    "bounded_brand_residual": [min(brand_residual.values()), max(brand_residual.values())],
    "bounded_model_residual": [min(model_residual.values()), max(model_residual.values())],
    "warranty_eligibility": "registration date + synthetic months + odometer limit",
    "component_fault_selection": "powertrain/category/age/km/usage conditioned", "random_seed": SEED,
}
metadata["changelog_summary"] = changes
metadata["file_catalog"] = []
for path in sorted(list(SRC.glob("*")) + [p for p in DER.glob("*") if p.name != "dataset_metadata.json"]):
    item = {"file_name": path.name, "layer": "SOURCE" if path.parent == SRC else "DERIVED_OUTPUT", "format": path.suffix.lstrip(".").upper(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
    if path.suffix == ".csv": item.update(row_count=len(read_csv(path)), column_count=len(read_csv(path).columns))
    elif path.suffix == ".parquet":
        t = pq.read_table(path); item.update(row_count=t.num_rows, column_count=t.num_columns)
    metadata["file_catalog"].append(item)
write_json(metadata, DER / "dataset_metadata.json")

# ZIP exactly the required directories and test every member.
with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for directory in [SRC, DER, REP]:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(str(path.relative_to(OUT)), date_time=(2026, 8, 25, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
with zipfile.ZipFile(ZIP_PATH, "r") as archive:
    bad = archive.testzip()
    if bad is not None: raise RuntimeError(f"ZIP integrity failure: {bad}")
zip_sha = sha256_file(ZIP_PATH)
(REP / "ridebase_synthetic_dataset_v1_2.sha256").write_text(f"{zip_sha}  {ZIP_PATH.name}\n", encoding="utf-8")

result = {
    "release_gate": release_gate, "failed_high_checks": high_failures, "services": len(services),
    "repair": int(services.service_type_code.eq("REPAIR").sum()), "breakdown": int(services.service_type_code.eq("BREAKDOWN").sum()),
    "overall_failure_rate": overall_rate, "adjusted_brand_rates": brand_adj, "adjusted_max_min_ratio": adjusted_ratio,
    "honda_same_km": f"{honda_wins}/{honda_comparisons}", "riding_intensity": intensity_map.to_dict(),
    "load_severity": load_rates.set_index("load_band")["failure_rate"].to_dict(),
    "overdue": overdue_rates.set_index("overdue_bucket")["failure_rate"].to_dict(),
    "warranty": warranty_rates.set_index("warranty_age_bucket")["warranty_rate"].to_dict(),
    "final_drive_fault_count": final_drive_count, "fault_task_coverage": f"{primary_fault_coverage}/{len(failure_ids)}",
    "changed_service_rows": changed_services, "task_rows_before": len(v11_tasks), "task_rows_after": len(tasks),
    "zip_path": str(ZIP_PATH), "sha256": zip_sha,
}
write_json(result, REP / "release_summary.json")
print(json.dumps(result, ensure_ascii=False, indent=2))
