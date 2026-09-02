#!/usr/bin/env python3
"""Behavioral and source-contract gate for RideBase synthetic release v1.4."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from build_ridebase_v1_4 import CONTRACT, PARENT, ROOT, VERSION, sha256_file, source_qa, weekly_hazards

sys.path.insert(0, str(ROOT / "ridebase-ml"))
from ridebase_ml.v2_1.landmarks import _asof_join_landmarks, _primary_policy_table  # noqa: E402


OUTPUT = ROOT / "ridebase_v1_4"


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.replace({np.nan: None}).to_json(orient="records"))


def build_landmark_audit(source: Path) -> pd.DataFrame:
    mileage = pd.read_csv(source / "mileage_timeline_monthly.csv", low_memory=False)
    services = pd.read_csv(source / "services.csv", low_memory=False)
    motorcycles = pd.read_csv(source / "motorcycles.csv", low_memory=False)
    models = pd.read_csv(source / "ridebase_motorcycle_models_v1.csv", low_memory=False)
    policies = pd.read_csv(source / "maintenance_policies.csv", low_memory=False)
    usage = pd.read_csv(source / "usage_profiles.csv", low_memory=False)
    mileage["landmark_at"] = pd.to_datetime(mileage.period_end_date, format="mixed") + pd.Timedelta(hours=23, minutes=59)
    mileage = mileage.rename(columns={"closing_odometer_km": "current_odometer"})
    services["service_at"] = pd.to_datetime(services.received_at, format="mixed")
    services = services.rename(columns={"odometer_km": "last_service_odometer"})
    joined = _asof_join_landmarks(
        mileage[["motorcycle_id", "landmark_at", "current_odometer"]],
        services[["motorcycle_id", "service_at", "service_id", "last_service_odometer"]],
    )
    joined = joined.loc[joined.service_at.notna()].copy()
    policy = _primary_policy_table(models, policies)[["model_id", "oem_interval_days", "oem_interval_km"]]
    joined = joined.merge(motorcycles[["motorcycle_id", "model_id"]], on="motorcycle_id")
    joined = joined.merge(policy, on="model_id").merge(usage[["motorcycle_id", "usage_type", "annual_km_baseline"]], on="motorcycle_id")
    joined["days_due_ratio"] = (joined.landmark_at - joined.service_at).dt.total_seconds() / 86400.0 / joined.oem_interval_days
    joined["km_due_ratio"] = (joined.current_odometer - joined.last_service_odometer).clip(lower=0) / joined.oem_interval_km
    joined["max_due_ratio"] = joined[["days_due_ratio", "km_due_ratio"]].max(axis=1)
    duration = (joined.next_service_at - joined.landmark_at).dt.total_seconds() / 86400.0
    joined["event_observed"] = joined.next_service_at.notna().astype(int)
    for horizon in [30, 60, 90, 120]:
        joined[f"event_{horizon}d"] = (joined.next_service_at.notna() & duration.le(horizon)).astype(int)
    joined["due_state"] = pd.cut(
        joined.max_due_ratio, [-np.inf, 0.8, 1.2, 2.0, np.inf],
        labels=["NOT_DUE", "NEAR_DUE", "OVERDUE", "SEVERELY_OVERDUE"],
    )
    return joined


def controlled_sensitivity(source: Path) -> dict:
    usage = pd.read_csv(source / "usage_profiles.csv", low_memory=False).iloc[0]
    motorcycle = pd.read_csv(source / "motorcycles.csv", low_memory=False).iloc[0]
    workshop = pd.read_csv(source / "workshops.csv", low_memory=False).iloc[0]
    behavior = {"adherence": 0.55, "frailty": 1.0}
    when = pd.Timestamp("2025-06-15")
    def risk(days: float, km: float) -> float:
        return weekly_hazards(when, days, km, behavior, usage, motorcycle, workshop)["PERIODIC"]
    return {
        "km_control": {"500_like": risk(0.45, 0.10), "20000_like": risk(0.45, 3.30)},
        "time_control": {"30d_like": risk(0.10, 0.10), "730d_like": risk(2.00, 0.10)},
    }


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    source_dir = OUTPUT / "source_tables"
    source = {filename: pd.read_csv(source_dir / filename, low_memory=False) for filename in contract["tables"]}
    qa = source_qa(source, contract)
    metadata = json.loads((OUTPUT / "dataset_metadata.json").read_text())
    parent_hashes_now = {path.name: sha256_file(path) for path in sorted((PARENT / "source_tables").glob("*.csv"))}
    landmarks = build_landmark_audit(source_dir)
    audit = pd.read_csv(OUTPUT / "reports" / "v1_4_generator_event_audit.csv", parse_dates=["event_at"])
    services = source["services.csv"].copy()
    services["received_at"] = pd.to_datetime(services.received_at, format="mixed")
    services = services.sort_values(["motorcycle_id", "received_at"])
    services["interval_days"] = services.groupby("motorcycle_id").received_at.diff().dt.total_seconds() / 86400.0
    services["interval_km"] = services.groupby("motorcycle_id").odometer_km.diff()

    due = landmarks.groupby("due_state", observed=True).agg(
        landmarks=("motorcycle_id", "size"), motorcycles=("motorcycle_id", "nunique"),
        event_30d_rate=("event_30d", "mean"), event_60d_rate=("event_60d", "mean"),
        event_90d_rate=("event_90d", "mean"), event_120d_rate=("event_120d", "mean"),
        eventual_event_rate=("event_observed", "mean"), median_due_ratio=("max_due_ratio", "median"),
    ).reset_index()
    due_lookup = due.set_index("due_state").event_90d_rate.to_dict()
    behavior = audit.groupby("behavior_group").agg(
        attempts=("outcome", "size"), service_rate=("outcome", lambda values: values.eq("SERVICE").mean()),
        p10_due=("max_due_ratio", lambda values: values.quantile(.1)),
        median_due=("max_due_ratio", "median"), p90_due=("max_due_ratio", lambda values: values.quantile(.9)),
    ).reset_index()
    usage = landmarks.groupby("usage_type").agg(
        landmarks=("motorcycle_id", "size"), p30=("event_30d", "mean"), p90=("event_90d", "mean"),
        median_due=("max_due_ratio", "median"), annual_km=("annual_km_baseline", "median"),
    ).reset_index()
    annual = services.assign(year=services.received_at.dt.year).groupby(["motorcycle_id", "year"]).size()
    appointments = source["appointments.csv"].status.value_counts(dropna=False)
    sensitivity = controlled_sensitivity(source_dir)
    old = pd.read_parquet(ROOT / "ridebase-ml" / "derived_outputs" / "v2_1" / "v2_1_modeling_table.parquet")
    old_state = pd.cut(old.max_due_ratio, [-np.inf, .8, 1.2, 2, np.inf], labels=["NOT_DUE", "NEAR_DUE", "OVERDUE", "SEVERELY_OVERDUE"])
    old_due = old.assign(due_state=old_state).groupby("due_state", observed=True).event_within_90d.mean().to_dict()

    schema_unchanged = all(list(source[name].columns) == spec["ordered_columns"] for name, spec in contract["tables"].items())
    parent_unchanged = parent_hashes_now == metadata["parent_hashes"]
    overlap = bool(behavior.service_rate.between(0.55, 0.99).all() and behavior.p10_due.max() < behavior.p90_due.min() * 1.5)
    nondeterministic = bool(audit.groupby(pd.cut(audit.max_due_ratio, [-np.inf, .8, 1.2, 2, np.inf]), observed=True).outcome.nunique().ge(2).all())
    gate = {
        "source_schema_unchanged": schema_unchanged,
        "v1_3_hashes_unchanged": parent_unchanged,
        "source_qa_pass": qa["status"] == "PASS",
        "severely_overdue_dead_region_resolved": due_lookup.get("SEVERELY_OVERDUE", 0) >= 0.15,
        "overdue_return_behavior_meaningful": due_lookup.get("OVERDUE", 0) >= due_lookup.get("NOT_DUE", 0) * 1.25,
        "due_pressure_direction": due_lookup.get("NEAR_DUE", 0) >= due_lookup.get("NOT_DUE", 0) and due_lookup.get("SEVERELY_OVERDUE", 0) >= due_lookup.get("OVERDUE", 0) * .75,
        "km_usage_sensitivity": sensitivity["km_control"]["20000_like"] >= sensitivity["km_control"]["500_like"] * 1.5,
        "time_usage_sensitivity": sensitivity["time_control"]["730d_like"] >= sensitivity["time_control"]["30d_like"] * 1.5,
        "behavior_group_overlap": overlap,
        "service_outcome_not_deterministic": nondeterministic,
        "reproducible_source_hashes": bool(metadata.get("reproducibility_verified")),
    }
    failed = [name for name, passed in gate.items() if not passed]
    report = {
        "report": "RideBase v1.4 Synthetic Generator Update", "version": VERSION,
        "status": "PASS" if not failed else "FAIL", "failed_checks": failed, "gate_checks": gate,
        "root_cause": {
            "code": "v1.3 regenerate_services preserved each motorcycle's fixed source row count and only rescaled timestamps; no stochastic event could occur after the final retained row",
            "evidence": "99.0016% of v1.3 severely-overdue landmarks were after the final generated service; their P90 was 0%, versus 93.6306% when a future retained service existed",
            "v1_3_p90_by_due_state": old_due,
        },
        "counts": {
            "services": len(services), "motorcycles_with_service": int(services.motorcycle_id.nunique()),
            "new_services": metadata["new_event_rows"], "new_no_show": metadata["new_no_show_rows"],
            "new_cancel": metadata["new_cancel_rows"],
            "services_per_motorcycle": services.groupby("motorcycle_id").size().describe().round(5).to_dict(),
        },
        "service_type_shares": services.service_type_code.value_counts(normalize=True).round(6).to_dict(),
        "inter_service_days": services.interval_days.dropna().describe(percentiles=[.01, .1, .25, .5, .75, .9, .99]).round(5).to_dict(),
        "inter_service_km": services.interval_km.dropna().describe(percentiles=[.01, .1, .25, .5, .75, .9, .99]).round(5).to_dict(),
        "behavior_group_overlap": records(behavior), "usage_group_behavior": records(usage),
        "policy_group_behavior": records(audit.groupby("policy_group", dropna=False).agg(attempts=("outcome", "size"), service_rate=("outcome", lambda x: x.eq("SERVICE").mean())).reset_index()),
        "annual_services_per_motorcycle": annual.describe(percentiles=[.1, .25, .5, .75, .9, .99]).round(5).to_dict(),
        "due_pressure_vs_return": records(due),
        "breakdown_repair_contribution": services.service_type_code.isin(["BREAKDOWN", "REPAIR"]).mean(),
        "appointments": appointments.to_dict(), "controlled_km_time_sensitivity": sensitivity,
        "heterogeneity": {"behavior_groups": int(behavior.behavior_group.nunique()), "within_bin_mixed_outcomes": nondeterministic},
        "source_qa": qa,
    }
    report_dir = OUTPUT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "v1_4_generator_sanity.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    due.to_csv(report_dir / "v1_4_due_state_behavior.csv", index=False)
    markdown = [
        "# RideBase v1.4 Synthetic Generator Update", "",
        f"**Gate: {report['status']}**", "", "## Root cause", "", report["root_cause"]["code"], "",
        report["root_cause"]["evidence"], "", "## Due pressure vs actual return", "", due.to_markdown(index=False, floatfmt=".4f"), "",
        "## Behavior overlap", "", behavior.to_markdown(index=False, floatfmt=".4f"), "",
        "## Hard gate", "",
    ]
    markdown.extend(f"- {'PASS' if passed else 'FAIL'} — `{name}`" for name, passed in gate.items())
    markdown.extend(["", "## Final verdict", "", "V1.4 GENERATOR READY FOR V2.1 REBUILD" if not failed else "BLOCKED", ""])
    (report_dir / "v1_4_generator_sanity.md").write_text("\n".join(markdown))
    print(json.dumps({"status": report["status"], "failed_checks": failed, "due": records(due)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
