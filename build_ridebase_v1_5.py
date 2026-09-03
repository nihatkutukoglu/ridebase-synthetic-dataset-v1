#!/usr/bin/env python3
"""Build the separate V1.5 synthetic behavior world for the V2.2 challenger.

V1.4 and V2.1 are immutable. V1.5 branches from the same frozen V1.3 core so
the V1.4 and V1.5 tail generators can be compared without stacking synthetic
events. Latent tendencies are written only to an audit trace, never source data.
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

import build_ridebase_v1_4 as v14


ROOT = Path(__file__).resolve().parent
PARENT = ROOT / "ridebase_v1_3"
REFERENCE = ROOT / "ridebase_v1_4"
DEFAULT_OUTPUT = ROOT / "ridebase_v1_5"
CONTRACT = ROOT / "ridebase-ml/config/source_schema_contract_v1_3.json"
VERSION = "1.5.0"
SOURCE_SCHEMA_VERSION = "1.3.0"
EXPERIMENT = "V2_2_BEHAVIORAL_RETURN_CHALLENGER"
SEED = 52
HORIZON = pd.Timestamp("2026-08-25 23:59:59")
STEP_DAYS = 3


def stable_unit(*parts: object, salt: str = "") -> float:
    raw = ":".join([str(SEED), salt, *map(str, parts)]).encode()
    return int(hashlib.sha256(raw).hexdigest()[:15], 16) / float(16**15)


def stable_normal(*parts: object, salt: str = "") -> float:
    u1 = max(stable_unit(*parts, salt=salt + "-u1"), 1e-12)
    u2 = stable_unit(*parts, salt=salt + "-u2")
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-float(np.clip(value, -30.0, 30.0))))


def sha256_file(path: Path) -> str:
    return v14.sha256_file(path)


def write_json(value: Any, path: Path) -> None:
    v14.write_json(value, path)


class MileageLookup:
    """Array-backed interpolation; deterministic and substantially faster than row scans."""

    def __init__(self, frame: pd.DataFrame):
        self.groups: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
        work = frame.copy()
        work["period_start_date"] = pd.to_datetime(work["period_start_date"])
        work["period_end_date"] = pd.to_datetime(work["period_end_date"])
        for key, group in work.groupby("motorcycle_id", sort=False):
            ordered = group.sort_values("period_start_date")
            self.groups[str(key)] = (
                ordered.period_start_date.values.astype("datetime64[D]"),
                ordered.period_end_date.values.astype("datetime64[D]"),
                ordered.opening_odometer_km.to_numpy(float),
                ordered.closing_odometer_km.to_numpy(float),
            )

    def odometer(self, motorcycle_id: str, when: pd.Timestamp) -> float:
        starts, ends, opening, closing = self.groups[str(motorcycle_id)]
        day = when.to_datetime64().astype("datetime64[D]")
        index = int(np.searchsorted(starts, day, side="right") - 1)
        if index < 0:
            return float(opening[0])
        if index >= len(starts) or day > ends[index]:
            return float(closing[-1])
        span = max(int((ends[index] - starts[index]).astype(int)) + 1, 1)
        fraction = float(np.clip((int((day - starts[index]).astype(int)) + 0.5) / span, 0.0, 1.0))
        return float(opening[index] + fraction * (closing[index] - opening[index]))


def behavior_state(
    customer: pd.Series,
    usage: pd.Series,
    old_services: pd.DataFrame,
    old_appointments: pd.DataFrame,
) -> dict[str, Any]:
    periodic = old_services.loc[old_services.service_type_code.eq("PERIODIC")]
    delays = pd.to_numeric(periodic.service_delay_days, errors="coerce")
    mean_delay = float(delays.mean()) if delays.notna().any() else 14.0
    on_time = float((delays.fillna(0) <= 0).mean()) if len(delays) else 0.45
    no_shows = int(old_appointments.status.astype(str).eq("NO_SHOW").sum())
    cancelled = int(old_appointments.status.astype(str).eq("CANCELLED").sum())
    customer_id = str(customer.name)
    annual_km = float(usage.annual_km_baseline)
    fleet = str(customer.customer_type) in {"FLEET", "CORPORATE"} or bool(customer.is_fleet_customer)

    adherence_logit = 0.15 + 1.20 * (on_time - 0.5) - 0.018 * max(mean_delay, 0)
    adherence_logit += 0.35 * fleet + 0.28 * stable_normal(customer_id, salt="adherence")
    adherence = sigmoid(adherence_logit)
    no_show_tendency = sigmoid(-1.55 + 0.38 * no_shows + 0.18 * cancelled - 1.0 * adherence
                               + 0.50 * stable_normal(customer_id, salt="no-show"))
    price_sensitivity = sigmoid(-0.25 + 0.60 * stable_normal(customer_id, salt="price"))
    loyalty = sigmoid(0.30 + 0.55 * fleet + 0.70 * adherence
                      + 0.45 * stable_normal(customer_id, salt="loyalty"))
    churn = sigmoid(-2.45 + 1.20 * no_show_tendency + 0.65 * price_sensitivity
                    - 0.95 * loyalty + 0.50 * stable_normal(customer_id, salt="churn"))
    frailty = float(np.clip(math.exp(0.30 * stable_normal(customer_id, salt="frailty")), 0.52, 1.85))

    # A deterministic mixture guarantees representation of every simulation
    # archetype. The archetype modifies tendencies but never enters source data.
    profile_draw = stable_unit(customer_id, salt="profile-mixture")
    cuts = [
        (.16, "ON_TIME"), (.46, "NORMAL"), (.61, "DELAYER"),
        (.72, "HEAVY_USER"), (.80, "PRICE_SENSITIVE"), (.87, "CHURN_RISK"),
        (.94, "WORKSHOP_LOYAL"), (1.01, "NO_SHOW_PRONE"),
    ]
    profile = next(label for cutoff, label in cuts if profile_draw < cutoff)
    if profile == "ON_TIME":
        adherence = min(0.96, adherence + 0.22); loyalty = min(0.96, loyalty + 0.08)
    elif profile == "DELAYER":
        adherence = max(0.08, adherence - 0.24)
    elif profile == "HEAVY_USER":
        frailty = min(1.85, frailty * 1.12)
    elif profile == "PRICE_SENSITIVE":
        price_sensitivity = min(0.97, price_sensitivity + 0.28); loyalty = max(0.05, loyalty - 0.14)
    elif profile == "CHURN_RISK":
        churn = min(0.94, churn + 0.38); loyalty = max(0.04, loyalty - 0.18)
    elif profile == "WORKSHOP_LOYAL":
        loyalty = min(0.98, loyalty + 0.30); churn = max(0.01, churn - 0.12)
    elif profile == "NO_SHOW_PRONE":
        no_show_tendency = min(0.96, no_show_tendency + 0.42); adherence = max(0.06, adherence - 0.12)
    return {
        "profile": profile,
        "adherence": adherence,
        "no_show_tendency": no_show_tendency,
        "price_sensitivity": price_sensitivity,
        "loyalty": loyalty,
        "churn_tendency": churn,
        "frailty": frailty,
        "historical_mean_delay": mean_delay,
        "historical_on_time_rate": on_time,
        "prior_no_shows": no_shows,
        "prior_cancellations": cancelled,
    }


def step_hazards(
    when: pd.Timestamp,
    days_ratio: float,
    km_ratio: float,
    behavior: dict[str, Any],
    usage: pd.Series,
    motorcycle: pd.Series,
    workshop: pd.Series,
    recent_failure: bool,
    missed_since_service: int,
) -> dict[str, float]:
    pressure = max(days_ratio, km_ratio)
    pressure_signal = (
        0.0020
        + 0.018 * sigmoid(5.0 * (pressure - 0.62))
        + 0.070 * sigmoid(5.5 * (pressure - 1.00))
        + 0.060 * sigmoid(2.4 * (pressure - 1.65))
        + 0.045 * sigmoid(3.0 * (pressure - 2.45))
        + 0.038 * sigmoid(4.5 * (days_ratio - 0.95))
        + 0.016 * sigmoid(4.5 * (km_ratio - 0.95))
    )
    annual_km = float(usage.annual_km_baseline)
    usage_signal = sigmoid((annual_km - 11000.0) / 6500.0)
    due_usage_interaction = 1.0 + 0.42 * usage_signal * sigmoid(4.0 * (pressure - 0.85))
    adherence = 0.38 + 1.34 * behavior["adherence"]
    missed = math.exp(-0.38 * min(missed_since_service, 5))
    historical_miss_friction = math.exp(-0.58 * min(behavior.get("prior_no_shows", 0), 5))
    latent_friction = 1.0 - 0.48 * behavior["no_show_tendency"] - 0.25 * behavior["churn_tendency"]
    capacity = float(np.clip(0.78 + 0.025 * float(workshop.service_bay_count), 0.82, 1.12))
    season = 0.88 + 0.16 * math.cos(2 * math.pi * (when.month - 5) / 12.0)
    periodic = pressure_signal * due_usage_interaction * adherence * missed * historical_miss_friction
    periodic *= max(latent_friction, 0.28) * behavior["frailty"] * capacity * season

    age_years = max((when - pd.Timestamp(motorcycle.first_registration_date)).days / 365.25, 0.0)
    severity = float(usage.load_severity_factor)
    breakdown = 0.00035 + 0.00013 * age_years + 0.0010 * max(severity - 1.0, 0.0)
    breakdown += 0.0011 * usage_signal * sigmoid(3.0 * (pressure - 1.15))
    repair = 0.0008 + 0.00018 * age_years + 0.0007 * max(severity - 0.9, 0.0)
    if recent_failure:
        repair *= 1.35
    tire = 0.00035 + 0.025 * sigmoid(6.0 * (km_ratio - 1.45))
    appointment_create = periodic * (0.58 + 0.22 * behavior["loyalty"])
    direct_periodic = periodic * (0.34 + 0.12 * (1.0 - behavior["no_show_tendency"]))
    return {
        "PERIODIC": float(np.clip(periodic, 0.0002, 0.32)),
        "APPOINTMENT_CREATE": float(np.clip(appointment_create, 0.0001, 0.24)),
        "DIRECT_PERIODIC": float(np.clip(direct_periodic, 0.0001, 0.16)),
        "BREAKDOWN": float(np.clip(breakdown, 0.00015, 0.030)),
        "REPAIR": float(np.clip(repair, 0.00025, 0.030)),
        "TIRE": float(np.clip(tire, 0.00015, 0.070)),
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


def make_appointment(
    ids: IdFactory,
    motorcycle: pd.Series,
    created: pd.Timestamp,
    scheduled: pd.Timestamp,
    event_type: str,
    status: str,
    service_id: str | None,
) -> dict[str, Any]:
    appointment_id = ids.next_appointment()
    return {
        "appointment_id": appointment_id,
        "workshop_id": motorcycle.workshop_id,
        "customer_id": motorcycle.customer_id,
        "motorcycle_id": motorcycle.motorcycle_id,
        "created_at": created + pd.Timedelta(hours=10),
        "scheduled_at": scheduled + pd.Timedelta(hours=9),
        "appointment_type": event_type,
        "source": ["MOBILE_APP", "PHONE", "WHATSAPP"][int(stable_unit(appointment_id, salt="source") * 3) % 3],
        "status": status,
        "service_id": service_id,
        "customer_request": event_type,
        "data_origin": "SYNTHETIC",
        "generator_version": VERSION,
    }


def make_service(
    service_id: str,
    appointment_id: str | None,
    motorcycle: pd.Series,
    when: pd.Timestamp,
    odometer: int,
    event_type: str,
    policy: dict[str, Any],
    days_ratio: float,
    km_ratio: float,
    failure_count: int,
    failure_hazard: float,
    task_code: str,
) -> dict[str, Any]:
    row = v14.make_service(
        service_id, appointment_id, motorcycle, when, odometer, event_type, policy,
        days_ratio, km_ratio, failure_count, failure_hazard, task_code,
    )
    row.update({
        "customer_complaint": "Sentetik v1.5 davranış olayı",
        "generator_version": VERSION,
        "random_seed": SEED,
        "scenario_id": EXPERIMENT,
    })
    return row


def make_task(task_id: str, service: dict[str, Any], task_catalog: pd.DataFrame, policy_id: str | None) -> dict[str, Any]:
    row = v14.make_task(task_id, service, task_catalog, policy_id)
    row.update({"generator_version": VERSION, "random_seed": SEED, "notes": "V1.5 challenger tail event"})
    return row


def _outcome(behavior: dict[str, Any], motorcycle_id: str, created: pd.Timestamp, attempt: int) -> str:
    conversion = 0.34 + 0.52 * behavior["adherence"] + 0.16 * behavior["loyalty"]
    conversion -= 0.42 * behavior["no_show_tendency"] + 0.14 * behavior["churn_tendency"]
    conversion = float(np.clip(conversion, 0.18, 0.96))
    draw = stable_unit(motorcycle_id, created.date(), attempt, salt="appointment-outcome")
    if draw < conversion:
        return "CONVERTED_TO_SERVICE"
    no_show_share = float(np.clip(0.48 + 0.35 * behavior["no_show_tendency"], 0.48, 0.84))
    return "NO_SHOW" if stable_unit(motorcycle_id, created.date(), attempt, salt="miss-kind") < no_show_share else "CANCELLED"


def extend_behavior_tail(source: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    services = source["services.csv"].copy()
    services["received_at"] = pd.to_datetime(services.received_at, format="mixed")
    appointments = source["appointments.csv"].copy()
    appointments["created_at"] = pd.to_datetime(appointments.created_at, format="mixed")
    appointments["scheduled_at"] = pd.to_datetime(appointments.scheduled_at, format="mixed")
    tasks = source["service_tasks.csv"].copy()
    motorcycles = source["motorcycles.csv"].copy()
    customers = source["customers.csv"].set_index("customer_id")
    usage = source["usage_profiles.csv"].set_index("motorcycle_id")
    workshops = source["workshops.csv"].set_index("workshop_id")
    policies = v14.primary_policies(source["ridebase_motorcycle_models_v1.csv"], source["maintenance_policies.csv"])
    model_groups = source["ridebase_motorcycle_models_v1.csv"].set_index("model_id")["policy_group"].to_dict()
    lookup = MileageLookup(source["mileage_timeline_monthly.csv"])
    task_catalog = source["maintenance_tasks.csv"]
    ids = IdFactory(
        v14.numeric_suffix(services, "service_id"),
        v14.numeric_suffix(appointments, "appointment_id"),
        v14.numeric_suffix(tasks, "service_task_id"),
    )
    existing_services = {key: group.sort_values("received_at") for key, group in services.groupby("motorcycle_id")}
    existing_appointments = {key: group.sort_values("created_at") for key, group in appointments.groupby("motorcycle_id")}
    empty_services = services.iloc[0:0]
    empty_appointments = appointments.iloc[0:0]
    new_services: list[dict[str, Any]] = []
    new_appointments: list[dict[str, Any]] = []
    new_tasks: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []

    for motorcycle_tuple in motorcycles.itertuples(index=False):
        motorcycle = pd.Series(motorcycle_tuple._asdict())
        group = existing_services.get(motorcycle.motorcycle_id, empty_services)
        apt_group = existing_appointments.get(motorcycle.motorcycle_id, empty_appointments)
        start = pd.Timestamp(motorcycle.observation_start_date)
        raw_end = pd.to_datetime(motorcycle.observation_end_date, errors="coerce")
        end = HORIZON if pd.isna(raw_end) else min(pd.Timestamp(raw_end) + pd.Timedelta(hours=23, minutes=59), HORIZON)
        if not group.empty:
            last = group.iloc[-1]
            last_at = pd.Timestamp(last.received_at)
            last_odo = float(last.odometer_km)
            failure_count = int(group.service_type_code.isin(["BREAKDOWN", "REPAIR"]).sum())
            recent_failure = bool(group.tail(2).service_type_code.isin(["BREAKDOWN", "REPAIR"]).any())
        else:
            last_at, last_odo, failure_count, recent_failure = start, float(motorcycle.initial_mileage_km), 0, False
        if last_at >= end - pd.Timedelta(days=STEP_DAYS):
            continue

        profile = usage.loc[motorcycle.motorcycle_id]
        customer = customers.loc[motorcycle.customer_id]
        workshop = workshops.loc[motorcycle.workshop_id]
        behavior = behavior_state(customer, profile, group, apt_group)
        policy = policies[motorcycle.model_id]
        tail_days = max((end - last_at).days, STEP_DAYS)
        churned = stable_unit(motorcycle.motorcycle_id, salt="churn-event") < 0.22 * behavior["churn_tendency"]
        churn_at = last_at + pd.Timedelta(days=int(tail_days * (0.28 + 0.55 * stable_unit(motorcycle.motorcycle_id, salt="churn-time"))))
        pending: dict[str, Any] | None = None
        attempt = 0
        missed_since_service = 0
        last_miss_at: pd.Timestamp | None = None
        when = (last_at + pd.Timedelta(days=STEP_DAYS)).normalize()

        while when <= end:
            if churned and when >= churn_at and pending is None:
                audit.append({
                    "motorcycle_id": motorcycle.motorcycle_id, "event_at": churn_at, "outcome": "CHURN_CENSOR",
                    "event_type": "NON_RETURN", "latent_profile": behavior["profile"],
                    "adherence_band": "GOOD" if behavior["adherence"] >= .62 else "AVERAGE" if behavior["adherence"] >= .40 else "POOR",
                    "churn_band": "HIGH", "prior_no_shows": behavior["prior_no_shows"] + missed_since_service,
                    "usage_type": profile.usage_type, "riding_intensity": profile.riding_intensity,
                    "annual_km_baseline": profile.annual_km_baseline, "policy_group": model_groups.get(motorcycle.model_id, "UNKNOWN"),
                    "days_due_ratio": np.nan, "km_due_ratio": np.nan, "max_due_ratio": np.nan,
                    "periodic_hazard": 0.0, "rebook_after_miss": False,
                })
                break

            odo = lookup.odometer(motorcycle.motorcycle_id, when)
            days_ratio = max((when - last_at).total_seconds() / 86400.0, 0.0) / max(policy["days"], 1.0)
            km_ratio = max(odo - last_odo, 0.0) / max(policy["km"], 1.0)
            hazards = step_hazards(
                when, days_ratio, km_ratio, behavior, profile, motorcycle, workshop,
                recent_failure, missed_since_service,
            )

            event_type: str | None = None
            appointment_id: str | None = None
            if pending is not None and when >= pending["scheduled"]:
                if pending["status"] == "CONVERTED_TO_SERVICE":
                    event_type = pending["event_type"]
                    appointment_id = pending["appointment"]["appointment_id"]
                else:
                    missed_since_service += 1
                    last_miss_at = pending["scheduled"]
                    audit.append({
                        "motorcycle_id": motorcycle.motorcycle_id, "event_at": pending["scheduled"],
                        "outcome": pending["status"], "event_type": pending["event_type"],
                        "latent_profile": behavior["profile"],
                        "adherence_band": "GOOD" if behavior["adherence"] >= .62 else "AVERAGE" if behavior["adherence"] >= .40 else "POOR",
                        "churn_band": "HIGH" if behavior["churn_tendency"] >= .55 else "MEDIUM" if behavior["churn_tendency"] >= .30 else "LOW",
                        "prior_no_shows": behavior["prior_no_shows"] + missed_since_service,
                        "usage_type": profile.usage_type, "riding_intensity": profile.riding_intensity,
                        "annual_km_baseline": profile.annual_km_baseline,
                        "policy_group": model_groups.get(motorcycle.model_id, "UNKNOWN"),
                        "days_due_ratio": days_ratio, "km_due_ratio": km_ratio,
                        "max_due_ratio": max(days_ratio, km_ratio), "periodic_hazard": hazards["PERIODIC"],
                        "rebook_after_miss": False,
                    })
                    pending = None
                    when += pd.Timedelta(days=STEP_DAYS)
                    continue
                pending = None

            if event_type is None:
                for candidate in ["BREAKDOWN", "REPAIR", "TIRE"]:
                    if stable_unit(motorcycle.motorcycle_id, when.date(), candidate, salt="event") < hazards[candidate]:
                        event_type = candidate
                        break

            if event_type is None and pending is None:
                apt_draw = stable_unit(motorcycle.motorcycle_id, when.date(), attempt, salt="appointment-create")
                if apt_draw < hazards["APPOINTMENT_CREATE"]:
                    attempt += 1
                    lead = int(6 + 27 * stable_unit(motorcycle.motorcycle_id, when.date(), attempt, salt="appointment-lead"))
                    scheduled = when + pd.Timedelta(days=lead)
                    if scheduled <= end:
                        status = _outcome(behavior, motorcycle.motorcycle_id, when, attempt)
                        appointment = make_appointment(ids, motorcycle, when, scheduled, "PERIODIC", status, None)
                        new_appointments.append(appointment)
                        pending = {
                            "scheduled": scheduled, "status": status, "event_type": "PERIODIC",
                            "appointment": appointment,
                        }
                elif stable_unit(motorcycle.motorcycle_id, when.date(), salt="direct-periodic") < hazards["DIRECT_PERIODIC"]:
                    event_type = "PERIODIC"

            if event_type is None:
                when += pd.Timedelta(days=STEP_DAYS)
                continue

            service_id = ids.next_service()
            if appointment_id is not None:
                for appointment in reversed(new_appointments):
                    if appointment["appointment_id"] == appointment_id:
                        appointment["service_id"] = service_id
                        break
            task_code = (
                policy["task_code"] if event_type == "PERIODIC" else
                "FRONT_TIRE_CHANGE" if event_type == "TIRE" else
                ["ENGINE_COMPRESSION_TEST", "FUEL_SYSTEM_DIAGNOSTIC", "COOLING_SYSTEM_INSPECTION", "ABS_DIAGNOSTIC"][
                    int(stable_unit(service_id, salt="fault-task") * 4) % 4
                ]
            )
            service = make_service(
                service_id, appointment_id, motorcycle, when, int(round(odo)), event_type, policy,
                days_ratio, km_ratio, failure_count, hazards["BREAKDOWN"] + hazards["REPAIR"], task_code,
            )
            new_services.append(service)
            new_tasks.append(make_task(ids.next_task(), service, task_catalog, policy["policy_id"]))
            rebook = last_miss_at is not None and (when - last_miss_at).days <= 90
            if rebook:
                for row in reversed(audit):
                    if row["motorcycle_id"] == motorcycle.motorcycle_id and row["outcome"] in {"NO_SHOW", "CANCELLED"}:
                        row["rebook_after_miss"] = True
                        break
            audit.append({
                "motorcycle_id": motorcycle.motorcycle_id, "event_at": service["received_at"],
                "outcome": "SERVICE", "event_type": event_type, "latent_profile": behavior["profile"],
                "adherence_band": "GOOD" if behavior["adherence"] >= .62 else "AVERAGE" if behavior["adherence"] >= .40 else "POOR",
                "churn_band": "HIGH" if behavior["churn_tendency"] >= .55 else "MEDIUM" if behavior["churn_tendency"] >= .30 else "LOW",
                "prior_no_shows": behavior["prior_no_shows"] + missed_since_service,
                "usage_type": profile.usage_type, "riding_intensity": profile.riding_intensity,
                "annual_km_baseline": profile.annual_km_baseline,
                "policy_group": model_groups.get(motorcycle.model_id, "UNKNOWN"),
                "days_due_ratio": days_ratio, "km_due_ratio": km_ratio,
                "max_due_ratio": max(days_ratio, km_ratio), "periodic_hazard": hazards["PERIODIC"],
                "rebook_after_miss": rebook,
            })
            if event_type in {"BREAKDOWN", "REPAIR"}:
                failure_count += 1
                recent_failure = True
            else:
                recent_failure = False
            last_at, last_odo = pd.Timestamp(service["received_at"]), odo
            missed_since_service = 0
            pending = None
            when = (last_at + pd.Timedelta(days=STEP_DAYS)).normalize()

    if new_services:
        services = pd.concat([
            services, pd.DataFrame(new_services).reindex(columns=services.columns)
        ], ignore_index=True).sort_values("service_id")
        tasks = pd.concat([
            tasks, pd.DataFrame(new_tasks).reindex(columns=tasks.columns)
        ], ignore_index=True).sort_values("service_task_id")
    if new_appointments:
        appointments = pd.concat([
            appointments, pd.DataFrame(new_appointments).reindex(columns=appointments.columns)
        ], ignore_index=True).sort_values("appointment_id")
    source["services.csv"] = services
    source["appointments.csv"] = appointments
    source["service_tasks.csv"] = tasks

    enriched = source["services_enriched.csv"].copy()
    if new_services:
        extra = []
        for service in new_services:
            row = {
                "service_id": service["service_id"],
                "subtotal_before_discount": service["labor_total"] + service["parts_total"],
                "discount_rate": 0.0, "tax_rate": 0.2, "pricing_currency": "TRY",
                "cost_calculation_basis": "V1_5_SYNTHETIC_BEHAVIOR_EVENT",
                "cost_rule_version": VERSION,
            }
            row.update(service)
            extra.append(row)
        enriched = pd.concat([
            enriched, pd.DataFrame(extra).reindex(columns=enriched.columns)
        ], ignore_index=True).sort_values("service_id")
    source["services_enriched.csv"] = enriched
    return source, pd.DataFrame(audit)


def build(output: Path) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    source = {
        filename: pd.read_csv(PARENT / "source_tables" / filename, low_memory=False)
        for filename in contract["tables"]
    }
    frozen_hashes_before = {
        "v1_3": v14.source_hashes(PARENT),
        "v1_4": v14.source_hashes(REFERENCE),
    }
    source, audit = extend_behavior_tail(source)
    source_dir, report_dir = output / "source_tables", output / "reports"
    source_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    for filename, frame in source.items():
        frame.to_csv(source_dir / filename, index=False, encoding="utf-8", lineterminator="\n")
    audit.to_parquet(report_dir / "v1_5_generator_event_audit.parquet", index=False)
    qa = v14.source_qa(source, contract)
    frozen_hashes_after = {
        "v1_3": v14.source_hashes(PARENT),
        "v1_4": v14.source_hashes(REFERENCE),
    }
    frozen_ok = frozen_hashes_before == frozen_hashes_after
    qa["checks"]["frozen:v1_3_and_v1_4_hashes"] = frozen_ok
    qa["checks"]["latent_profiles_absent_from_source"] = all(
        "latent_profile" not in frame.columns for frame in source.values()
    )
    qa["checks"]["no_show_exists"] = bool((audit.outcome == "NO_SHOW").any())
    qa["checks"]["cancellation_exists"] = bool((audit.outcome == "CANCELLED").any())
    qa["checks"]["churn_censor_exists"] = bool((audit.outcome == "CHURN_CENSOR").any())
    qa["checks"]["rebooking_exists"] = bool(audit.rebook_after_miss.fillna(False).any())
    qa["failed"] = [name for name, passed in qa["checks"].items() if not passed]
    qa["status"] = "PASS" if not qa["failed"] else "FAIL"
    metadata = {
        "dataset_version": VERSION,
        "experiment": EXPERIMENT,
        "branching_parent": "1.3.0 frozen core",
        "immutable_reference": "1.4.0",
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "source_schema_changed": False,
        "random_seed": SEED,
        "step_days": STEP_DAYS,
        "source_hashes": v14.source_hashes(output),
        "frozen_reference_hashes": frozen_hashes_before,
        "new_event_rows": int((audit.outcome == "SERVICE").sum()),
        "new_no_show_rows": int((audit.outcome == "NO_SHOW").sum()),
        "new_cancel_rows": int((audit.outcome == "CANCELLED").sum()),
        "new_churn_censors": int((audit.outcome == "CHURN_CENSOR").sum()),
        "rebooked_after_miss": int(
            (audit.outcome.eq("SERVICE") & audit.rebook_after_miss.fillna(False)).sum()
        ),
        "latent_profile_counts_audit_only": audit.latent_profile.value_counts().to_dict(),
        "qa": qa,
        "disclaimer": "Synthetic behavioral assumptions; not validated on real RideBase fleet data.",
    }
    write_json(metadata, output / "dataset_metadata.json")
    write_json(qa, report_dir / "source_qa.json")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-reproducibility", action="store_true")
    args = parser.parse_args()
    forbidden = {PARENT.resolve(), REFERENCE.resolve()}
    if args.output.resolve() in forbidden:
        raise SystemExit("Refusing to overwrite frozen V1.3/V1.4")
    if args.output.exists():
        shutil.rmtree(args.output)
    metadata = build(args.output)
    if args.verify_reproducibility:
        with tempfile.TemporaryDirectory(prefix="ridebase-v1-5-repro-") as temp:
            second = build(Path(temp) / "ridebase_v1_5")
            reproducible = metadata["source_hashes"] == second["source_hashes"]
        metadata["reproducibility_verified"] = reproducible
        metadata["qa"]["checks"]["reproducibility:source_hashes"] = reproducible
        if not reproducible:
            metadata["qa"]["status"] = "FAIL"
            metadata["qa"]["failed"].append("reproducibility:source_hashes")
        write_json(metadata, args.output / "dataset_metadata.json")
        write_json(metadata["qa"], args.output / "reports/source_qa.json")
    print(json.dumps({
        "dataset_version": metadata["dataset_version"],
        "new_event_rows": metadata["new_event_rows"],
        "new_no_show_rows": metadata["new_no_show_rows"],
        "new_cancel_rows": metadata["new_cancel_rows"],
        "new_churn_censors": metadata["new_churn_censors"],
        "rebooked_after_miss": metadata["rebooked_after_miss"],
        "qa": metadata["qa"]["status"],
        "reproducibility": metadata.get("reproducibility_verified"),
    }, indent=2))


if __name__ == "__main__":
    main()
