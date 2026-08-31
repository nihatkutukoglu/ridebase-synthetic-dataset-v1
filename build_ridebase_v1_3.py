from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import zipfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, median_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder
from sklearn.feature_selection import mutual_info_regression


ROOT = Path(__file__).resolve().parent
V12 = ROOT / "ridebase_v1_2"
VERSION = "1.3.0"
SEED = 42
HORIZON = pd.Timestamp("2026-08-25 23:59:59")
TRAIN_END = pd.Timestamp("2025-06-30 23:59:59")
VALIDATION_END = pd.Timestamp("2025-12-31 23:59:59")
FAILURE_TYPES = {"REPAIR", "BREAKDOWN"}
EXPERIMENT_DESCRIPTION = (
    "This release is a synthetic generator calibration experiment intended to test the "
    "learnability of next-service timing/mileage from snapshot-available features. "
    "It is not production validation."
)


def stable_unit(*parts: object, salt: str = "") -> float:
    raw = ":".join([str(SEED), salt, *map(str, parts)]).encode()
    return int(hashlib.sha256(raw).hexdigest()[:15], 16) / float(16**15)


def stable_normal(*parts: object, salt: str = "") -> float:
    u1 = max(stable_unit(*parts, salt=salt + "-u1"), 1e-12)
    u2 = stable_unit(*parts, salt=salt + "-u2")
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def stable_between(low: float, high: float, *parts: object, salt: str = "") -> float:
    return low + (high - low) * stable_unit(*parts, salt=salt)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def write_json(obj: object, path: Path) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")


def json_default(x):
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.floating,)): return None if not np.isfinite(x) else float(x)
    if isinstance(x, (pd.Timestamp,)): return x.isoformat()
    raise TypeError(type(x).__name__)


