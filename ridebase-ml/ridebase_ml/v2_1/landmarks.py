"""Build the V2.1 monthly dynamic-landmark dataset from frozen v1.3 sources.

The source layer is strictly read-only.  Every field created here is written to
the V2.1 derived-output namespace and represents information available at the
end of a mileage month.  Survival time starts at that landmark, not at a prior
service event.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .schema_contract import assert_source_schema_contract


IDENTIFIER_COLUMNS = [
    "landmark_id", "motorcycle_id", "customer_id", "workshop_id", "model_id",
    "landmark_at", "source_last_service_id",
]

CATEGORICAL_FEATURES = [
    "brand", "category", "powertrain_type", "policy_group", "customer_type",
    "usage_type", "riding_intensity", "climate_zone", "storage_condition",
    "workshop_region", "workshop_price_level", "last_service_type_code",
    "last_arrival_mode",
]

NUMERIC_FEATURES = [
    "production_age_days", "ownership_age_days", "is_fleet_customer",
    "current_odometer_km_at_landmark", "annual_km_baseline", "recent_90d_km",
    "recent_vs_baseline_usage_ratio", "days_since_last_service",
    "km_since_last_service", "avg_km_per_day_since_last_service",
    "oem_interval_days", "oem_interval_km", "days_due_ratio", "km_due_ratio",
    "max_due_ratio", "days_overdue", "km_overdue", "maintenance_due_now",
    "due_task_count", "days_until_next_scheduled_due", "km_until_next_scheduled_due",
    "recent_service_count_90d", "recent_service_count_365d",
    "prior_service_count", "prior_periodic_service_count", "prior_breakdown_count",
    "prior_repair_count", "historical_service_delay_mean_days",
    "historical_on_time_rate", "cumulative_service_spend",
    "last_service_was_breakdown", "last_service_was_warranty",
    "last_service_task_count", "last_service_spend", "service_bay_count",
    "appointment_rate", "avg_parts_lead_days", "customer_volume_index",
    "landmark_month_sin", "landmark_month_cos",
]

FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET_COLUMNS = [
    "landmark_id", "duration_days", "event_observed", "next_service_id",
    "administrative_cutoff_at", "event_within_30d", "event_within_60d",
    "event_within_90d", "event_within_120d",
]

FORBIDDEN_FEATURE_TOKENS = (
    "split", "censor", "event_observed", "next_service", "target", "future_",
    "duration_days", "snapshot_year", "landmark_year", "days_observed",
    "current_service_", "source_service_id",
)


@dataclass(frozen=True)
class LandmarkPaths:
    repo_root: Path
    source_dir: Path
    output_dir: Path
    config_path: Path
    schema_contract_path: Path

    @classmethod
    def from_repo(cls, repo_root: Path) -> "LandmarkPaths":
        root = Path(repo_root).resolve()
        return cls(
            repo_root=root,
            source_dir=root / "ridebase_v1_3" / "source_tables",
            output_dir=root / "ridebase-ml" / "derived_outputs" / "v2_1",
            config_path=root / "ridebase-ml" / "config" / "v2_1_landmark_config.json",
            schema_contract_path=root / "ridebase-ml" / "config" / "source_schema_contract_v1_3.json",
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _read_sources(source_dir: Path) -> Dict[str, pd.DataFrame]:
    wanted = {
        "motorcycles", "customers", "services", "service_tasks", "usage_profiles",
        "workshops", "mileage_timeline_monthly", "ridebase_motorcycle_models_v1",
        "maintenance_policies", "maintenance_tasks",
    }
    return {
        name: pd.read_csv(source_dir / f"{name}.csv", low_memory=False)
        for name in wanted
    }


def _primary_policy_table(models: pd.DataFrame, policies: pd.DataFrame) -> pd.DataFrame:
    active = policies.loc[
        (policies["is_generator_active"].astype(str).isin(["1", "True", "true"]))
        & (policies["policy_kind"] == "SCHEDULED")
    ].copy()
    rows = []
    for model in models.to_dict("records"):
        exact = active.loc[(active["scope_type"] == "MODEL") & (active["model_id"] == model["model_id"])]
        group = active.loc[(active["scope_type"] == "GROUP") & (active["policy_group"] == model["policy_group"])]
        candidates = pd.concat([exact, group], ignore_index=True)
        preferred = "ENGINE_OIL_CHANGE" if model["powertrain_type"] == "ICE" else "GENERAL_SAFETY_INSPECTION"
        chosen = candidates.loc[candidates["task_code"] == preferred]
        if chosen.empty:
            chosen = candidates.loc[
                candidates["recurring_km"].notna() | candidates["recurring_months"].notna()
            ].sort_values(["precedence", "recurring_km"], na_position="last")
        if chosen.empty:
            rows.append({"model_id": model["model_id"], "primary_policy_id": None})
            continue
        row = chosen.sort_values(
            ["scope_type", "precedence"], ascending=[False, True]
        ).iloc[0]
        rows.append({
            "model_id": model["model_id"],
            "primary_policy_id": row["policy_id"],
            "primary_task_code": row["task_code"],
            "oem_interval_km": row["recurring_km"] if pd.notna(row["recurring_km"]) else row["initial_trigger_km"],
            "oem_interval_days": (
                float(row["recurring_months"] if pd.notna(row["recurring_months"]) else row["initial_trigger_months"])
                * 30.4375
                if pd.notna(row["recurring_months"]) or pd.notna(row["initial_trigger_months"])
                else np.nan
            ),
            "primary_trigger_mode": row["trigger_mode"],
            "primary_policy_evidence_level": row["evidence_level"],
        })
    return pd.DataFrame(rows)


def _applicable_policies(model_id: str, policy_group: str, policies: pd.DataFrame) -> pd.DataFrame:
    active = policies.loc[
        (policies["is_generator_active"].astype(str).isin(["1", "True", "true"]))
        & (policies["policy_kind"] == "SCHEDULED")
        & (
            ((policies["scope_type"] == "MODEL") & (policies["model_id"] == model_id))
            | ((policies["scope_type"] == "GROUP") & (policies["policy_group"] == policy_group))
        )
    ].copy()
    if active.empty:
        return active
    # Model-specific rows take precedence for the same task.
    active["_scope_rank"] = (active["scope_type"] == "MODEL").astype(int)
    return (
        active.sort_values(["task_code", "_scope_rank", "precedence"], ascending=[True, False, True])
        .drop_duplicates("task_code", keep="first")
        .drop(columns="_scope_rank")
    )


def _asof_join_landmarks(landmarks: pd.DataFrame, services: pd.DataFrame) -> pd.DataFrame:
    left = landmarks.sort_values(["landmark_at", "motorcycle_id"]).copy()
    right = services.sort_values(["service_at", "motorcycle_id"]).copy()
    past = pd.merge_asof(
        left, right, by="motorcycle_id", left_on="landmark_at", right_on="service_at",
        direction="backward", allow_exact_matches=True,
    )
    future_cols = services[["motorcycle_id", "service_at", "service_id"]].rename(
        columns={"service_at": "next_service_at", "service_id": "next_service_id"}
    ).sort_values(["next_service_at", "motorcycle_id"])
    joined = pd.merge_asof(
        past.sort_values(["landmark_at", "motorcycle_id"]), future_cols,
        by="motorcycle_id", left_on="landmark_at", right_on="next_service_at",
        direction="forward", allow_exact_matches=False,
    )
    return joined.sort_values(["motorcycle_id", "landmark_at"]).reset_index(drop=True)


def _history_features(frame: pd.DataFrame, services: pd.DataFrame) -> pd.DataFrame:
    numeric = {
        "recent_service_count_90d": np.zeros(len(frame), dtype=np.int32),
        "recent_service_count_365d": np.zeros(len(frame), dtype=np.int32),
        "prior_service_count": np.zeros(len(frame), dtype=np.int32),
        "prior_periodic_service_count": np.zeros(len(frame), dtype=np.int32),
        "prior_breakdown_count": np.zeros(len(frame), dtype=np.int32),
        "prior_repair_count": np.zeros(len(frame), dtype=np.int32),
        "historical_service_delay_mean_days": np.full(len(frame), np.nan),
        "historical_on_time_rate": np.full(len(frame), np.nan),
        "cumulative_service_spend": np.zeros(len(frame), dtype=float),
    }
    service_groups = {key: group.sort_values("service_at") for key, group in services.groupby("motorcycle_id")}
    for motorcycle_id, landmarks in frame.groupby("motorcycle_id", sort=False):
        svc = service_groups.get(motorcycle_id)
        if svc is None or svc.empty:
            continue
        positions = landmarks.index.to_numpy()
        lm_days = landmarks["landmark_at"].values.astype("datetime64[D]")
        svc_days = svc["service_at"].values.astype("datetime64[D]")
        right = np.searchsorted(svc_days, lm_days, side="right")
        left90 = np.searchsorted(svc_days, lm_days - np.timedelta64(89, "D"), side="left")
        left365 = np.searchsorted(svc_days, lm_days - np.timedelta64(364, "D"), side="left")
        numeric["recent_service_count_90d"][positions] = right - left90
        numeric["recent_service_count_365d"][positions] = right - left365
        numeric["prior_service_count"][positions] = right

        types = svc["service_type_code"].astype(str).to_numpy()
        delay = svc["service_delay_days"].fillna(0.0).to_numpy(float)
        spend = svc["grand_total"].fillna(0.0).to_numpy(float)
        for out_idx, count in zip(positions, right):
            prefix_types = types[:count]
            numeric["prior_periodic_service_count"][out_idx] = int(np.sum(prefix_types == "PERIODIC"))
            numeric["prior_breakdown_count"][out_idx] = int(np.sum(prefix_types == "BREAKDOWN"))
            numeric["prior_repair_count"][out_idx] = int(np.sum(prefix_types == "REPAIR"))
            if count:
                numeric["historical_service_delay_mean_days"][out_idx] = float(np.mean(delay[:count]))
                numeric["historical_on_time_rate"][out_idx] = float(np.mean(delay[:count] <= 0.0))
                numeric["cumulative_service_spend"][out_idx] = float(np.sum(spend[:count]))
    for name, values in numeric.items():
        frame[name] = values
    return frame


def _due_task_features(
    frame: pd.DataFrame,
    services: pd.DataFrame,
    task_events: pd.DataFrame,
    policies: pd.DataFrame,
) -> pd.DataFrame:
    due_count = np.zeros(len(frame), dtype=np.int16)
    min_days = np.full(len(frame), np.nan)
    min_km = np.full(len(frame), np.nan)
    svc_groups = {key: group for key, group in services.groupby("motorcycle_id")}
    task_groups = {
        key: group.sort_values("task_at")
        for key, group in task_events.groupby(["motorcycle_id", "task_code"])
    }
    for motorcycle_id, landmarks in frame.groupby("motorcycle_id", sort=False):
        positions = landmarks.index.to_numpy()
        lm_days = landmarks["landmark_at"].values.astype("datetime64[D]")
        lm_odo = landmarks["current_odometer_km_at_landmark"].to_numpy(float)
        model_id = str(landmarks["model_id"].iloc[0])
        policy_group = str(landmarks["policy_group"].iloc[0])
        applicable = _applicable_policies(model_id, policy_group, policies)
        if applicable.empty:
            continue
        observation_start = landmarks["observation_start_date"].iloc[0].to_datetime64().astype("datetime64[D]")
        initial_odo = float(landmarks["initial_mileage_km"].iloc[0])
        for policy in applicable.to_dict("records"):
            recurring_km = policy["recurring_km"] if pd.notna(policy["recurring_km"]) else policy["initial_trigger_km"]
            recurring_days = (
                float(policy["recurring_months"] if pd.notna(policy["recurring_months"]) else policy["initial_trigger_months"])
                * 30.4375
                if pd.notna(policy["recurring_months"]) or pd.notna(policy["initial_trigger_months"])
                else np.nan
            )
            if pd.isna(recurring_km) and pd.isna(recurring_days):
                continue
            events = task_groups.get((motorcycle_id, policy["task_code"]))
            if events is not None and not events.empty:
                event_days = events["task_at"].values.astype("datetime64[D]")
                event_odo = events["task_odometer_km"].to_numpy(float)
                indices = np.searchsorted(event_days, lm_days, side="right") - 1
                has = indices >= 0
                last_days = np.full(len(positions), observation_start, dtype="datetime64[D]")
                last_odo = np.full(len(positions), initial_odo, dtype=float)
                last_days[has] = event_days[indices[has]]
                last_odo[has] = event_odo[indices[has]]
            else:
                last_days = np.full(len(positions), observation_start, dtype="datetime64[D]")
                last_odo = np.full(len(positions), initial_odo, dtype=float)
            elapsed_days = (lm_days - last_days).astype("timedelta64[D]").astype(float)
            elapsed_km = np.maximum(0.0, lm_odo - last_odo)
            day_ratio = elapsed_days / recurring_days if pd.notna(recurring_days) and recurring_days > 0 else np.zeros(len(positions))
            km_ratio = elapsed_km / recurring_km if pd.notna(recurring_km) and recurring_km > 0 else np.zeros(len(positions))
            trigger = str(policy["trigger_mode"])
            if trigger == "TIME_ONLY":
                due = day_ratio >= 1.0
            elif trigger == "KM_ONLY":
                due = km_ratio >= 1.0
            else:
                due = np.maximum(day_ratio, km_ratio) >= 1.0
            due_count[positions] += due.astype(np.int16)
            if pd.notna(recurring_days) and recurring_days > 0:
                remaining = np.maximum(0.0, recurring_days - elapsed_days)
                existing = min_days[positions]
                min_days[positions] = np.where(np.isnan(existing), remaining, np.minimum(existing, remaining))
            if pd.notna(recurring_km) and recurring_km > 0:
                remaining = np.maximum(0.0, recurring_km - elapsed_km)
                existing = min_km[positions]
                min_km[positions] = np.where(np.isnan(existing), remaining, np.minimum(existing, remaining))
    frame["due_task_count"] = due_count
    frame["days_until_next_scheduled_due"] = min_days
    frame["km_until_next_scheduled_due"] = min_km
    frame["maintenance_due_now"] = (due_count > 0).astype(np.int8)
    return frame


def _assign_splits(frame: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
    split_cfg = config["primary_split"]
    train_end = pd.Timestamp(split_cfg["train_end"])
    validation_end = pd.Timestamp(split_cfg["validation_end"])
    digest_value = frame["motorcycle_id"].map(
        lambda value: int(hashlib.sha256(f"{config['random_seed']}:{value}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    )
    unseen = digest_value < float(config["unseen_motorcycle_fraction"])
    primary = np.where(
        frame["landmark_at"] <= train_end, "TRAIN",
        np.where(frame["landmark_at"] <= validation_end, "VALIDATION", "TEST"),
    )
    manifest = frame[IDENTIFIER_COLUMNS].copy()
    manifest["primary_split"] = primary
    manifest["is_unseen_motorcycle_holdout"] = unseen.astype(np.int8)
    manifest["modeling_role"] = np.where(
        unseen,
        np.where(primary == "TEST", "UNSEEN_MOTORCYCLE_TEMPORAL_TEST", "UNSEEN_MOTORCYCLE_EXCLUDED"),
        primary,
    )
    return manifest


def _feature_dictionary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in frame.columns:
        if column in IDENTIFIER_COLUMNS or column in {"observation_start_date", "initial_mileage_km"}:
            role = "IDENTIFIER_OR_AUDIT"
        elif column in FEATURE_COLUMNS:
            role = "MODEL_FEATURE"
        else:
            role = "DERIVED_AUDIT"
        rows.append({
            "field": column,
            "role": role,
            "dtype": str(frame[column].dtype),
            "source_layer": "V2_1_DERIVED",
            "available_at_landmark": True,
            "model_input": column in FEATURE_COLUMNS,
        })
    for column in TARGET_COLUMNS:
        rows.append({
            "field": column,
            "role": "TARGET_OR_LABEL",
            "dtype": "derived",
            "source_layer": "V2_1_DERIVED_TARGET",
            "available_at_landmark": column == "landmark_id",
            "model_input": False,
        })
    return pd.DataFrame(rows)


def _quality_report(
    snapshots: pd.DataFrame, targets: pd.DataFrame, manifest: pd.DataFrame,
) -> Dict[str, Any]:
    forbidden = [
        column for column in FEATURE_COLUMNS
        if any(token in column.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    ]
    joined = snapshots[["landmark_id", "landmark_at"]].merge(
        targets[["landmark_id", "duration_days", "event_observed", "next_service_id"]],
        on="landmark_id", validate="one_to_one",
    )
    checks = {
        "unique_landmark_id": int(snapshots["landmark_id"].nunique()) == len(snapshots),
        "snapshot_target_key_match": set(snapshots["landmark_id"]) == set(targets["landmark_id"]),
        "positive_duration": bool((targets["duration_days"] >= 1).all()),
        "event_binary": set(targets["event_observed"].unique()).issubset({0, 1}),
        "observed_has_next_service": bool(targets.loc[targets["event_observed"] == 1, "next_service_id"].notna().all()),
        "censored_has_no_next_service": bool(targets.loc[targets["event_observed"] == 0, "next_service_id"].isna().all()),
        "forbidden_model_features_absent": not forbidden,
        "no_absolute_year_feature": "landmark_year" not in FEATURE_COLUMNS and "snapshot_year" not in FEATURE_COLUMNS,
        "manifest_key_match": set(snapshots["landmark_id"]) == set(manifest["landmark_id"]),
        "current_odometer_nonnegative": bool((snapshots["current_odometer_km_at_landmark"] >= 0).all()),
        "km_since_service_nonnegative": bool((snapshots["km_since_last_service"] >= 0).all()),
        "next_service_strictly_after_landmark": bool((targets.loc[targets["event_observed"] == 1, "duration_days"] > 0).all()),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "forbidden_features": forbidden,
        "rows": len(snapshots),
        "motorcycles": int(snapshots["motorcycle_id"].nunique()),
        "events": int(targets["event_observed"].sum()),
        "censored": int((targets["event_observed"] == 0).sum()),
        "event_rate": round(float(targets["event_observed"].mean()), 6),
        "landmarks_per_motorcycle": snapshots.groupby("motorcycle_id").size().describe().round(3).to_dict(),
        "split_counts": manifest["modeling_role"].value_counts().to_dict(),
    }


def build_landmark_dataset(paths: LandmarkPaths) -> Dict[str, Any]:
    config = _load_config(paths.config_path)
    schema_check = assert_source_schema_contract(paths.source_dir, paths.schema_contract_path)
    source = _read_sources(paths.source_dir)

    motorcycles = source["motorcycles"].copy()
    motorcycles["observation_start_date"] = pd.to_datetime(motorcycles["observation_start_date"])
    motorcycles["first_registration_date"] = pd.to_datetime(motorcycles["first_registration_date"])
    motorcycles["ownership_start_date"] = pd.to_datetime(motorcycles["ownership_start_date"])
    models = source["ridebase_motorcycle_models_v1"].copy()
    primary_policies = _primary_policy_table(models, source["maintenance_policies"])

    tasks = source["service_tasks"].copy()
    task_agg = tasks.groupby("service_id").agg(
        last_service_task_count=("service_task_id", "size"),
        last_service_policy_due_task_count=("is_policy_due", "sum"),
    ).reset_index()

    services = source["services"].loc[
        source["services"]["status"].isin(config["eligible_service_statuses"])
    ].copy()
    services["service_at"] = pd.to_datetime(services["received_at"]).dt.normalize()
    services = services.merge(task_agg, on="service_id", how="left")
    services["last_service_task_count"] = services["last_service_task_count"].fillna(0).astype(int)
    services["last_service_spend"] = services["grand_total"].fillna(0.0)
    services["last_service_was_breakdown"] = services["is_breakdown"].fillna(0).astype(int)
    services["last_service_was_warranty"] = services["is_warranty"].fillna(0).astype(int)
    service_keep = [
        "motorcycle_id", "service_at", "service_id", "odometer_km", "service_type_code",
        "arrival_mode", "service_delay_days", "grand_total", "last_service_task_count",
        "last_service_spend", "last_service_was_breakdown", "last_service_was_warranty",
    ]
    services = services[service_keep].sort_values(["motorcycle_id", "service_at", "service_id"])

    task_events = tasks.loc[tasks["completed"] == 1, ["motorcycle_id", "service_id", "task_code"]].merge(
        services[["service_id", "service_at", "odometer_km"]], on="service_id", how="inner"
    ).rename(columns={"service_at": "task_at", "odometer_km": "task_odometer_km"})

    timeline = source["mileage_timeline_monthly"].copy()
    timeline["landmark_at"] = pd.to_datetime(timeline["period_end_date"]).dt.normalize()
    timeline = timeline.sort_values(["motorcycle_id", "landmark_at"])
    timeline["recent_90d_km"] = (
        timeline.groupby("motorcycle_id", sort=False)["km_added"]
        .rolling(window=3, min_periods=1).sum().reset_index(level=0, drop=True)
    )
    cutoffs = timeline.groupby("motorcycle_id")["landmark_at"].max().rename("administrative_cutoff_at")
    timeline = timeline.merge(cutoffs, on="motorcycle_id", how="left")
    timeline = timeline.loc[timeline["landmark_at"] < timeline["administrative_cutoff_at"]].copy()

    static = (
        motorcycles.merge(models, on=["model_id", "brand", "category", "powertrain_type"], how="left", suffixes=("", "_model"))
        .merge(primary_policies, on="model_id", how="left")
        .merge(source["customers"][["customer_id", "customer_type", "is_fleet_customer"]], on="customer_id", how="left")
        .merge(source["usage_profiles"][[
            "motorcycle_id", "usage_type", "annual_km_baseline", "riding_intensity",
            "climate_zone", "storage_condition",
        ]], on="motorcycle_id", how="left")
        .merge(source["workshops"][[
            "workshop_id", "region", "price_level", "service_bay_count", "appointment_rate",
            "avg_parts_lead_days", "customer_volume_index",
        ]].rename(columns={
            "region": "workshop_region", "price_level": "workshop_price_level",
        }), on="workshop_id", how="left")
    )
    landmarks = timeline[[
        "motorcycle_id", "landmark_at", "administrative_cutoff_at", "closing_odometer_km",
        "recent_90d_km",
    ]].merge(static, on="motorcycle_id", how="left", validate="many_to_one")
    landmarks = landmarks.rename(columns={"closing_odometer_km": "current_odometer_km_at_landmark"})

    joined = _asof_join_landmarks(landmarks, services)
    joined = joined.loc[joined["service_id"].notna()].copy()
    joined = joined.rename(columns={
        "service_id": "source_last_service_id",
        "service_type_code": "last_service_type_code",
        "arrival_mode": "last_arrival_mode",
    }).reset_index(drop=True)

    # Next-service target is observed only when it occurs by the per-motorcycle cutoff.
    observed = joined["next_service_at"].notna() & (joined["next_service_at"] <= joined["administrative_cutoff_at"])
    duration = np.where(
        observed,
        (joined["next_service_at"] - joined["landmark_at"]).dt.days,
        (joined["administrative_cutoff_at"] - joined["landmark_at"]).dt.days,
    ).astype(int)
    joined = joined.loc[duration >= int(config["minimum_landmark_duration_days"])].copy().reset_index(drop=True)
    observed = observed.loc[joined.index] if len(observed) == len(joined) else (
        joined["next_service_at"].notna() & (joined["next_service_at"] <= joined["administrative_cutoff_at"])
    )
    duration = np.where(
        observed,
        (joined["next_service_at"] - joined["landmark_at"]).dt.days,
        (joined["administrative_cutoff_at"] - joined["landmark_at"]).dt.days,
    ).astype(int)

    joined["landmark_id"] = [f"LMK{i:09d}" for i in range(1, len(joined) + 1)]
    joined["production_age_days"] = (joined["landmark_at"] - joined["first_registration_date"]).dt.days.clip(lower=0)
    joined["ownership_age_days"] = (joined["landmark_at"] - joined["ownership_start_date"]).dt.days.clip(lower=0)
    joined["days_since_last_service"] = (joined["landmark_at"] - joined["service_at"]).dt.days
    joined["km_since_last_service"] = (
        joined["current_odometer_km_at_landmark"] - joined["odometer_km"]
    ).clip(lower=0)
    joined["avg_km_per_day_since_last_service"] = np.where(
        joined["days_since_last_service"] > 0,
        joined["km_since_last_service"] / joined["days_since_last_service"],
        0.0,
    )
    joined["recent_vs_baseline_usage_ratio"] = np.where(
        joined["annual_km_baseline"] > 0,
        (joined["recent_90d_km"] * (365.25 / 90.0)) / joined["annual_km_baseline"],
        np.nan,
    )
    joined["days_due_ratio"] = np.where(
        joined["oem_interval_days"] > 0,
        joined["days_since_last_service"] / joined["oem_interval_days"], np.nan,
    )
    joined["km_due_ratio"] = np.where(
        joined["oem_interval_km"] > 0,
        joined["km_since_last_service"] / joined["oem_interval_km"], np.nan,
    )
    joined["max_due_ratio"] = joined[["days_due_ratio", "km_due_ratio"]].max(axis=1, skipna=True)
    joined["days_overdue"] = np.maximum(0.0, joined["days_since_last_service"] - joined["oem_interval_days"])
    joined["km_overdue"] = np.maximum(0.0, joined["km_since_last_service"] - joined["oem_interval_km"])
    month = joined["landmark_at"].dt.month.astype(float)
    joined["landmark_month_sin"] = np.sin(2.0 * math.pi * month / 12.0)
    joined["landmark_month_cos"] = np.cos(2.0 * math.pi * month / 12.0)

    joined = _history_features(joined, services)
    joined = _due_task_features(joined, services, task_events, source["maintenance_policies"])

    targets = pd.DataFrame({
        "landmark_id": joined["landmark_id"],
        "duration_days": duration,
        "event_observed": observed.astype(np.int8).to_numpy(),
        "next_service_id": joined["next_service_id"].where(observed, None),
        "administrative_cutoff_at": joined["administrative_cutoff_at"],
    })
    for horizon in config["horizons_days"]:
        targets[f"event_within_{horizon}d"] = np.where(
            (targets["event_observed"] == 1) & (targets["duration_days"] <= horizon), 1,
            np.where(targets["duration_days"] >= horizon, 0, np.nan),
        )

    snapshots = joined[IDENTIFIER_COLUMNS + ["observation_start_date", "initial_mileage_km"] + FEATURE_COLUMNS].copy()
    manifest = _assign_splits(snapshots, config)
    modeling = snapshots.merge(targets, on="landmark_id", validate="one_to_one").merge(
        manifest[["landmark_id", "primary_split", "is_unseen_motorcycle_holdout", "modeling_role"]],
        on="landmark_id", validate="one_to_one",
    )
    dictionary = _feature_dictionary(snapshots)
    quality = _quality_report(snapshots, targets, manifest)
    if quality["status"] != "PASS":
        raise RuntimeError(f"V2.1 landmark quality gate failed: {quality['checks']}")

    paths.output_dir.mkdir(parents=True, exist_ok=True)
    output_files = {
        "snapshots": paths.output_dir / "v2_1_landmark_snapshots.parquet",
        "targets": paths.output_dir / "v2_1_survival_targets.parquet",
        "modeling": paths.output_dir / "v2_1_modeling_table.parquet",
        "manifest": paths.output_dir / "v2_1_landmark_manifest.csv",
        "dictionary": paths.output_dir / "v2_1_feature_dictionary.csv",
        "quality": paths.output_dir / "v2_1_data_quality_report.json",
        "metadata": paths.output_dir / "v2_1_generation_metadata.json",
    }
    snapshots.to_parquet(output_files["snapshots"], index=False)
    targets.to_parquet(output_files["targets"], index=False)
    modeling.to_parquet(output_files["modeling"], index=False)
    manifest.to_csv(output_files["manifest"], index=False)
    dictionary.to_csv(output_files["dictionary"], index=False)
    output_files["quality"].write_text(json.dumps(quality, indent=2, ensure_ascii=False) + "\n")
    metadata = {
        "dataset_version": config["dataset_version"],
        "experiment": config["experiment"],
        "parent_dataset": config["parent_dataset"],
        "source_schema_version": config["source_schema_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": config["random_seed"],
        "landmark_strategy": config["landmark_strategy"],
        "target_contract": "time from landmark_at to the next delivered service; otherwise right-censored at the motorcycle administrative cutoff",
        "time_origin": "landmark_at",
        "left_truncation_required": False,
        "feature_count": len(FEATURE_COLUMNS),
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "source_schema_check": schema_check,
        "source_hashes": {
            path.name: _sha256(path) for path in sorted(paths.source_dir.glob("*.csv"))
        },
    }
    output_files["metadata"].write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    # A file cannot contain a stable checksum of itself.  Hash every other
    # generated artifact and keep the metadata file outside that checksum map.
    metadata["output_hashes"] = {
        name: _sha256(path)
        for name, path in output_files.items()
        if name != "metadata" and path.exists()
    }
    output_files["metadata"].write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    return {"quality": quality, "metadata": metadata, "files": {k: str(v) for k, v in output_files.items()}}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    result = build_landmark_dataset(LandmarkPaths.from_repo(root))
    print(json.dumps({"quality": result["quality"], "files": result["files"]}, indent=2, ensure_ascii=False))
