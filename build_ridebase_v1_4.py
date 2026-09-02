#!/usr/bin/env python3
"""Build RideBase synthetic source release v1.4 without changing source schema.

V1.3 is an immutable parent.  V1.4 preserves every parent source row and extends
the observation tail with stochastic service/appointment/task events.  Generator
state (maintenance pressure, adherence, frailty, capacity and hazards) never
becomes a source column.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
PARENT = ROOT / "ridebase_v1_3"
DEFAULT_OUTPUT = ROOT / "ridebase_v1_4"
CONTRACT = ROOT / "ridebase-ml" / "config" / "source_schema_contract_v1_3.json"
VERSION = "1.4.0"
PARENT_VERSION = "1.3.0"
SOURCE_SCHEMA_VERSION = "1.3.0"
EXPERIMENT = "V2_1_BEHAVIORAL_SERVICE_RETURN"
SEED = 42
HORIZON = pd.Timestamp("2026-08-25 23:59:59")
STEP_DAYS = 7


def stable_unit(*parts: object, salt: str = "") -> float:
    raw = ":".join([str(SEED), salt, *map(str, parts)]).encode()
    return int(hashlib.sha256(raw).hexdigest()[:15], 16) / float(16**15)


def stable_normal(*parts: object, salt: str = "") -> float:
    u1 = max(stable_unit(*parts, salt=salt + "-u1"), 1e-12)
    u2 = stable_unit(*parts, salt=salt + "-u2")
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-float(np.clip(x, -30.0, 30.0))))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default) + "\n")


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)): return bool(value)
    if isinstance(value, pd.Timestamp): return value.isoformat()
    raise TypeError(type(value).__name__)


class MileageLookup:
    def __init__(self, frame: pd.DataFrame):
        self.groups = {}
        frame = frame.copy()
        frame["period_start_date"] = pd.to_datetime(frame["period_start_date"])
        frame["period_end_date"] = pd.to_datetime(frame["period_end_date"])
        for key, group in frame.groupby("motorcycle_id", sort=False):
            self.groups[key] = group.sort_values("period_start_date")

    def odometer(self, motorcycle_id: str, when: pd.Timestamp) -> float:
        group = self.groups[motorcycle_id]
        hit = group.loc[(group.period_start_date <= when.normalize()) & (group.period_end_date >= when.normalize())]
        if hit.empty:
            if when < group.period_start_date.min(): return float(group.iloc[0].opening_odometer_km)
            return float(group.iloc[-1].closing_odometer_km)
        row = hit.iloc[0]
        span = max((row.period_end_date - row.period_start_date).days + 1, 1)
        fraction = np.clip(((when.normalize() - row.period_start_date).days + 0.5) / span, 0.0, 1.0)
        return float(row.opening_odometer_km + fraction * (row.closing_odometer_km - row.opening_odometer_km))


def primary_policies(models: pd.DataFrame, policies: pd.DataFrame) -> dict[str, dict[str, Any]]:
    active = policies.loc[
        policies["is_generator_active"].eq(1) & policies["policy_kind"].eq("SCHEDULED")
    ].copy()
    result: dict[str, dict[str, Any]] = {}
    for model in models.to_dict("records"):
        candidates = active.loc[
            ((active.scope_type == "MODEL") & (active.model_id == model["model_id"]))
            | ((active.scope_type == "GROUP") & (active.policy_group == model["policy_group"]))
        ].copy()
        preferred = "ENGINE_OIL_CHANGE" if model["powertrain_type"] == "ICE" else "GENERAL_SAFETY_INSPECTION"
        chosen = candidates.loc[candidates.task_code.eq(preferred)]
        if chosen.empty:
            chosen = candidates.loc[candidates.recurring_km.notna() | candidates.recurring_months.notna()]
        if chosen.empty:
            result[model["model_id"]] = {
                "policy_id": None, "task_code": preferred, "days": 365.25, "km": 6000.0,
            }
            continue
        chosen = chosen.assign(scope_rank=chosen.scope_type.eq("MODEL").astype(int)).sort_values(
            ["scope_rank", "precedence"], ascending=[False, True]
        ).iloc[0]
        months = chosen.recurring_months if pd.notna(chosen.recurring_months) else chosen.initial_trigger_months
        km = chosen.recurring_km if pd.notna(chosen.recurring_km) else chosen.initial_trigger_km
        result[model["model_id"]] = {
            "policy_id": chosen.policy_id,
            "task_code": chosen.task_code,
            "days": float(months * 30.4375) if pd.notna(months) else 365.25,
            "km": float(km) if pd.notna(km) else 6000.0,
        }
    return result


def behavior_state(customer: pd.Series, usage: pd.Series, old_services: pd.DataFrame) -> dict[str, Any]:
    delays = pd.to_numeric(old_services.loc[old_services.service_type_code.eq("PERIODIC"), "service_delay_days"], errors="coerce")
    historical_delay = float(delays.median()) if delays.notna().any() else 0.0
    customer_type = str(customer.customer_type)
    usage_type = str(usage.usage_type)
    base = 0.0
    if customer_type in {"FLEET", "CORPORATE"} or bool(customer.is_fleet_customer): base += 0.35
    if usage_type == "COURIER": base += 0.18
    if historical_delay > 30: base -= 0.55
    elif historical_delay > 7: base -= 0.25
    customer_id = str(customer.name)
    base += 0.32 * stable_normal(customer_id, salt="adherence")
    adherence = sigmoid(base)
    if adherence >= 0.60: label = "REGULAR"
    elif adherence >= 0.42: label = "SLIGHTLY_LATE"
    else: label = "IRREGULAR"
    return {
        "adherence": adherence,
        "label": label,
        "frailty": float(np.clip(math.exp(0.38 * stable_normal(customer_id, salt="frailty")), 0.45, 2.1)),
        "appointment_propensity": float(np.clip(0.50 + 0.42 * adherence + 0.08 * stable_normal(customer_id, salt="appointment"), 0.25, 0.96)),
    }


def weekly_hazards(
    when: pd.Timestamp,
    days_ratio: float,
    km_ratio: float,
    behavior: dict[str, Any],
    usage: pd.Series,
    motorcycle: pd.Series,
    workshop: pd.Series,
) -> dict[str, float]:
    pressure = max(days_ratio, km_ratio)
    # Smooth accumulation: due pressure matters strongly but never implies certainty.
    periodic = (
        0.0015
        + 0.009 * sigmoid(8.0 * (pressure - 0.62))
        + 0.045 * sigmoid(8.0 * (pressure - 0.98))
        + 0.040 * sigmoid(4.0 * (pressure - 1.55))
    )
    adherence_multiplier = 0.48 + 1.05 * behavior["adherence"]
    month_wave = 0.84 + 0.18 * math.cos(2 * math.pi * (when.month - 5) / 12.0)
    capacity = float(np.clip(0.70 + 0.035 * float(workshop.service_bay_count), 0.75, 1.15))
    periodic *= adherence_multiplier * behavior["frailty"] * month_wave * capacity

    annual_km = float(usage.annual_km_baseline)
    age_years = max((when - pd.Timestamp(motorcycle.first_registration_date)).days / 365.25, 0.0)
    severity = float(usage.load_severity_factor)
    breakdown = 0.00035 + 0.00016 * age_years + 0.000000018 * annual_km * max(age_years, 1.0)
    breakdown += 0.0009 * max(severity - 1.0, 0.0) + 0.0008 * sigmoid(3.0 * (pressure - 1.3))
    repair = 0.0009 + 0.00022 * age_years + 0.0007 * max(severity - 0.9, 0.0)
    tire = 0.0004 + 0.032 * sigmoid(7.0 * (km_ratio - 1.55))
    return {
        "PERIODIC": float(np.clip(periodic, 0.0002, 0.18)),
        "BREAKDOWN": float(np.clip(breakdown, 0.0002, 0.025)),
        "REPAIR": float(np.clip(repair, 0.0003, 0.025)),
        "TIRE": float(np.clip(tire, 0.0002, 0.08)),
    }


@dataclass
class IdFactory:
    service: int
    appointment: int
    task: int

    def next_service(self) -> str:
        self.service += 1
        return f"SVC{self.service:06d}"

    def next_appointment(self) -> str:
        self.appointment += 1
        return f"APT{self.appointment:06d}"

    def next_task(self) -> str:
        self.task += 1
        return f"STK{self.task:07d}"


def numeric_suffix(frame: pd.DataFrame, column: str) -> int:
    return int(frame[column].astype(str).str.extract(r"(\d+)$")[0].astype(float).max())


def make_appointment(
    ids: IdFactory, motorcycle: pd.Series, when: pd.Timestamp, event_type: str,
    status: str, service_id: str | None, attempt: int,
) -> dict[str, Any]:
    appointment_id = ids.next_appointment()
    lead = int(1 + 12 * stable_unit(motorcycle.motorcycle_id, when.date(), attempt, salt="appointment-lead"))
    scheduled = when if status == "CONVERTED_TO_SERVICE" else when + pd.Timedelta(days=lead)
    created = scheduled - pd.Timedelta(days=lead, hours=2)
    return {
        "appointment_id": appointment_id, "workshop_id": motorcycle.workshop_id,
        "customer_id": motorcycle.customer_id, "motorcycle_id": motorcycle.motorcycle_id,
        "created_at": created, "scheduled_at": scheduled, "appointment_type": event_type,
        "source": ["MOBILE_APP", "PHONE", "WHATSAPP"][int(stable_unit(appointment_id, salt="source") * 3) % 3],
        "status": status, "service_id": service_id, "customer_request": event_type,
        "data_origin": "SYNTHETIC", "generator_version": VERSION,
    }


def make_service(
    service_id: str, appointment_id: str | None, motorcycle: pd.Series, when: pd.Timestamp,
    odometer: int, event_type: str, policy: dict[str, Any], days_ratio: float, km_ratio: float,
    failure_count: int, failure_hazard: float, task_code: str,
) -> dict[str, Any]:
    failure = event_type in {"BREAKDOWN", "REPAIR"}
    received = when + pd.Timedelta(hours=int(8 + 9 * stable_unit(service_id, salt="hour")))
    duration = int(45 + 210 * stable_unit(service_id, salt="duration"))
    completed = received + pd.Timedelta(minutes=duration)
    delivered = completed + pd.Timedelta(hours=int(1 + 20 * stable_unit(service_id, salt="delivery")))
    overdue_days = max((days_ratio - 1.0) * policy["days"], 0.0)
    overdue_km = max((km_ratio - 1.0) * policy["km"], 0.0)
    labor = round(duration * (7.0 + 3.0 * stable_unit(service_id, salt="labor-rate")), 2)
    # No synthetic part row is invented for an unknown model fitment.  The
    # corresponding service remains labor-only and the existing part catalog
    # relationships stay authoritative.
    parts = 0.0
    subtotal = labor + parts
    tax = round(subtotal * 0.20, 2)
    return {
        "service_id": service_id, "workshop_id": motorcycle.workshop_id,
        "customer_id": motorcycle.customer_id, "motorcycle_id": motorcycle.motorcycle_id,
        "appointment_id": appointment_id, "service_type_code": event_type,
        "primary_trigger_task": task_code,
        "trigger_due_km": odometer - max((km_ratio - 1.0) * policy["km"], 0.0) if event_type == "PERIODIC" else np.nan,
        "trigger_due_date": received - pd.Timedelta(days=overdue_days) if event_type == "PERIODIC" else pd.NaT,
        "service_delay_days": round(overdue_days, 2) if event_type == "PERIODIC" else np.nan,
        "arrival_mode": "APPOINTMENT" if appointment_id else ("TOWED" if event_type == "BREAKDOWN" else "WALK_IN"),
        "received_at": received, "odometer_km": odometer, "mileage_source": "ESTIMATED",
        "mileage_quality_flag": "ESTIMATED", "is_mileage_estimated": 1, "status": "DELIVERED",
        "estimated_delivery_at": received + pd.Timedelta(hours=6), "completed_at": completed,
        "delivered_at": delivered, "customer_complaint": "Sentetik v1.4 olay süreci",
        "technician_notes": np.nan, "labor_minutes_pre_task": duration,
        "labor_total": labor, "parts_total": parts, "discount_total": 0.0,
        "tax_total": tax, "grand_total": round(subtotal + tax, 2),
        "is_breakdown": int(event_type == "BREAKDOWN"), "is_warranty": int(failure and failure_count == 0),
        "capture_origin": "RIDEBASE_WORKSHOP", "data_origin": "SYNTHETIC",
        "generator_version": VERSION, "random_seed": SEED, "scenario_id": EXPERIMENT,
        "maintenance_overdue_days_pre_service": round(overdue_days, 2),
        "maintenance_overdue_km_pre_service": round(overdue_km, 2),
        "overdue_maintenance_days_at_failure": round(overdue_days, 2) if failure else np.nan,
        "overdue_maintenance_km_at_failure": round(overdue_km, 2) if failure else np.nan,
        "previous_failure_count": failure_count, "failure_hazard_score": round(failure_hazard, 6),
        "primary_fault_component": "ENGINE" if failure else np.nan,
        "failure_severity": "HIGH" if event_type == "BREAKDOWN" else ("MEDIUM" if event_type == "REPAIR" else np.nan),
    }


def make_task(task_id: str, service: dict[str, Any], task_catalog: pd.DataFrame, policy_id: str | None) -> dict[str, Any]:
    code = service["primary_trigger_task"]
    hit = task_catalog.loc[task_catalog.task_code.eq(code)]
    if hit.empty:
        hit = task_catalog.loc[task_catalog.task_code.eq("GENERAL_SAFETY_INSPECTION")]
    definition = hit.iloc[0]
    started = pd.Timestamp(service["received_at"]) + pd.Timedelta(minutes=5)
    completed = pd.Timestamp(service["completed_at"])
    return {
        "service_task_id": task_id, "service_id": service["service_id"],
        "motorcycle_id": service["motorcycle_id"], "workshop_id": service["workshop_id"],
        "task_sequence": 1, "task_code": definition.task_code,
        "display_title": definition.canonical_name_tr, "title_variant_type": "CANONICAL",
        "component_group": definition.component_group, "action_type": definition.action_type,
        "trigger_reason": "FAULT" if service["service_type_code"] in {"BREAKDOWN", "REPAIR"} else "MILEAGE_AND_TIME",
        "is_policy_due": int(service["service_type_code"] == "PERIODIC"),
        "policy_id": policy_id if service["service_type_code"] == "PERIODIC" else np.nan,
        "status": "COMPLETED", "completed": 1, "started_at": started, "completed_at": completed,
        "completed_by": f"TECH-{service['workshop_id']}-01", "labor_minutes": service["labor_minutes_pre_task"],
        "labor_cost": service["labor_total"], "labor_cost_basis": "SYNTHETIC_YEAR_X_WORKSHOP_RATE",
        "severity": "HIGH" if service["service_type_code"] == "BREAKDOWN" else "NORMAL",
        "data_origin": "SYNTHETIC", "generator_version": VERSION, "random_seed": SEED,
        "notes": "V1.4 tail event", "task_role": service["service_type_code"],
    }


def extend_event_tail(source: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    services = source["services.csv"].copy()
    services["received_at"] = pd.to_datetime(services.received_at)
    appointments = source["appointments.csv"].copy()
    tasks = source["service_tasks.csv"].copy()
    motorcycles = source["motorcycles.csv"].copy()
    customers = source["customers.csv"].set_index("customer_id")
    usage = source["usage_profiles.csv"].set_index("motorcycle_id")
    workshops = source["workshops.csv"].set_index("workshop_id")
    policies = primary_policies(source["ridebase_motorcycle_models_v1.csv"], source["maintenance_policies.csv"])
    model_groups = source["ridebase_motorcycle_models_v1.csv"].set_index("model_id")["policy_group"].to_dict()
    lookup = MileageLookup(source["mileage_timeline_monthly.csv"])
    task_catalog = source["maintenance_tasks.csv"]
    ids = IdFactory(numeric_suffix(services, "service_id"), numeric_suffix(appointments, "appointment_id"), numeric_suffix(tasks, "service_task_id"))
    existing = {key: group.sort_values("received_at") for key, group in services.groupby("motorcycle_id")}
    new_services: list[dict[str, Any]] = []
    new_appointments: list[dict[str, Any]] = []
    new_tasks: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []

    for motorcycle in motorcycles.itertuples(index=False):
        motorcycle = pd.Series(motorcycle._asdict())
        group = existing.get(motorcycle.motorcycle_id, services.iloc[0:0])
        start = pd.Timestamp(motorcycle.observation_start_date)
        raw_end = pd.to_datetime(motorcycle.observation_end_date, errors="coerce")
        end = HORIZON if pd.isna(raw_end) else min(pd.Timestamp(raw_end) + pd.Timedelta(hours=23, minutes=59), HORIZON)
        if not group.empty:
            last = group.iloc[-1]
            last_at = pd.Timestamp(last.received_at)
            last_odo = float(last.odometer_km)
            failure_count = int(group.service_type_code.isin(["BREAKDOWN", "REPAIR"]).sum())
        else:
            last_at = start
            last_odo = float(motorcycle.initial_mileage_km)
            failure_count = 0
        if last_at >= end - pd.Timedelta(days=STEP_DAYS):
            continue
        customer = customers.loc[motorcycle.customer_id]
        profile = usage.loc[motorcycle.motorcycle_id]
        workshop = workshops.loc[motorcycle.workshop_id]
        behavior = behavior_state(customer, profile, group)
        policy = policies[motorcycle.model_id]
        attempt = 0
        step = 0
        when = (last_at + pd.Timedelta(days=STEP_DAYS)).normalize()
        while when <= end:
            step += 1
            odo = lookup.odometer(motorcycle.motorcycle_id, when)
            days_ratio = max((when - last_at).total_seconds() / 86400.0, 0.0) / max(policy["days"], 1.0)
            km_ratio = max(odo - last_odo, 0.0) / max(policy["km"], 1.0)
            hazards = weekly_hazards(when, days_ratio, km_ratio, behavior, profile, motorcycle, workshop)
            draws = {name: stable_unit(motorcycle.motorcycle_id, when.date(), name, salt="event") for name in hazards}
            event_type = None
            for candidate in ["BREAKDOWN", "REPAIR", "TIRE", "PERIODIC"]:
                if draws[candidate] < hazards[candidate]:
                    event_type = candidate
                    break
            if event_type is None:
                when += pd.Timedelta(days=STEP_DAYS)
                continue

            appointment_id = None
            if event_type != "BREAKDOWN" and stable_unit(motorcycle.motorcycle_id, when.date(), salt="appointment-use") < behavior["appointment_propensity"]:
                attempt += 1
                miss_probability = float(np.clip(0.26 - 0.18 * behavior["adherence"] + 0.04 * stable_unit(motorcycle.workshop_id, when.month, salt="capacity-friction"), 0.05, 0.30))
                if stable_unit(motorcycle.motorcycle_id, when.date(), attempt, salt="appointment-outcome") < miss_probability:
                    status = "NO_SHOW" if stable_unit(motorcycle.motorcycle_id, attempt, salt="miss-kind") < 0.62 else "CANCELLED"
                    new_appointments.append(make_appointment(ids, motorcycle, when, event_type, status, None, attempt))
                    audit.append({
                        "motorcycle_id": motorcycle.motorcycle_id, "event_at": when, "outcome": status,
                        "event_type": event_type, "behavior_group": behavior["label"],
                        "usage_type": profile.usage_type, "policy_group": model_groups.get(motorcycle.model_id, "UNKNOWN"),
                        "days_due_ratio": days_ratio, "km_due_ratio": km_ratio,
                        "max_due_ratio": max(days_ratio, km_ratio), "hazard": hazards[event_type],
                    })
                    when += pd.Timedelta(days=STEP_DAYS)
                    continue
                service_id = ids.next_service()
                appointment = make_appointment(ids, motorcycle, when, event_type, "CONVERTED_TO_SERVICE", service_id, attempt)
                appointment_id = appointment["appointment_id"]
                new_appointments.append(appointment)
            else:
                service_id = ids.next_service()

            service = make_service(
                service_id, appointment_id, motorcycle, when, int(round(odo)), event_type, policy,
                days_ratio, km_ratio, failure_count, hazards["BREAKDOWN"] + hazards["REPAIR"],
                (
                    policy["task_code"] if event_type == "PERIODIC" else
                    "FRONT_TIRE_CHANGE" if event_type == "TIRE" else
                    ["ENGINE_COMPRESSION_TEST", "FUEL_SYSTEM_DIAGNOSTIC", "COOLING_SYSTEM_INSPECTION", "ABS_DIAGNOSTIC"][
                        int(stable_unit(service_id, salt="fault-task") * 4) % 4
                    ]
                ),
            )
            new_services.append(service)
            new_tasks.append(make_task(ids.next_task(), service, task_catalog, policy["policy_id"]))
            audit.append({
                "motorcycle_id": motorcycle.motorcycle_id, "event_at": service["received_at"], "outcome": "SERVICE",
                "event_type": event_type, "behavior_group": behavior["label"], "usage_type": profile.usage_type,
                "policy_group": model_groups.get(motorcycle.model_id, "UNKNOWN"), "days_due_ratio": days_ratio,
                "km_due_ratio": km_ratio, "max_due_ratio": max(days_ratio, km_ratio), "hazard": hazards[event_type],
            })
            if event_type in {"BREAKDOWN", "REPAIR"}: failure_count += 1
            last_at = pd.Timestamp(service["received_at"])
            last_odo = odo
            when = (last_at + pd.Timedelta(days=STEP_DAYS)).normalize()

    if new_services:
        additions = pd.DataFrame(new_services).reindex(columns=services.columns)
        services = pd.concat([services, additions], ignore_index=True).sort_values("service_id")
        tasks = pd.concat([tasks, pd.DataFrame(new_tasks).reindex(columns=tasks.columns)], ignore_index=True).sort_values("service_task_id")
    if new_appointments:
        appointments = pd.concat([appointments, pd.DataFrame(new_appointments).reindex(columns=appointments.columns)], ignore_index=True).sort_values("appointment_id")
    source["services.csv"] = services
    source["appointments.csv"] = appointments
    source["service_tasks.csv"] = tasks

    enriched = source["services_enriched.csv"].copy()
    if new_services:
        extra_columns = [column for column in enriched.columns if column not in services.columns]
        extra = []
        for service in new_services:
            row = {
                "service_id": service["service_id"], "subtotal_before_discount": service["labor_total"] + service["parts_total"],
                "discount_rate": 0.0, "tax_rate": 0.2, "pricing_currency": "TRY",
                "cost_calculation_basis": "V1_4_SYNTHETIC_EVENT", "cost_rule_version": VERSION,
            }
            row.update(service)
            extra.append(row)
        enriched = pd.concat([enriched, pd.DataFrame(extra).reindex(columns=enriched.columns)], ignore_index=True).sort_values("service_id")
    source["services_enriched.csv"] = enriched
    return source, pd.DataFrame(audit)


def source_qa(source: dict[str, pd.DataFrame], contract: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for filename, spec in contract["tables"].items():
        checks[f"schema:{filename}"] = list(source[filename].columns) == spec["ordered_columns"]
        pk = spec["primary_key"]
        checks[f"pk:{filename}"] = not source[filename].duplicated(pk).any() and not source[filename][pk].isna().any().any()
    s, a, t, p = (source[name] for name in ["services.csv", "appointments.csv", "service_tasks.csv", "service_parts.csv"])
    checks.update({
        "fk:service_motorcycle": s.motorcycle_id.isin(source["motorcycles.csv"].motorcycle_id).all(),
        "fk:service_customer": s.customer_id.isin(source["customers.csv"].customer_id).all(),
        "fk:service_workshop": s.workshop_id.isin(source["workshops.csv"].workshop_id).all(),
        "fk:task_service": t.service_id.isin(s.service_id).all(),
        "fk:part_service": p.service_id.isin(s.service_id).all(),
        "fk:appointment_service": a.service_id.dropna().isin(s.service_id).all(),
        "relation:service_appointment": s.appointment_id.dropna().isin(a.appointment_id).all(),
        "relation:service_has_task": s.service_id.isin(t.service_id).all(),
    })
    received = pd.to_datetime(s.received_at)
    completed = pd.to_datetime(s.completed_at)
    delivered = pd.to_datetime(s.delivered_at)
    checks["timestamps:service_order"] = bool(((completed >= received) & (delivered >= completed)).all())
    ordered = s.assign(received_at=received).sort_values(["motorcycle_id", "received_at"])
    checks["odometer:monotonic"] = bool((ordered.groupby("motorcycle_id").odometer_km.diff().fillna(0) >= 0).all())
    motorcycles = source["motorcycles.csv"][["motorcycle_id", "observation_start_date", "observation_end_date"]]
    window = ordered.merge(motorcycles, on="motorcycle_id", how="left")
    window_end = pd.to_datetime(window.observation_end_date, errors="coerce").fillna(HORIZON)
    checks["window:no_future_history"] = bool(
        (window.received_at >= pd.to_datetime(window.observation_start_date)).all()
        and (window.received_at <= window_end + pd.Timedelta(days=1)).all()
    )
    policy_tasks = set(source["maintenance_policies.csv"].task_code)
    checks["policy:mapping"] = set(s.loc[s.service_type_code.eq("PERIODIC"), "primary_trigger_task"].dropna()).issubset(policy_tasks)
    failed = [name for name, passed in checks.items() if not passed]
    return {"status": "PASS" if not failed else "FAIL", "failed": failed, "checks": checks}


def source_hashes(directory: Path) -> dict[str, str]:
    return {path.name: sha256_file(path) for path in sorted((directory / "source_tables").glob("*.csv"))}


def build(output: Path) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    source = {
        filename: pd.read_csv(PARENT / "source_tables" / filename, low_memory=False)
        for filename in contract["tables"]
    }
    parent_hash_before = source_hashes(PARENT)
    source, event_audit = extend_event_tail(source)
    source_dir = output / "source_tables"
    report_dir = output / "reports"
    source_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    for filename, frame in source.items():
        frame.to_csv(source_dir / filename, index=False, encoding="utf-8", lineterminator="\n")
    event_audit.to_csv(report_dir / "v1_4_generator_event_audit.csv", index=False)
    qa = source_qa(source, contract)
    parent_hash_after = source_hashes(PARENT)
    qa["checks"]["frozen:v1_3_hashes"] = parent_hash_before == parent_hash_after
    if parent_hash_before != parent_hash_after:
        qa["status"] = "FAIL"; qa["failed"].append("frozen:v1_3_hashes")
    metadata = {
        "dataset_version": VERSION, "experiment": EXPERIMENT, "parent_dataset": PARENT_VERSION,
        "source_schema_version": SOURCE_SCHEMA_VERSION, "random_seed": SEED,
        "source_schema_changed": False, "parent_hashes": parent_hash_before,
        "source_hashes": source_hashes(output), "new_event_rows": int((event_audit.outcome == "SERVICE").sum()),
        "new_no_show_rows": int((event_audit.outcome == "NO_SHOW").sum()),
        "new_cancel_rows": int((event_audit.outcome == "CANCELLED").sum()),
        "qa": qa,
    }
    write_json(metadata, output / "dataset_metadata.json")
    write_json(qa, report_dir / "source_qa.json")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-reproducibility", action="store_true")
    args = parser.parse_args()
    if args.output.resolve() == PARENT.resolve():
        raise SystemExit("Refusing to overwrite frozen v1.3")
    if args.output.exists():
        shutil.rmtree(args.output)
    metadata = build(args.output)
    if args.verify_reproducibility:
        with tempfile.TemporaryDirectory(prefix="ridebase-v1-4-repro-") as temp:
            second = build(Path(temp) / "ridebase_v1_4")
            reproducible = metadata["source_hashes"] == second["source_hashes"]
        metadata["reproducibility_verified"] = reproducible
        metadata["qa"]["checks"]["reproducibility:source_hashes"] = reproducible
        if not reproducible:
            metadata["qa"]["status"] = "FAIL"
            metadata["qa"]["failed"].append("reproducibility:source_hashes")
        write_json(metadata, args.output / "dataset_metadata.json")
        write_json(metadata["qa"], args.output / "reports" / "source_qa.json")
    print(json.dumps({
        "dataset_version": metadata["dataset_version"], "new_event_rows": metadata["new_event_rows"],
        "new_no_show_rows": metadata["new_no_show_rows"], "new_cancel_rows": metadata["new_cancel_rows"],
        "qa": metadata["qa"]["status"], "reproducibility": metadata.get("reproducibility_verified"),
    }, indent=2))


if __name__ == "__main__":
    main()