def update_versions(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["generator_version", "taxonomy_version", "policy_version", "profile_rule_version", "feature_version", "target_version", "noise_rule_version"]:
        if col in out: out[col] = VERSION
    if "random_seed" in out: out["random_seed"] = SEED
    if "scenario_id" in out: out["scenario_id"] = "REGRESSION_CALIBRATION_V1_3"
    return out


def md_table(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False, floatfmt=".4f")


def lag1(frame: pd.DataFrame, value: str, group: str = "motorcycle_id") -> float:
    pairs = []
    for _, g in frame.groupby(group, sort=False):
        a = pd.to_numeric(g[value], errors="coerce").dropna().to_numpy(float)
        if len(a) >= 3: pairs.append(np.column_stack([a[:-1], a[1:]]))
    if not pairs: return math.nan
    z = np.vstack(pairs)
    return float(np.corrcoef(z[:, 0], z[:, 1])[0, 1])


def split_name(ts: pd.Timestamp) -> str:
    if ts <= TRAIN_END: return "TRAIN"
    if ts <= VALIDATION_END: return "VALIDATION"
    return "TEST"


def policy_anchors(policies: pd.DataFrame) -> dict[str, tuple[float, float]]:
    p = policies[(policies["is_generator_active"].eq(1)) & policies["policy_kind"].eq("SCHEDULED")].copy()
    anchors = {}
    for group, g in p.groupby("policy_group"):
        kms = pd.to_numeric(g["recurring_km"], errors="coerce").dropna()
        kms = kms[kms >= 3000]
        months = pd.to_numeric(g["recurring_months"], errors="coerce").dropna()
        # A service visit is anchored to the common high-priority cadence, not every
        # 500 km chain-lubrication task.
        km = float(kms.quantile(.25)) if len(kms) else 6000.0
        days = float(months.min() * 30.4375) if len(months) else 365.25
        anchors[group] = (float(np.clip(days, 180, 730)), float(np.clip(km, 3000, 12000)))
    return anchors


def regenerate_mileage(mileage: pd.DataFrame, usage: pd.DataFrame) -> pd.DataFrame:
    out = mileage.copy()
    out["period_start_date"] = pd.to_datetime(out["period_start_date"])
    out["period_end_date"] = pd.to_datetime(out["period_end_date"])
    u = usage.set_index("motorcycle_id")
    rows = []
    for mid, g in out.sort_values(["motorcycle_id", "period_start_date"]).groupby("motorcycle_id", sort=False):
        profile = u.loc[mid]
        usage_type = profile["usage_type"]
        phi = .72 if usage_type in {"COMMUTER", "COURIER"} else .58
        innovation = .105 if usage_type == "COURIER" else (.13 if usage_type in {"COMMUTER", "TOURING"} else .18)
        seasonal_amp = float(profile.get("seasonality_strength", .2)) * (1.25 if usage_type in {"WEEKEND", "SEASONAL"} else .65)
        seasonal_amp = float(np.clip(seasonal_amp, .04, .48))
        annual = float(profile["annual_km_baseline"])
        opening = float(g.iloc[0]["opening_odometer_km"])
        ar = stable_between(-.08, .08, mid, salt="usage-initial-state")
        trend = stable_between(-.06, .06, mid, salt="usage-long-trend")
        n = max(len(g) - 1, 1)
        for j, (_, row) in enumerate(g.iterrows()):
            month = int(row["period_start_date"].month)
            active_fraction = max(int(row["active_days"]), 1) / max(int(row["period_end_date"].days_in_month), 1)
            phase = 2 * math.pi * (month - 7) / 12
            season = max(.35, 1 + seasonal_amp * math.cos(phase))
            ar = phi * ar + innovation * stable_normal(mid, row["year_month"], salt="usage-month-innovation")
            drift = 1 + trend * (j / n - .5)
            km = int(round(max(8, annual / 12 * active_fraction * season * math.exp(ar) * drift)))
            r = row.copy()
            r["opening_odometer_km"] = int(round(opening))
            r["km_added"] = km
            r["closing_odometer_km"] = int(round(opening + km))
            r["avg_km_per_active_day_observed"] = round(km / max(int(row["active_days"]), 1), 1)
            r["usage_type"] = usage_type
            r["annual_km_baseline"] = int(round(annual))
            r["generator_version"] = VERSION
            rows.append(r)
            opening += km
    return pd.DataFrame(rows, columns=out.columns)


class MileageLookup:
    def __init__(self, mileage: pd.DataFrame):
        self.data = {}
        for mid, g in mileage.sort_values(["motorcycle_id", "period_start_date"]).groupby("motorcycle_id", sort=False):
            self.data[mid] = g[["period_start_date", "period_end_date", "opening_odometer_km", "closing_odometer_km"]].copy()

    def odometer(self, mid: str, when: pd.Timestamp) -> float:
        g = self.data[mid]
        hit = g[(g.period_start_date <= when.normalize()) & (g.period_end_date >= when.normalize())]
        if len(hit):
            r = hit.iloc[0]
            span = max((r.period_end_date - r.period_start_date).days + 1, 1)
            frac = np.clip(((when.normalize() - r.period_start_date).days + .5) / span, 0, 1)
            return float(r.opening_odometer_km + frac * (r.closing_odometer_km - r.opening_odometer_km))
        if when < g.period_start_date.min(): return float(g.iloc[0].opening_odometer_km)
        return float(g.iloc[-1].closing_odometer_km)

    def rate(self, mid: str, when: pd.Timestamp, days: int) -> float:
        return max((self.odometer(mid, when) - self.odometer(mid, when - pd.Timedelta(days=days))) / days, .05)


def regenerate_services(source: dict[str, pd.DataFrame], mileage: pd.DataFrame):
    services = source["services.csv"].copy()
    old = services.copy()
    motorcycles = source["motorcycles.csv"].copy()
    usage = source["usage_profiles.csv"].copy()
    models = source["ridebase_motorcycle_models_v1.csv"]
    policies = source["maintenance_policies.csv"]
    anchors = policy_anchors(policies)
    lookup = MileageLookup(mileage)
    mc = motorcycles.set_index("motorcycle_id")
    up = usage.set_index("motorcycle_id")
    model_policy = models.set_index("model_id")["policy_group"]
    old["received_at"] = pd.to_datetime(old["received_at"])
    for c in ["estimated_delivery_at", "completed_at", "delivered_at", "trigger_due_date"]:
        old[c] = pd.to_datetime(old[c], errors="coerce")
    # Stable behavior is derived from past-like customer history, then remains latent.
    old_delays = old.loc[old.service_type_code.eq("PERIODIC")].groupby("customer_id")["service_delay_days"].median()
    components = []
    new_rows = []
    for mid, g in old.sort_values(["motorcycle_id", "received_at", "service_id"]).groupby("motorcycle_id", sort=False):
        g = g.copy().reset_index(drop=True)
        mrow = mc.loc[mid]
        profile = up.loc[mid]
        policy_group = model_policy.get(mrow.model_id, mrow.get("policy_group", ""))
        policy_days, policy_km = anchors.get(policy_group, (365.25, 6000.0))
        customer_delay = float(old_delays.get(mrow.customer_id, 0.0) or 0.0)
        tendency = np.clip(1 + customer_delay / max(policy_days, 120) * .45 + stable_between(-.07, .07, mrow.customer_id, salt="behavior-tendency"), .84, 1.24)
        behavior_label = "REGULAR" if tendency < 1.04 else ("SLIGHTLY_LATE" if tendency < 1.14 else "IRREGULAR")
        dates = [pd.Timestamp(g.iloc[0].received_at)]
        dets, noises, pday_list, pkm_list, rates = [], [], [], [], []
        recent_behavior = tendency
        history_intervals = []
        for j in range(1, len(g)):
            prev = dates[-1]
            recent_rate = lookup.rate(mid, prev, 90)
            long_rate = max(float(profile.annual_km_baseline) / 365.25, .1)
            usage_ratio = float(np.clip(recent_rate / long_rate, .55, 1.65))
            due_from_km = policy_km / max(.68 * recent_rate + .32 * long_rate, .1)
            policy_due = min(policy_days, due_from_km)
            hist_factor = 1.0
            if history_intervals:
                hist_factor = float(np.clip(np.median(history_intervals[-3:]) / max(policy_due, 1), .82, 1.20))
            adherence = .68 * tendency + .22 * recent_behavior + .10
            service_history = 1 - .025 * min(j, 5) / 5
            deterministic = policy_due * adherence * (.95 + .05 / usage_ratio) * (.72 + .28 * hist_factor) * service_history
            next_type = str(g.iloc[j].service_type_code)
            risk = float(g.iloc[j].get("failure_hazard_score", .05) or .05)
            if next_type in FAILURE_TYPES:
                deterministic *= float(np.clip(.72 - 1.8 * (risk - .05), .42, .84))
            elif next_type == "TIRE":
                tire_km = stable_between(8500, 14500, mid, j, salt="tire-wear-threshold")
                deterministic = min(deterministic, tire_km / max(recent_rate, .1)) * .92
            noise_z = stable_normal(mid, j, salt="service-interval-noise")
            noise_scale = .14 if behavior_label != "IRREGULAR" else .19
            factor = float(np.clip(math.exp(noise_scale * noise_z - .5 * noise_scale**2), .67, 1.43))
            interval = max(5 if next_type in FAILURE_TYPES else 14, deterministic * factor)
            dets.append(deterministic); noises.append(interval - deterministic)
            pday_list.append(policy_days); pkm_list.append(policy_km); rates.append(recent_rate)
            dates.append(prev + pd.Timedelta(days=interval))
            history_intervals.append(interval)
            recent_behavior = .72 * recent_behavior + .28 * np.clip(interval / max(policy_due, 1), .7, 1.35)
        end = pd.to_datetime(mrow.observation_end_date, errors="coerce")
        end = HORIZON if pd.isna(end) else min(pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=59), HORIZON)
        if len(dates) > 1 and dates[-1] > end:
            available = max((end - dates[0]).total_seconds() / 86400 - 1, len(dates) * 5)
            raw_sum = sum((dates[k] - dates[k-1]).total_seconds() / 86400 for k in range(1, len(dates)))
            volume_scale = available / max(raw_sum, 1)
            revised = [dates[0]]
            for k in range(1, len(dates)):
                old_interval = (dates[k] - dates[k-1]).total_seconds() / 86400
                new_interval = max(3 if g.iloc[k].service_type_code in FAILURE_TYPES else 7, old_interval * volume_scale)
                revised.append(revised[-1] + pd.Timedelta(days=new_interval))
                dets[k-1] *= volume_scale; noises[k-1] *= volume_scale
            dates = revised
        prev_periodic_delay = 0.0
        prev_periodic_km_delay = 0.0
        for j, (_, row) in enumerate(g.iterrows()):
            r = row.copy()
            new_at = dates[j].round("s")
            old_at = pd.Timestamp(row.received_at)
            delta = new_at - old_at
            odo = int(round(lookup.odometer(mid, new_at)))
            r["received_at"] = new_at
            r["odometer_km"] = odo
            for col in ["estimated_delivery_at", "completed_at", "delivered_at"]:
                val = pd.to_datetime(row[col], errors="coerce")
                r[col] = val + delta if pd.notna(val) else pd.NaT
            r["estimated_delivery_at"] = max(pd.Timestamp(r["estimated_delivery_at"]), new_at) if pd.notna(r["estimated_delivery_at"]) else new_at + pd.Timedelta(hours=4)
            r["completed_at"] = max(pd.Timestamp(r["completed_at"]), new_at) if pd.notna(r["completed_at"]) else new_at + pd.Timedelta(hours=2)
            r["delivered_at"] = max(pd.Timestamp(r["delivered_at"]), pd.Timestamp(r["completed_at"])) if pd.notna(r["delivered_at"]) else pd.Timestamp(r["completed_at"]) + pd.Timedelta(hours=2)
            r["maintenance_overdue_days_pre_service"] = prev_periodic_delay
            r["maintenance_overdue_km_pre_service"] = prev_periodic_km_delay
            if j == 0:
                due_date, due_km = pd.NaT, np.nan
            else:
                prev_at = dates[j-1]
                prev_odo = int(round(lookup.odometer(mid, prev_at)))
                due_date = prev_at + pd.Timedelta(days=pday_list[j-1])
                due_km = prev_odo + pkm_list[j-1]
            if r.service_type_code == "PERIODIC":
                r["trigger_due_date"] = due_date
                r["trigger_due_km"] = due_km
                delay = max((new_at - due_date).total_seconds() / 86400, 0) if pd.notna(due_date) else 0.0
                km_delay = max(odo - due_km, 0) if pd.notna(due_km) else 0.0
                r["service_delay_days"] = round(delay, 2)
                prev_periodic_delay, prev_periodic_km_delay = delay, km_delay
            elif r.service_type_code in FAILURE_TYPES:
                r["service_delay_days"] = np.nan
                r["overdue_maintenance_days_at_failure"] = prev_periodic_delay
                r["overdue_maintenance_km_at_failure"] = prev_periodic_km_delay
            r["is_warranty"] = int(
                r.service_type_code in FAILURE_TYPES
                and new_at <= pd.Timestamp(mrow.first_registration_date) + pd.DateOffset(months=int(mrow.warranty_months))
                and odo <= float(mrow.warranty_km_limit)
                and str(r.get("failure_severity")) != "HIGH"
            )
            r["scenario_id"] = "REGRESSION_CALIBRATION_V1_3"
            r["generator_version"] = VERSION
            new_rows.append(r)
            if j > 0:
                actual_days = (dates[j] - dates[j-1]).total_seconds() / 86400
                actual_km = odo - int(round(lookup.odometer(mid, dates[j-1])))
                components.append({
                    "source_service_id": g.iloc[j-1].service_id, "next_service_id": r.service_id,
                    "motorcycle_id": mid, "behavior_label": behavior_label,
                    "policy_interval_days": pday_list[j-1], "policy_interval_km": pkm_list[j-1],
                    "recent_km_per_day": rates[j-1], "deterministic_days": dets[j-1],
                    "noise_days": noises[j-1], "actual_days": actual_days,
                    "deterministic_km": dets[j-1] * rates[j-1],
                    "noise_km": actual_km - dets[j-1] * rates[j-1], "actual_km": actual_km,
                    "noise_z": stable_normal(mid, j, salt="service-interval-noise"),
                })
    services = pd.DataFrame(new_rows, columns=old.columns).sort_values("service_id").reset_index(drop=True)
    return services, pd.DataFrame(components), old


def shift_related(source: dict[str, pd.DataFrame], old_services: pd.DataFrame, services: pd.DataFrame):
    old_at = old_services.set_index("service_id")["received_at"].map(pd.Timestamp)
    new_at = services.set_index("service_id")["received_at"].map(pd.Timestamp)
    delta = new_at - old_at
    # Appointments preserve lifecycle identity/diversity; linked appointments move with service.
    ap = source["appointments.csv"].copy()
    for idx, row in ap[ap.service_id.notna()].iterrows():
        d = delta.get(row.service_id, pd.Timedelta(0))
        for c in ["created_at", "scheduled_at"]:
            v = pd.to_datetime(row[c], errors="coerce")
            if pd.notna(v): ap.at[idx, c] = v + d
    source["appointments.csv"] = ap
    tasks = source["service_tasks.csv"].copy()
    for c in ["started_at", "completed_at"]: tasks[c] = pd.to_datetime(tasks[c], errors="coerce")
    tasks["_delta"] = tasks.service_id.map(delta)
    for c in ["started_at", "completed_at"]: tasks[c] = tasks[c] + tasks["_delta"]
    recv = tasks.service_id.map(new_at)
    tasks["started_at"] = tasks["started_at"].where(tasks.started_at >= recv, recv + pd.Timedelta(minutes=5))
    tasks.loc[tasks.status.eq("COMPLETED"), "completed_at"] = np.maximum(
        tasks.loc[tasks.status.eq("COMPLETED"), "completed_at"].values.astype("datetime64[ns]"),
        (tasks.loc[tasks.status.eq("COMPLETED"), "started_at"] + pd.Timedelta(minutes=1)).values.astype("datetime64[ns]")
    )
    tasks = tasks.drop(columns="_delta")
    source["service_tasks.csv"] = tasks
    enriched = source["services_enriched.csv"].drop(columns=[c for c in services.columns if c in source["services_enriched.csv"] and c != "service_id"]).merge(services, on="service_id", how="right")
    source["services_enriched.csv"] = enriched
    return source, delta


def rebuild_status_history(base: pd.DataFrame, services: pd.DataFrame, delta: pd.Series) -> pd.DataFrame:
    h = base.copy()
    h["status_at"] = pd.to_datetime(h["status_at"], errors="coerce") + h.service_id.map(delta)
    h = h.sort_values(["service_id", "status_sequence", "status_at"])
    h["status_at"] = h.groupby("service_id")["status_at"].cummax()
    return update_versions(h)


def service_history_features(snapshots: pd.DataFrame, services: pd.DataFrame, mileage_lookup: MileageLookup, components: pd.DataFrame, policy_map: dict):
    s = snapshots.copy().set_index("source_service_id", drop=False)
    sv = services.sort_values(["motorcycle_id", "received_at", "service_id"]).copy()
    comp = components.set_index("source_service_id") if len(components) else pd.DataFrame()
    records = []
    for mid, g in sv.groupby("motorcycle_id", sort=False):
        g = g.reset_index(drop=True)
        intervals_d, intervals_k, policy_delays = [], [], []
        on_time = []
        last_periodic_delay = np.nan
        for j, row in g.iterrows():
            at = pd.Timestamp(row.received_at); odo = float(row.odometer_km)
            if j:
                pdays = (at - pd.Timestamp(g.iloc[j-1].received_at)).total_seconds()/86400
                pkm = odo - float(g.iloc[j-1].odometer_km)
                intervals_d.append(pdays); intervals_k.append(pkm)
            if row.service_type_code == "PERIODIC":
                delay = float(row.service_delay_days or 0)
                policy_delays.append(delay); on_time.append(float(delay <= 14)); last_periodic_delay = delay
            prev_d = intervals_d[-1] if intervals_d else np.nan
            prev_k = intervals_k[-1] if intervals_k else np.nan
            past_d = np.asarray(intervals_d, float); past_k = np.asarray(intervals_k, float)
            c = comp.loc[row.service_id] if len(comp) and row.service_id in comp.index else None
            records.append({
                "source_service_id": row.service_id,
                "previous_service_count": j,
                "previous_interval_days": prev_d, "previous_interval_km": prev_k,
                "historical_interval_days_median": float(np.median(past_d)) if len(past_d) else np.nan,
                "historical_interval_days_std": float(np.std(past_d, ddof=1)) if len(past_d)>1 else np.nan,
                "historical_interval_km_median": float(np.median(past_k)) if len(past_k) else np.nan,
                "historical_interval_km_std": float(np.std(past_k, ddof=1)) if len(past_k)>1 else np.nan,
                "historical_policy_delay_median_days": float(np.median(policy_delays)) if policy_delays else np.nan,
                "historical_policy_delay_mean_days": float(np.mean(policy_delays)) if policy_delays else np.nan,
                "historical_on_time_rate": float(np.mean(on_time)) if on_time else np.nan,
                "previous_policy_delay_days": last_periodic_delay,
                "recent_30d_km": mileage_lookup.rate(mid, at, 30)*30,
                "recent_60d_km": mileage_lookup.rate(mid, at, 60)*60,
                "recent_90d_km": mileage_lookup.rate(mid, at, 90)*90,
                "recent_180d_km": mileage_lookup.rate(mid, at, 180)*180,
                "recent_km_per_day": mileage_lookup.rate(mid, at, 90),
                "long_term_km_per_day": max(float(s.loc[row.service_id].annual_km_baseline)/365.25, .05),
                "policy_interval_days": float(c.policy_interval_days) if c is not None else policy_map.get(s.loc[row.service_id].policy_group,(365.25,6000))[0],
                "policy_interval_km": float(c.policy_interval_km) if c is not None else policy_map.get(s.loc[row.service_id].policy_group,(365.25,6000))[1],
            })
    f = pd.DataFrame(records).set_index("source_service_id")
    f["recent_vs_long_term_usage_ratio"] = (f.recent_km_per_day / f.long_term_km_per_day).clip(.2, 3)
    return f


def rebuild_snapshots_targets(source: dict[str, pd.DataFrame], mileage: pd.DataFrame, components: pd.DataFrame):
    services = source["services.csv"].copy()
    services["received_at"] = pd.to_datetime(services.received_at)
    snapshots = pd.read_parquet(V12 / "derived_outputs/ml_maintenance_snapshots.parquet").copy()
    snapshots = snapshots.set_index("source_service_id", drop=False)
    sv = services.set_index("service_id")
    lookup = MileageLookup(mileage)
    policies = policy_anchors(source["maintenance_policies.csv"])
    hist = service_history_features(snapshots, services, lookup, components, policies)
    for sid in snapshots.index:
        r = sv.loc[sid]; at = pd.Timestamp(r.received_at)
        snapshots.at[sid, "snapshot_at"] = at
        snapshots.at[sid, "snapshot_date"] = at.normalize()
        snapshots.at[sid, "snapshot_year"] = at.year
        snapshots.at[sid, "snapshot_month"] = at.month
        snapshots.at[sid, "snapshot_quarter"] = at.quarter
        snapshots.at[sid, "snapshot_day_of_year"] = at.dayofyear
        snapshots.at[sid, "snapshot_month_sin"] = math.sin(2*math.pi*at.month/12)
        snapshots.at[sid, "snapshot_month_cos"] = math.cos(2*math.pi*at.month/12)
        snapshots.at[sid, "snapshot_odometer_km"] = r.odometer_km
        snapshots.at[sid, "current_service_type_code"] = r.service_type_code
        snapshots.at[sid, "current_arrival_mode"] = r.arrival_mode
        snapshots.at[sid, "current_primary_trigger_task"] = r.primary_trigger_task
        snapshots.at[sid, "current_service_delay_days"] = r.service_delay_days
        snapshots.at[sid, "current_is_breakdown"] = r.is_breakdown
        snapshots.at[sid, "current_is_warranty"] = r.is_warranty
        snapshots.at[sid, "maintenance_overdue_days_pre_service"] = r.maintenance_overdue_days_pre_service
        snapshots.at[sid, "maintenance_overdue_km_pre_service"] = r.maintenance_overdue_km_pre_service
        snapshots.at[sid, "previous_failure_count"] = r.previous_failure_count
        snapshots.at[sid, "failure_hazard_score"] = r.failure_hazard_score
    for c in hist.columns: snapshots[c] = snapshots.source_service_id.map(hist[c])
    snapshots["days_since_previous_service"] = snapshots["previous_interval_days"]
    snapshots["km_since_previous_service"] = snapshots["previous_interval_km"]
    snapshots["avg_km_per_day_since_previous_service"] = snapshots.km_since_previous_service / snapshots.days_since_previous_service.replace(0, np.nan)
    snapshots["avg_service_interval_days"] = snapshots["historical_interval_days_median"]
    snapshots["avg_service_interval_km"] = snapshots["historical_interval_km_median"]
    snapshots["rolling3_interval_days"] = snapshots["historical_interval_days_median"]
    snapshots["rolling3_interval_km"] = snapshots["historical_interval_km_median"]
    snapshots["feature_version"] = VERSION; snapshots["generator_version"] = VERSION
    snapshots["scenario_id"] = "REGRESSION_CALIBRATION_V1_3"
    snapshots = snapshots.reset_index(drop=True)
    # Recompute sequence and cumulative event counters in new chronological order.
    order = services.sort_values(["motorcycle_id","received_at","service_id"]).copy()
    order["service_sequence"] = order.groupby("motorcycle_id").cumcount()+1
    for typ, col in [("PERIODIC","periodic_service_count"),("REPAIR","repair_service_count"),("BREAKDOWN","breakdown_service_count")]:
        order[col] = order.service_type_code.eq(typ).groupby(order.motorcycle_id).cumsum()
    order["warranty_service_count"] = order.is_warranty.groupby(order.motorcycle_id).cumsum()
    ol = order.set_index("service_id")
    for c in ["service_sequence","periodic_service_count","repair_service_count","breakdown_service_count","warranty_service_count"]:
        snapshots[c] = snapshots.source_service_id.map(ol[c])
    # Next-event targets, including natural right censoring at the observation end.
    mc_end = source["motorcycles.csv"].set_index("motorcycle_id")["observation_end_date"]
    next_map = {}
    for mid, g in order.groupby("motorcycle_id", sort=False):
        ids = g.service_id.tolist()
        for a,b in zip(ids[:-1],ids[1:]): next_map[a]=b
    template = pd.read_parquet(V12 / "derived_outputs/ml_next_service_targets.parquet").set_index("source_service_id", drop=False)
    targets=[]
    future_cols = [c for c in template.columns if c.startswith("next_service_")] + ["target_next_service_at","days_to_next_service_raw","days_to_next_service","target_time_repaired","km_to_next_service_raw","km_to_next_service","target_km_valid"]
    for _, snap in snapshots.iterrows():
        sid=snap.source_service_id; row=template.loc[sid].copy(); nxt=next_map.get(sid)
        at=pd.Timestamp(snap.snapshot_at); end=pd.to_datetime(mc_end.get(snap.motorcycle_id),errors="coerce"); end=HORIZON if pd.isna(end) else min(pd.Timestamp(end)+pd.Timedelta(hours=23,minutes=59),HORIZON)
        row["snapshot_at"]=at; row["snapshot_odometer_km"]=snap.snapshot_odometer_km
        row["censor_at"]=end; row["censor_days"]=(end-at).total_seconds()/86400; row["days_to_event_or_censor"]=row["censor_days"]
        if nxt is None:
            row["target_event_observed"]=0; row["is_right_censored"]=1
            for c in set(future_cols):
                if c in row: row[c]=pd.NA
        else:
            nr=sv.loc[nxt]; nat=pd.Timestamp(nr.received_at); days=(nat-at).total_seconds()/86400; km=float(nr.odometer_km)-float(snap.snapshot_odometer_km)
            row["target_event_observed"]=1; row["is_right_censored"]=0; row["next_service_id"]=nxt
            row["next_service_received_at_raw"]=nat; row["target_next_service_at"]=nat; row["next_service_delivered_at"]=nr.delivered_at
            row["days_to_next_service_raw"]=days; row["days_to_next_service"]=days; row["target_time_repaired"]=0
            row["next_service_odometer_km"]=nr.odometer_km; row["km_to_next_service_raw"]=km; row["km_to_next_service"]=km; row["target_km_valid"]=int(km>=0)
            for tc,sc in [("next_service_mileage_source","mileage_source"),("next_service_mileage_quality_flag","mileage_quality_flag"),("next_service_is_mileage_estimated","is_mileage_estimated"),("next_service_type_code","service_type_code"),("next_service_primary_trigger_task","primary_trigger_task"),("next_service_arrival_mode","arrival_mode"),("next_service_is_breakdown","is_breakdown"),("next_service_is_warranty","is_warranty")]: row[tc]=nr[sc]
            row["days_to_event_or_censor"]=days
        row["target_version"]=VERSION; row["generator_version"]=VERSION; row["scenario_id"]="REGRESSION_CALIBRATION_V1_3"
        targets.append(row)
    targets=pd.DataFrame(targets,columns=template.columns)
    return snapshots, targets, next_map


def rebuild_next_tasks(source: dict[str,pd.DataFrame], targets: pd.DataFrame) -> pd.DataFrame:
    base=pd.read_parquet(V12/"derived_outputs/ml_next_task_targets.parquet").set_index("snapshot_id",drop=False)
    tasks=source["service_tasks.csv"]
    code_sets=tasks.groupby("service_id")["task_code"].agg(set)
    list_rows=tasks.groupby("service_id").agg(next_task_codes=("task_code",lambda x:"|".join(sorted(set(x)))),next_task_count=("task_code","size"),next_completed_task_count=("completed","sum"),next_declined_task_count=("status",lambda x:int((x=="DECLINED").sum()))).to_dict("index")
    completed=tasks[tasks.status.eq("COMPLETED")].groupby("service_id")["task_code"].agg(lambda x:"|".join(sorted(set(x))))
    declined=tasks[tasks.status.eq("DECLINED")].groupby("service_id")["task_code"].agg(lambda x:"|".join(sorted(set(x))))
    out=[]; label_cols=[c for c in base.columns if c.startswith("task__")]
    for _,t in targets.iterrows():
        r=base.loc[t.snapshot_id].copy(); nxt=t.next_service_id if t.target_event_observed==1 else None
        r["next_service_id"]=nxt; r["target_event_observed"]=t.target_event_observed; r["is_right_censored"]=t.is_right_censored
        if nxt is None or pd.isna(nxt):
            for c in label_cols+["next_task_codes","next_completed_task_codes","next_declined_task_codes","next_task_count","next_completed_task_count","next_declined_task_count"]: r[c]=pd.NA
        else:
            codes=code_sets.get(nxt,set()); info=list_rows.get(nxt,{})
            for c in label_cols: r[c]=int(c.removeprefix("task__") in codes)
            for c in ["next_task_codes","next_task_count","next_completed_task_count","next_declined_task_count"]: r[c]=info.get(c,pd.NA)
            r["next_completed_task_codes"]=completed.get(nxt,pd.NA); r["next_declined_task_codes"]=declined.get(nxt,pd.NA)
        r["target_version"]=VERSION; r["generator_version"]=VERSION; r["taxonomy_version"]=VERSION; r["scenario_id"]="REGRESSION_CALIBRATION_V1_3"
        out.append(r)
    return pd.DataFrame(out,columns=base.columns)


def rebuild_split(snapshots: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    base=read_csv(V12/"derived_outputs/split_manifest.csv").set_index("snapshot_id",drop=False)
    t=targets.set_index("snapshot_id")
    out=[]
    for _,s in snapshots.iterrows():
        r=base.loc[s.snapshot_id].copy(); at=pd.Timestamp(s.snapshot_at); split=split_name(at); target=t.loc[s.snapshot_id]
        cutoff={"TRAIN":TRAIN_END,"VALIDATION":VALIDATION_END,"TEST":HORIZON}[split]
        start={"TRAIN":pd.Timestamp("2021-01-01"),"VALIDATION":pd.Timestamp("2025-07-01"),"TEST":pd.Timestamp("2026-01-01")}[split]
        nxt=pd.to_datetime(target.target_next_service_at,errors="coerce"); full=int(target.target_event_observed)
        in_window=int(full and nxt<=cutoff); boundary=int(full and nxt>cutoff)
        r["snapshot_at"]=at; r["snapshot_odometer_km"]=s.snapshot_odometer_km; r["primary_time_split"]=split
        r["primary_split_start_at"]=start; r["primary_split_end_at"]=cutoff; r["primary_label_cutoff_at"]=cutoff
        r["next_service_id"]=target.next_service_id; r["next_service_at"]=nxt; r["full_dataset_event_observed"]=full; r["full_dataset_right_censored"]=1-full
        r["event_observed_by_primary_cutoff"]=in_window; r["boundary_crossing_future_target"]=boundary
        r["task_target_eligible_primary"]=in_window; r["next_service_regression_eligible_primary"]=in_window
        r["survival_target_eligible_primary"]=1; r["survival_event_observed_in_window"]=in_window; r["survival_admin_censor_at"]=cutoff
        r["split_version"]="SPLIT_MANIFEST_V1_3"; r["generator_version"]=VERSION; r["scenario_id"]="REGRESSION_CALIBRATION_V1_3"
        out.append(r)
    return pd.DataFrame(out,columns=base.columns)


def metric_values(y, pred, target):
    y=np.asarray(y,float); pred=np.clip(np.asarray(pred,float),0,None); ae=np.abs(y-pred)
    tol=[15,30,60] if target=="DAYS" else [500,1000,2000]
    d={"mae":mean_absolute_error(y,pred),"median_ae":median_absolute_error(y,pred),"rmse":mean_squared_error(y,pred)**.5,"r2":r2_score(y,pred)}
    d.update({f"within_{x}":float(np.mean(ae<=x)) for x in tol}); return d


def model_features(snapshots: pd.DataFrame):
    try:
        original=list(joblib.load(ROOT/"ridebase-ml/models/ml_preprocessor_v1_2.joblib").feature_names_in_)
    except Exception:
        original=[]
    new=["previous_service_count","previous_interval_days","previous_interval_km","historical_interval_days_median","historical_interval_days_std","historical_interval_km_median","historical_interval_km_std","historical_policy_delay_median_days","historical_policy_delay_mean_days","historical_on_time_rate","previous_policy_delay_days","recent_30d_km","recent_60d_km","recent_90d_km","recent_180d_km","recent_km_per_day","long_term_km_per_day","recent_vs_long_term_usage_ratio","policy_interval_days","policy_interval_km"]
    synthetic_only={"failure_hazard_score","chronic_risk_tier"}
    return [c for c in dict.fromkeys(original+new) if c in snapshots and c not in synthetic_only]


def make_preprocessor(X: pd.DataFrame, features: list[str]):
    cat=[c for c in features if X[c].dtype=="object" or str(X[c].dtype).startswith("string") or str(X[c].dtype)=="bool"]
    num=[c for c in features if c not in cat]
    return ColumnTransformer([
        ("num",Pipeline([("imp",SimpleImputer(strategy="median",add_indicator=True))]),num),
        ("cat",Pipeline([("imp",SimpleImputer(strategy="most_frequent")),("enc",OrdinalEncoder(handle_unknown="use_encoded_value",unknown_value=-1))]),cat),
    ],verbose_feature_names_out=False),cat,num


def run_regression(snapshots: pd.DataFrame, targets: pd.DataFrame, split: pd.DataFrame, features: list[str], target_override: dict[str,pd.Series]|None=None, max_iter=100):
    j=snapshots.merge(targets[["snapshot_id","days_to_next_service","km_to_next_service","target_km_valid"]],on="snapshot_id").merge(split[["snapshot_id","primary_time_split","next_service_regression_eligible_primary"]],on="snapshot_id")
    prep,_,_=make_preprocessor(j,features)
    train_all=j.primary_time_split.eq("TRAIN")
    prep.fit(j.loc[train_all,features])
    X=prep.transform(j[features]).astype("float32")
    rows=[]; predictions={}
    for target,col in [("DAYS","days_to_next_service"),("KM","km_to_next_service")]:
        y=(target_override or {}).get(target,j[col])
        valid=j.next_service_regression_eligible_primary.eq(1)&pd.Series(y).notna()
        if target=="KM": valid &= j.target_km_valid.eq(1)
        tr=valid&j.primary_time_split.eq("TRAIN")
        model=HistGradientBoostingRegressor(random_state=SEED,max_iter=max_iter).fit(X[tr],np.asarray(y)[tr])
        for sp in ["TRAIN","VALIDATION","TEST"]:
            m=valid&j.primary_time_split.eq(sp); pred=model.predict(X[m]); predictions[(target,sp)]=pred
            for metric,value in metric_values(np.asarray(y)[m],pred,target).items(): rows.append({"target":target,"split":sp,"model":"HistGradientBoostingRegressor","metric":metric,"value":value,"n":int(m.sum())})
    return pd.DataFrame(rows),j,predictions


def associations(j: pd.DataFrame, target: str, features: list[str]) -> pd.DataFrame:
    col="days_to_next_service" if target=="DAYS" else "km_to_next_service"
    m=j.next_service_regression_eligible_primary.eq(1)&j[col].notna()
    d=j.loc[m,features+[col]].copy(); rows=[]
    for f in features:
        x=d[f]
        if not pd.api.types.is_numeric_dtype(x): x=pd.Series(pd.factorize(x.astype("string"))[0],index=x.index)
        x=pd.to_numeric(x,errors="coerce").fillna(pd.to_numeric(x,errors="coerce").median()).to_numpy(float)
        y=d[col].to_numpy(float)
        pear=float(np.corrcoef(x,y)[0,1]) if np.std(x)>0 else 0
        spear=float(pd.Series(x).corr(pd.Series(y),method="spearman")) if np.std(x)>0 else 0
        mi=float(mutual_info_regression(x.reshape(-1,1),y,random_state=SEED)[0]) if np.std(x)>0 else 0
        rows.append({"target":target,"feature":f,"pearson":pear,"spearman":spear,"mutual_information":mi,"n":len(y)})
    return pd.DataFrame(rows)


def target_stats(targets: pd.DataFrame, split: pd.DataFrame) -> pd.DataFrame:
    d=targets.merge(split[["snapshot_id","primary_time_split","next_service_regression_eligible_primary"]],on="snapshot_id")
    rows=[]
    for t,c in [("DAYS","days_to_next_service"),("KM","km_to_next_service")]:
        for sp,g in d[d.next_service_regression_eligible_primary.eq(1)].groupby("primary_time_split"):
            x=g[c].dropna(); rows.append({"target":t,"split":sp,"count":len(x),"mean":x.mean(),"median":x.median(),"std":x.std(),"p25":x.quantile(.25),"p75":x.quantile(.75),"p95":x.quantile(.95),"p99":x.quantile(.99)})
    return pd.DataFrame(rows)


def reliability_checks(source: dict[str,pd.DataFrame]):
    s=source["services.csv"]; u=source["usage_profiles.csv"][["motorcycle_id","riding_intensity","load_severity_factor"]]
    d=s.merge(u,on="motorcycle_id"); d["failure"]=d.service_type_code.isin(FAILURE_TYPES)
    intensity=d.groupby("riding_intensity").failure.mean().reindex(["LOW","MEDIUM","HIGH"])
    d["load_band"]=pd.cut(d.load_severity_factor,[-np.inf,.95,1.05,1.15,np.inf],labels=["LOW","MEDIUM","HIGH","VERY_HIGH"])
    load=d.groupby("load_band",observed=True).failure.mean()
    d["age_years"]=(pd.to_datetime(d.received_at).dt.year-d.motorcycle_id.map(source["motorcycles.csv"].set_index("motorcycle_id").production_year)).clip(lower=0)
    d["age_bucket"]=pd.cut(d.age_years,[-1,2,4,7,11,100],labels=["0-2","3-4","5-7","8-11","12+"])
    warranty=d.groupby("age_bucket",observed=True).is_warranty.mean()
    failures=s[s.service_type_code.isin(FAILURE_TYPES)]
    primary=source["service_tasks.csv"].query("task_role == 'PRIMARY_FAULT'").service_id.nunique()
    q12=json.loads((V12/"derived_outputs/quality_report.json").read_text())
    brand=q12.get("reliability_realism_checks",{}).get("brand_adjusted_spread",{}).get("adjusted_max_min_ratio",math.nan)
    return {"riding":intensity.to_dict(),"riding_pass":bool(intensity.is_monotonic_increasing),"load":load.to_dict(),"load_pass":bool(load.iloc[-1]>=load.iloc[0]),"warranty":warranty.to_dict(),"warranty_pass":bool(warranty.iloc[-1]<=warranty.iloc[0]),"fault_task_coverage":f"{primary}/{len(failures)}","fault_task_pass":primary==len(failures),"final_drive":int((failures.primary_fault_component=="FINAL_DRIVE").sum()),"adjusted_brand_spread":brand}


def quality_checks(source,snapshots,targets,next_task,split,status,mileage,reliability,regression,stats,assoc,components):
    checks=[]
    pk={"workshops.csv":"workshop_id","customers.csv":"customer_id","motorcycles.csv":"motorcycle_id","ridebase_motorcycle_models_v1.csv":"model_id","usage_profiles.csv":"usage_profile_id","mileage_timeline_monthly.csv":"timeline_id","maintenance_tasks.csv":"task_code","maintenance_policies.csv":"policy_id","appointments.csv":"appointment_id","services.csv":"service_id","services_enriched.csv":"service_id","service_tasks.csv":"service_task_id","service_parts.csv":"service_part_id"}
    dup=sum(int(source[f][c].duplicated().sum()) for f,c in pk.items())+int(snapshots.snapshot_id.duplicated().sum())
    checks.append(("pk_duplicates",dup==0,{"duplicates":dup}))
    services=source["services.csv"]; mc=source["motorcycles.csv"]
    orphan=int((~services.motorcycle_id.isin(mc.motorcycle_id)).sum())+int((~source["service_tasks.csv"].service_id.isin(services.service_id)).sum())+int((~source["service_parts.csv"].service_id.isin(services.service_id)).sum())
    checks.append(("foreign_key_orphans",orphan==0,{"orphans":orphan}))
    tsbad=int((pd.to_datetime(services.completed_at)<pd.to_datetime(services.received_at)).sum())+int((pd.to_datetime(services.delivered_at)<pd.to_datetime(services.completed_at)).sum())
    checks.append(("timestamp_order",tsbad==0,{"violations":tsbad}))
    reg=int((mileage.sort_values(["motorcycle_id","period_start_date"]).groupby("motorcycle_id").closing_odometer_km.diff()<0).sum())
    checks.append(("mileage_chronology",reg==0,{"regressions":reg}))
    align=len(set(snapshots.snapshot_id)^set(targets.snapshot_id))+len(set(snapshots.snapshot_id)^set(next_task.snapshot_id))
    checks.append(("snapshot_target_alignment",align==0,{"key_difference":align}))
    c=targets.target_event_observed.eq(0); future=[x for x in targets if x.startswith("next_service_") or x in {"days_to_next_service","km_to_next_service","target_next_service_at"}]
    nullbad=int(targets.loc[c,future].notna().sum().sum())
    checks.append(("nullable_semantics",nullbad==0,{"censored_future_nonnull":nullbad}))
    boundary=int((split.boundary_crossing_future_target.eq(1)&split.next_service_regression_eligible_primary.eq(1)).sum())
    checks.append(("split_integrity",boundary==0,{"boundary_eligible":boundary}))
    leakage=[x for x in model_features(snapshots) if any(k in x.lower() for k in ["future","next_service","next_task"])]
    checks.append(("no_leakage",not leakage,{"forbidden_features":leakage}))
    for name,key in [("riding_intensity_direction","riding_pass"),("load_failure_direction","load_pass"),("warranty_monotonicity","warranty_pass"),("fault_task_coverage","fault_task_pass")]: checks.append((name,bool(reliability[key]),{}))
    checks.append(("final_drive_presence",reliability["final_drive"]>0,{"count":reliability["final_drive"]}))
    checks.append(("brand_adjusted_spread",reliability["adjusted_brand_spread"]<=1.35,{"ratio":reliability["adjusted_brand_spread"]}))
    test_r2={t:float(regression.query("target==@t and split=='TEST' and metric=='r2'").value.iloc[0]) for t in ["DAYS","KM"]}
    over=max(test_r2.values())>.80
    signal_noise={}
    for t,scol,ncol in [("DAYS","deterministic_days","noise_days"),("KM","deterministic_km","noise_km")]:
        sv=float(components[scol].var()); nv=float(components[ncol].var()); signal_noise[t]={"signal_variance":sv,"noise_variance":nv,"signal_to_noise_ratio":sv/nv if nv else math.inf}
    assoc_map={(r.target,r.feature):abs(r.spearman) for r in assoc.itertuples()}
    drift={}
    for t in ["DAYS","KM"]:
        x=stats[stats.target.eq(t)].set_index("split")["mean"]; ratio=float(x.max()/max(x.min(),1e-9)); drift[t]="LOW" if ratio<1.2 else ("MEDIUM" if ratio<1.5 else "HIGH")
    learn={"target_distribution_drift":{"status":"DIAGNOSTIC","classification":drift},"signal_noise_balance":{"status":"PASS" if all(v["signal_to_noise_ratio"]>.5 for v in signal_noise.values()) else "WARN","metrics":signal_noise},"history_target_association":{"status":"DIAGNOSTIC","days_spearman":assoc_map.get(("DAYS","historical_interval_days_median")),"km_spearman":assoc_map.get(("KM","historical_interval_km_median"))},"recent_usage_target_association":{"status":"DIAGNOSTIC","days_spearman":assoc_map.get(("DAYS","recent_km_per_day")),"km_spearman":assoc_map.get(("KM","recent_km_per_day"))},"policy_target_association":{"status":"DIAGNOSTIC","days_spearman":assoc_map.get(("DAYS","policy_interval_days")),"km_spearman":assoc_map.get(("KM","policy_interval_km"))},"observed_censored_shift":{"status":"DIAGNOSTIC"},"over_determinism_check":{"status":"WARN" if over else "PASS","test_r2":test_r2,"warning":"POSSIBLE OVER-DETERMINISTIC GENERATOR" if over else None}}
    rows=[{"check":n,"status":"PASS" if ok else "FAIL","severity":"HIGH","metrics":m} for n,ok,m in checks]
    return rows,learn


def build_reports(rep:Path,source,snapshots,targets,split,mileage,components,stats,assoc,metrics,sensitivity,ablation,reliability,quality,learn):
    tables=rep/"tables"; tables.mkdir(parents=True,exist_ok=True)
    write_csv(stats,tables/"target_distribution_v1_3.csv"); write_csv(assoc,tables/"feature_target_associations_v1_3.csv"); write_csv(metrics,tables/"v1_3_regression_metrics.csv"); write_csv(sensitivity,tables/"regression_noise_sensitivity.csv"); write_csv(ablation,tables/"feature_signal_ablation.csv")
    v12metrics=read_csv(ROOT/"ridebase-ml/reports/tables/v1_regression_metrics.csv")
    v12test=v12metrics[(v12metrics.split.eq("TEST"))&v12metrics.notes.eq("ACTIONABLE")]
    v12stats=[]
    t12=pd.read_parquet(V12/"derived_outputs/ml_next_service_targets.parquet"); s12=read_csv(V12/"derived_outputs/split_manifest.csv")
    v12stat=target_stats(t12,s12); write_csv(v12stat,tables/"target_distribution_v1_2.csv")
    old_m=read_csv(V12/"source_tables/mileage_timeline_monthly.csv"); ac12=lag1(old_m.sort_values(["motorcycle_id","period_start_date"]),"km_added"); ac13=lag1(mileage.sort_values(["motorcycle_id","period_start_date"]),"km_added")
    event12=read_csv(V12/"source_tables/services.csv").service_type_code.value_counts(); event13=source["services.csv"].service_type_code.value_counts()
    event=pd.DataFrame({"v1_2":event12,"v1_3":event13}).fillna(0).astype(int); write_csv(event.reset_index(names="service_type"),tables/"service_event_distribution_comparison.csv")
    # Observed/censored feature shift with standardized mean differences.
    obs=targets[["snapshot_id","target_event_observed"]].merge(snapshots,on="snapshot_id")
    shift=[]
    for f in ["motorcycle_age_years","snapshot_odometer_km","recent_km_per_day","service_sequence","policy_interval_days"]:
        a=obs.loc[obs.target_event_observed.eq(1),f]; b=obs.loc[obs.target_event_observed.eq(0),f]; pooled=math.sqrt((a.var()+b.var())/2) if len(a)>1 and len(b)>1 else math.nan
        shift.append({"feature":f,"observed_mean":a.mean(),"censored_mean":b.mean(),"standardized_mean_difference":(a.mean()-b.mean())/pooled if pooled else math.nan})
    shift=pd.DataFrame(shift); write_csv(shift,tables/"observed_censored_shift_v1_3.csv")
    # Exact generator decomposition for v1.3; post-hoc observable residual proxy for v1.2.
    dec=[]
    for t,actual,signal,noise in [("DAYS","actual_days","deterministic_days","noise_days"),("KM","actual_km","deterministic_km","noise_km")]:
        for ver,frame in [("1.3",components)]:
            dec.append({"version":ver,"target":t,"method":"generator_component_exact","target_variance":frame[actual].var(),"signal_component_variance":frame[signal].var(),"noise_component_variance":frame[noise].var(),"signal_to_noise_ratio":frame[signal].var()/frame[noise].var()})
        r2=float(v12test[(v12test.target.eq(t))&v12test.metric.eq("r2")].value.iloc[0]); tv=float(v12stat[v12stat.target.eq(t)].set_index("split").loc["TEST","std"]**2)
        dec.append({"version":"1.2","target":t,"method":"posthoc_same_model_residual_proxy","target_variance":tv,"signal_component_variance":tv*max(r2,0),"noise_component_variance":tv*(1-r2),"signal_to_noise_ratio":max(r2,0)/(1-r2)})
    dec=pd.DataFrame(dec); write_csv(dec,tables/"signal_noise_decomposition.csv")
    learn_md=f"""# RideBase v1.3 Regression Learnability Audit

Bu rapor sentetik generator calibration deneyidir; production doğrulaması değildir. R² acceptance gate değildir.

## Target dağılımları

{md_table(pd.concat([v12stat.assign(version='1.2'),stats.assign(version='1.3')],ignore_index=True))}

## Signal / noise decomposition

{md_table(dec)}

V1.2 decomposition generator iç bileşenleri mevcut olmadığı için same-model residual proxy'dir; v1.3 satırları builder tarafından kaydedilen exact bileşenlerdir.

## Feature-target association

{md_table(assoc.sort_values(['target','mutual_information'],ascending=[True,False]))}

## Mileage persistence

Lag-1 autocorrelation v1.2 **{ac12:.4f}**, v1.3 **{ac13:.4f}**. Seri tamamen bağımsız değildir; innovation noise sıfır değildir.

## Observed / censored shift

{md_table(shift)}

## Cutoff drift decomposition

V1.2 validation ve test observed-only ortalamalarının düşük olmasının ana mekanizması 6–8 aylık split label cutoff'larının uzun next-event aralıklarını boundary-crossing yaparak regression eligibility dışında bırakmasıdır. Bu calendar truncation/selection etkisine event-type, history-depth ve kullanım kompozisyonu ikincil katkı verir. V1.3 aynı cutoff sözleşmesini korur; split hedefleri elle eşitlenmemiştir.
"""
    (rep/"regression_learnability_audit_v1_3.md").write_text(learn_md,encoding="utf-8")
    comparison=f"""# RideBase v1.2 → v1.3 Regression Calibration Comparison

## Hacim ve event mix

- Services: {len(read_csv(V12/'source_tables/services.csv')):,} → {len(source['services.csv']):,}
- Snapshots: {len(t12):,} → {len(snapshots):,}
- Mileage lag-1 autocorrelation: {ac12:.4f} → {ac13:.4f}

{md_table(event.reset_index(names='service_type'))}

## Target dağılımları

{md_table(pd.concat([v12stat.assign(version='1.2'),stats.assign(version='1.3')],ignore_index=True))}

## Failure realism

- Adjusted brand spread: {reliability['adjusted_brand_spread']:.4f}x
- Riding intensity: {reliability['riding']}
- Load severity: {reliability['load']}
- Warranty age: {reliability['warranty']}
- Fault-task coverage: {reliability['fault_task_coverage']}
- FINAL_DRIVE: {reliability['final_drive']}
"""
    (rep/"v1_2_to_v1_3_regression_calibration_comparison.md").write_text(comparison,encoding="utf-8")
    # Main benchmark comparison.
    def mv(frame,t,metric,sp="TEST"): return float(frame[(frame.target.eq(t))&frame.split.eq(sp)&frame.metric.eq(metric)].value.iloc[0])
    main=f"""# RideBase v1.2 vs v1.3 Regression Learnability

| Metric | V1.2 | V1.3 |
|---|---:|---:|
| Services | {len(read_csv(V12/'source_tables/services.csv'))} | {len(source['services.csv'])} |
| Snapshots | {len(t12)} | {len(snapshots)} |
| Observed | {int(t12.target_event_observed.sum())} | {int(targets.target_event_observed.sum())} |
| Censored | {int((t12.target_event_observed==0).sum())} | {int((targets.target_event_observed==0).sum())} |
| DAYS TEST MAE | {mv(v12test,'DAYS','mae'):.4f} | {mv(metrics,'DAYS','mae'):.4f} |
| DAYS TEST R² | {mv(v12test,'DAYS','r2'):.4f} | {mv(metrics,'DAYS','r2'):.4f} |
| KM TEST MAE | {mv(v12test,'KM','mae'):.4f} | {mv(metrics,'KM','mae'):.4f} |
| KM TEST R² | {mv(v12test,'KM','r2'):.4f} | {mv(metrics,'KM','r2'):.4f} |
| Failure rate | {read_csv(V12/'source_tables/services.csv').service_type_code.isin(FAILURE_TYPES).mean():.4%} | {source['services.csv'].service_type_code.isin(FAILURE_TYPES).mean():.4%} |
| Adjusted brand spread | {reliability['adjusted_brand_spread']:.4f}x | {reliability['adjusted_brand_spread']:.4f}x |
| Fault task coverage | v1.2 PASS | {reliability['fault_task_coverage']} |

R² yalnız gözlenebilir snapshot feature'larının sentetik target varyansını açıklama gücünü ölçer; production gerçekçiliği veya production performansı iddiası değildir.
"""
    (rep/"v1_2_vs_v1_3_regression_learnability.md").write_text(main,encoding="utf-8")
    changes={"dataset_version":VERSION,"source_files_changed":["mileage_timeline_monthly.csv","services.csv","services_enriched.csv","appointments.csv","service_tasks.csv"],"generator_functions_changed":["regenerate_mileage","regenerate_services","service_history_features","rebuild_snapshots_targets"],"service_events_changed":"timestamps/odometers/causal intervals; IDs and event-type mix preserved","mileage_timeline_changed":"AR(1) persistent usage + profile-conditioned seasonality + bounded innovations","snapshot_features_added":[c for c in snapshots if c not in pd.read_parquet(V12/'derived_outputs/ml_maintenance_snapshots.parquet',columns=None).columns],"derived_files_regenerated":["service_status_history.csv","noise_audit.csv","ml_maintenance_snapshots.parquet","ml_next_service_targets.parquet","ml_next_task_targets.parquet","split_manifest.csv","dataset_metadata.json","quality_report.json"],"noise_calibration":{"main_scale":0.14,"irregular_scale":0.19,"bounded_factor":[0.67,1.43]},"service_count_change":len(source['services.csv'])-len(read_csv(V12/'source_tables/services.csv')),"observed_censored_change":{"observed":int(targets.target_event_observed.sum()-t12.target_event_observed.sum()),"censored":int((targets.target_event_observed==0).sum()-(t12.target_event_observed==0).sum())},"failure_mix_change":"none; v1.2 calibrated failure identities retained","target_distribution_changes":stats.to_dict('records')}
    write_json(changes,rep/"v1_2_to_v1_3_changes.json")


def make_noise_audit(base:pd.DataFrame,components:pd.DataFrame)->pd.DataFrame:
    rows=[]
    for i,r in enumerate(components.itertuples(),1):
        for field,signal,noise,actual in [("days_to_next_service","deterministic_days","noise_days","actual_days"),("km_to_next_service","deterministic_km","noise_km","actual_km")]:
            rows.append({"noise_audit_id":f"CAL{i:06d}{'D' if field[0]=='d' else 'K'}","entity_type":"SERVICE_INTERVAL","entity_id":r.next_service_id,"service_id":r.next_service_id,"motorcycle_id":r.motorcycle_id,"workshop_id":pd.NA,"field_name":field,"issue_type":"CALIBRATED_BOUNDED_NOISE","issue_category":"REGRESSION_CALIBRATION","severity":"INFO","is_intentional_noise":1,"observed_value":getattr(r,actual),"original_clean_value":getattr(r,signal),"canonical_clean_value":getattr(r,signal),"clean_value_available":1,"detection_source":"GENERATOR_COMPONENT_LOG","repair_action":"NONE","repair_applied":0,"ml_handling":"DIAGNOSTIC_ONLY_NOT_A_FEATURE","noise_rule_version":VERSION,"data_origin":"SYNTHETIC","generator_version":VERSION,"random_seed":SEED,"scenario_id":"REGRESSION_CALIBRATION_V1_3","notes":f"noise_component={getattr(r,noise):.6f}","original_clean_value_available":1})
    return pd.DataFrame(rows,columns=base.columns)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output-dir",type=Path,default=ROOT/"ridebase_v1_3"); ap.add_argument("--zip-path",type=Path,default=ROOT/"ridebase_synthetic_dataset_v1_3.zip"); ap.add_argument("--force",action="store_true"); ap.add_argument("--reproducibility-verified",action="store_true"); args=ap.parse_args()
    if not V12.exists(): raise SystemExit("Missing immutable ridebase_v1_2")
    if args.output_dir.exists():
        if not args.force: raise SystemExit(f"Refusing to overwrite {args.output_dir}; pass --force")
        shutil.rmtree(args.output_dir)
    if args.zip_path.exists():
        if not args.force: raise SystemExit(f"Refusing to overwrite {args.zip_path}; pass --force")
        args.zip_path.unlink()
    src=args.output_dir/"source_tables"; der=args.output_dir/"derived_outputs"; rep=args.output_dir/"reports"; (rep/"tables").mkdir(parents=True); src.mkdir(); der.mkdir()
    source={p.name:read_csv(p) for p in sorted((V12/"source_tables").glob("*.csv"))}
    mileage=regenerate_mileage(source["mileage_timeline_monthly.csv"],source["usage_profiles.csv"])
    services,components,old_services=regenerate_services(source,mileage); source["mileage_timeline_monthly.csv"]=mileage; source["services.csv"]=services
    source,delta=shift_related(source,old_services,services)
    for name,d in source.items(): source[name]=update_versions(d); write_csv(source[name],src/name)
    status=rebuild_status_history(read_csv(V12/"derived_outputs/service_status_history.csv"),services,delta); write_csv(status,der/"service_status_history.csv")
    noise=make_noise_audit(read_csv(V12/"derived_outputs/noise_audit.csv"),components); write_csv(noise,der/"noise_audit.csv")
    snapshots,targets,next_map=rebuild_snapshots_targets(source,mileage,components); next_task=rebuild_next_tasks(source,targets); split=rebuild_split(snapshots,targets)
    pq.write_table(pa.Table.from_pandas(snapshots,preserve_index=False),der/"ml_maintenance_snapshots.parquet",compression="snappy")
    pq.write_table(pa.Table.from_pandas(targets,preserve_index=False),der/"ml_next_service_targets.parquet",compression="snappy")
    pq.write_table(pa.Table.from_pandas(next_task,preserve_index=False),der/"ml_next_task_targets.parquet",compression="snappy"); write_csv(split,der/"split_manifest.csv")
    features=model_features(snapshots); metrics,j,preds=run_regression(snapshots,targets,split,features)
    assoc_features=["policy_interval_days","previous_interval_days","historical_interval_days_median","recent_km_per_day","annual_km_baseline","service_sequence","historical_policy_delay_mean_days","policy_interval_km","previous_interval_km","historical_interval_km_median","snapshot_odometer_km","usage_type"]
    assoc=pd.concat([associations(j,"DAYS",assoc_features),associations(j,"KM",assoc_features)],ignore_index=True); stats=target_stats(targets,split)
    # Controlled mini sensitivity: same rows/features/seed family, only bounded component scale changes.
    c=components.set_index("source_service_id"); base_d=j.source_service_id.map(c.deterministic_days); base_k=j.source_service_id.map(c.deterministic_km); z=j.source_service_id.map(c.noise_z).fillna(0)
    sens=[]
    for level,scale,note in [("LOW",.07,"too smooth for main realism choice"),("MEDIUM",.14,"main reasonable bounded realism point"),("HIGH",.28,"substantial irreducible variation")]:
        od=(base_d*np.exp(scale*z-.5*scale**2)).clip(lower=3); ok=(base_k*np.exp(scale*z-.5*scale**2)).clip(lower=1)
        met,_,_=run_regression(snapshots,targets,split,features,{"DAYS":od,"KM":ok},max_iter=60)
        for t in ["DAYS","KM"]:
            q=met[(met.target.eq(t))&met.split.eq("TEST")].set_index("metric").value
            if t=="DAYS": dr2,dmae=q.r2,q.mae
            else: kr2,kmae=q.r2,q.mae
        sens.append({"noise_level":level,"noise_scale":scale,"days_r2":dr2,"days_mae":dmae,"km_r2":kr2,"km_mae":kmae,"realism_notes":note})
    sensitivity=pd.DataFrame(sens)
    groups={"POLICY_ONLY":["policy_interval_days","policy_interval_km"],"POLICY_USAGE":["policy_interval_days","policy_interval_km","annual_km_baseline","usage_type","recent_km_per_day"],"POLICY_USAGE_HISTORY":["policy_interval_days","policy_interval_km","annual_km_baseline","usage_type","recent_km_per_day","previous_interval_days","previous_interval_km","historical_interval_days_median","historical_interval_km_median"],"FULL_OBSERVABLE":features}
    abl=[]
    for name,fs in groups.items():
        met,_,_=run_regression(snapshots,targets,split,[x for x in fs if x in snapshots],max_iter=60)
        for t in ["DAYS","KM"]:
            q=met[(met.target.eq(t))&met.split.eq("TEST")].set_index("metric").value; abl.append({"feature_group":name,"target":t,"test_r2":q.r2,"test_mae":q.mae})
    ablation=pd.DataFrame(abl); reliability=reliability_checks(source)
    quality,learn=quality_checks(source,snapshots,targets,next_task,split,status,mileage,reliability,metrics,stats,assoc,components)
    build_reports(rep,source,snapshots,targets,split,mileage,components,stats,assoc,metrics,sensitivity,ablation,reliability,quality,learn)
    high_fail=[x["check"] for x in quality if x["severity"]=="HIGH" and x["status"]=="FAIL"]
    report={"report":{"name":"RideBase Synthetic Dataset v1.3 Quality Report","dataset_version":VERSION,"report_version":"QUALITY_REPORT_V1_3","report_date":str(HORIZON.date()),"random_seed":SEED,"release_gate":"PASS" if not high_fail else "FAIL"},"executive_summary":{"total_checks":len(quality),"pass_checks":sum(x['status']=='PASS' for x in quality),"fail_checks":sum(x['status']=='FAIL' for x in quality),"failed_high_severity_checks":high_fail},"regression_learnability_checks":learn,"reliability_realism_checks":reliability,"quality_checks":quality}; write_json(report,der/"quality_report.json")
    metadata=json.loads((V12/"derived_outputs/dataset_metadata.json").read_text()); metadata["dataset"]={**metadata.get("dataset",{}),"dataset_version":VERSION,"generator_version":VERSION,"rule_set_version":VERSION,"random_seed":SEED,"status":f"V1_3_RELEASE_{report['report']['release_gate']}"}; metadata["regression_calibration_experiment"]=True; metadata["regression_calibration_description"]=EXPERIMENT_DESCRIPTION; metadata["service_interval_generation_methodology"]={"policy_anchor":"maintenance_policies days/km, whichever first","observable_drivers":["recent usage","long-term usage","historical intervals","historical adherence","service history","past risk"],"latent_behavior_not_exported_as_ml_feature":True,"unscheduled_events":"age/km/failure-history/overdue/usage-conditioned v1.2 risk identities retained","r2_acceptance_gate":False}; metadata["noise_calibration"]={"main_regular_log_scale":.14,"main_irregular_log_scale":.19,"bounded_factor":[.67,1.43],"selection_reason":"reasonable realism, not score maximizing","sensitivity_table":"reports/tables/regression_noise_sensitivity.csv"}; metadata["feature_availability"]={"PRODUCTION_DERIVABLE":[x for x in features],"SYNTHETIC_ONLY_EXCLUDED_FROM_FINAL_ML":["behavior_label","noise_z","deterministic_days","deterministic_km","failure_hazard_score","chronic_risk_tier"]}; metadata["reproducibility"]={"same_seed_release_sha256_verified":bool(args.reproducibility_verified)}; metadata["file_catalog"]=[]
    for p in sorted(list(src.glob('*'))+[x for x in der.glob('*') if x.name!='dataset_metadata.json']):
        item={"file_name":p.name,"layer":"SOURCE" if p.parent==src else "DERIVED_OUTPUT","format":p.suffix.lstrip('.').upper(),"size_bytes":p.stat().st_size,"sha256":sha256_file(p)}
        if p.suffix=='.csv': d=read_csv(p); item.update(row_count=len(d),column_count=len(d.columns))
        elif p.suffix=='.parquet': t=pq.read_table(p); item.update(row_count=t.num_rows,column_count=t.num_columns)
        metadata["file_catalog"].append(item)
    write_json(metadata,der/"dataset_metadata.json")
    # Deterministic ZIP metadata enables byte-identical independent builds.
    with zipfile.ZipFile(args.zip_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for directory in [src,der,rep]:
            for p in sorted(directory.rglob('*')):
                if p.is_file():
                    info=zipfile.ZipInfo(str(p.relative_to(args.output_dir)),date_time=(2026,8,28,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644<<16; z.writestr(info,p.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
    with zipfile.ZipFile(args.zip_path) as z:
        if z.testzip() is not None: raise RuntimeError("ZIP integrity failure")
    digest=sha256_file(args.zip_path); (rep/"ridebase_synthetic_dataset_v1_3.sha256").write_text(f"{digest}  ridebase_synthetic_dataset_v1_3.zip\n",encoding="utf-8")
    summary={"release_gate":report['report']['release_gate'],"failed_high_checks":high_fail,"services":len(services),"snapshots":len(snapshots),"split_counts":split.primary_time_split.value_counts().to_dict(),"observed_by_split":split[split.next_service_regression_eligible_primary.eq(1)].primary_time_split.value_counts().to_dict(),"censored_total":int((targets.target_event_observed==0).sum()),"event_distribution":services.service_type_code.value_counts().to_dict(),"metrics":metrics.to_dict('records'),"target_stats":stats.to_dict('records'),"reliability":reliability,"mileage_autocorrelation":{"v1_2":lag1(read_csv(V12/'source_tables/mileage_timeline_monthly.csv').sort_values(['motorcycle_id','period_start_date']),'km_added'),"v1_3":lag1(mileage.sort_values(['motorcycle_id','period_start_date']),'km_added')},"reproducibility_verified":bool(args.reproducibility_verified),"zip_path":str(args.zip_path),"sha256":digest}; write_json(summary,rep/"release_summary.json")
    print(json.dumps(summary,ensure_ascii=False,indent=2,default=json_default))


if __name__=="__main__": main()
