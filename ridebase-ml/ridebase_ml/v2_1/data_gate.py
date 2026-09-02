"""V1.4-linked V2.1 dynamic-landmark dataset sanity and leakage gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .landmarks import FEATURE_COLUMNS, FORBIDDEN_FEATURE_TOKENS
from .schema_contract import assert_source_schema_compatible, assert_source_schema_contract


DUE_BINS = [-np.inf, .8, 1.2, 2.0, np.inf]
DUE_LABELS = ["NOT_DUE", "NEAR_DUE", "OVERDUE", "SEVERELY_OVERDUE"]
RATIO_BINS = [-np.inf, .25, .5, .8, 1.0, 1.5, 2.0, 3.0, np.inf]
RATIO_LABELS = ["<=0.25", ".25-.50", ".50-.80", ".80-1.0", "1.0-1.5", "1.5-2.0", "2.0-3.0", ">3.0"]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.replace({np.nan: None}).to_json(orient="records"))


def _group_rates(frame: pd.DataFrame, group: str) -> pd.DataFrame:
    return frame.groupby(group, observed=True, dropna=False).agg(
        landmarks=("landmark_id", "size"), motorcycles=("motorcycle_id", "nunique"),
        event_30d_rate=("event_within_30d", "mean"), event_90d_rate=("event_within_90d", "mean"),
        eventual_event_rate=("event_observed", "mean"), due_ratio_mean=("max_due_ratio", "mean"),
    ).reset_index()


def run_data_gate(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    derived = root / "ridebase-ml/derived_outputs/v2_1_v1_4"
    reports = root / "ridebase-ml/reports"
    source = root / "ridebase_v1_4/source_tables"
    contract = root / "ridebase-ml/config/source_schema_contract_v1_3.json"
    frozen = assert_source_schema_contract(root / "ridebase_v1_3/source_tables", contract)
    compatible = assert_source_schema_compatible(source, contract)
    frame = pd.read_parquet(derived / "v2_1_modeling_table.parquet")
    manifest = pd.read_csv(derived / "v2_1_landmark_manifest.csv")
    dictionary = pd.read_csv(derived / "v2_1_feature_dictionary.csv")
    services = pd.read_csv(source / "services.csv", low_memory=False)

    frame["due_state"] = pd.cut(frame.max_due_ratio, DUE_BINS, labels=DUE_LABELS)
    due = _group_rates(frame, "due_state")
    due_lookup = due.set_index("due_state").event_90d_rate.to_dict()
    ratio_tables = {}
    for column in ["km_due_ratio", "days_due_ratio"]:
        binned = frame.assign(ratio_bin=pd.cut(frame[column], RATIO_BINS, labels=RATIO_LABELS))
        ratio_tables[column] = _group_rates(binned, "ratio_bin")

    delay_group = pd.cut(
        frame.historical_service_delay_mean_days,
        [-np.inf, 0, 7, 30, np.inf], labels=["ON_TIME", "SLIGHT_DELAY", "LATE", "VERY_LATE"],
    )
    customer = _group_rates(frame.assign(customer_behavior=delay_group), "customer_behavior")
    usage = _group_rates(frame, "usage_type")
    policy = _group_rates(frame, "policy_group")
    category = _group_rates(frame, "category")
    age = _group_rates(frame.assign(age_band=pd.cut(frame.production_age_days / 365.25, [-np.inf, 2, 5, 10, np.inf])), "age_band")
    season = _group_rates(frame.assign(season=((pd.to_datetime(frame.landmark_at).dt.month % 12) // 3 + 1)), "season")

    next_types = frame[["next_service_id", "event_observed"]].merge(
        services[["service_id", "service_type_code"]], left_on="next_service_id", right_on="service_id", how="left"
    )
    breakdown = {
        "observed_next_event_type_share": next_types.loc[next_types.event_observed.eq(1), "service_type_code"].value_counts(normalize=True).round(6).to_dict(),
        "breakdown_or_repair_share": float(next_types.loc[next_types.event_observed.eq(1), "service_type_code"].isin(["BREAKDOWN", "REPAIR"]).mean()),
    }
    split = manifest.groupby("modeling_role").agg(
        landmarks=("landmark_id", "size"), motorcycles=("motorcycle_id", "nunique")
    ).reset_index()
    censor = frame.groupby("modeling_role").agg(
        landmarks=("landmark_id", "size"), censor_rate=("event_observed", lambda x: 1 - x.mean())
    ).reset_index()
    density = frame.groupby("motorcycle_id").size().describe(percentiles=[.1, .25, .5, .75, .9, .99]).round(5).to_dict()

    forbidden = [column for column in FEATURE_COLUMNS if any(token in column.lower() for token in FORBIDDEN_FEATURE_TOKENS)]
    explicit_leakage = [
        column for column in FEATURE_COLUMNS
        if column.startswith(("next_", "target_", "future_"))
        or any(token in column.lower() for token in ["censor", "event_observed", "duration", "split"])
    ]
    train_motorcycles = set(manifest.loc[manifest.modeling_role.eq("TRAIN"), "motorcycle_id"])
    unseen_motorcycles = set(manifest.loc[manifest.is_unseen_motorcycle_holdout.eq(1), "motorcycle_id"])
    horizon_monotonic = bool(
        frame[["event_within_30d", "event_within_60d", "event_within_90d", "event_within_120d"]]
        .fillna(0).diff(axis=1).iloc[:, 1:].ge(0).all().all()
    )
    event_overlap = bool(
        frame.groupby("due_state", observed=True).event_observed.agg(["min", "max"]).eq({"min": 0, "max": 1}).all().all()
    )
    customer_overlap = bool(customer.event_90d_rate.between(.05, .95).all())
    usage_overlap = bool(usage.event_90d_rate.between(.05, .95).all())
    km_table = ratio_tables["km_due_ratio"].set_index("ratio_bin").event_90d_rate
    day_table = ratio_tables["days_due_ratio"].set_index("ratio_bin").event_90d_rate
    gate = {
        "frozen_v1_3_source_unchanged": frozen["status"] == "PASS",
        "v1_4_source_schema_compatible": compatible["status"] == "PASS",
        "landmark_target_quality_pass": json.loads((derived / "v2_1_data_quality_report.json").read_text())["status"] == "PASS",
        "severe_overdue_not_near_zero": due_lookup.get("SEVERELY_OVERDUE", 0) >= .15,
        "overdue_direction_coherent": due_lookup.get("OVERDUE", 0) >= due_lookup.get("NOT_DUE", 0) * 1.25,
        "km_due_relevant": float(km_table.iloc[-1]) >= float(km_table.iloc[0]) * 1.5,
        "days_due_not_structurally_reversed": float(day_table.iloc[-1]) >= float(day_table.iloc[0]) * .9,
        "no_absolute_calendar_year_feature": not any("year" in column.lower() for column in FEATURE_COLUMNS),
        "event_no_event_overlap": event_overlap,
        "customer_behavior_overlap": customer_overlap,
        "usage_behavior_overlap": usage_overlap,
        "feature_lineage_no_leakage": not forbidden and not explicit_leakage,
        "split_not_model_feature": "primary_split" not in FEATURE_COLUMNS and "modeling_role" not in FEATURE_COLUMNS,
        "unseen_motorcycle_isolation": train_motorcycles.isdisjoint(unseen_motorcycles),
        "target_horizon_monotonicity": horizon_monotonic,
        "critical_due_feature_present": "critical_due_task_count" in FEATURE_COLUMNS,
    }
    failed = [name for name, passed in gate.items() if not passed]
    report = {
        "report": "RideBase V2.1 Dataset Rebuild", "status": "PASS" if not failed else "FAIL",
        "model_training_allowed": not failed, "failed_checks": failed, "gate_checks": gate,
        "input_version": "1.4.0", "source_schema_version": "1.3.0",
        "headline": {
            "landmarks": len(frame), "motorcycles": int(frame.motorcycle_id.nunique()),
            "events": int(frame.event_observed.sum()), "censored": int(frame.event_observed.eq(0).sum()),
            "features": len(FEATURE_COLUMNS),
        },
        "removed_artifacts": ["split", "absolute_year", "days_observed", "target/censor/future", "current_service_*"],
        "leakage_scan": {"forbidden": forbidden, "explicit": explicit_leakage},
        "due_state_behavior": _records(due),
        "km_due_behavior": _records(ratio_tables["km_due_ratio"]),
        "days_due_behavior": _records(ratio_tables["days_due_ratio"]),
        "customer_behavior": _records(customer), "usage_behavior": _records(usage),
        "policy_behavior": _records(policy), "category_behavior": _records(category),
        "age_behavior": _records(age), "season_behavior": _records(season),
        "breakdown_contribution": breakdown, "censoring": _records(censor),
        "landmark_density": density, "split_counts": _records(split),
        "temporal_cutoffs": {"train_end": "2025-06-30", "validation_end": "2025-12-31", "test_start": "2026-01-01"},
        "motorcycle_overlap": {
            "train_vs_temporal_test": len(train_motorcycles & set(manifest.loc[manifest.primary_split.eq("TEST"), "motorcycle_id"])),
            "train_vs_unseen": len(train_motorcycles & unseen_motorcycles),
        },
        "feature_dictionary_model_inputs": int(dictionary.model_input.sum()),
    }
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "v2_1_v1_4_data_gate.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    due.to_csv(reports / "v2_1_v1_4_due_state.csv", index=False)
    markdown = [
        "# RideBase V2.1 Dataset Rebuild", "", f"**Gate: {report['status']}**", "",
        f"Input v1.4.0; {len(frame):,} landmarks; {frame.motorcycle_id.nunique():,} motorcycles; "
        f"{int(frame.event_observed.sum()):,} events; {int(frame.event_observed.eq(0).sum()):,} censored; {len(FEATURE_COLUMNS)} features.",
        "", "## Due-state behavior", "", due.to_markdown(index=False, floatfmt=".4f"), "",
        "## Split", "", split.to_markdown(index=False), "", "## Gate checks", "",
    ]
    markdown.extend(f"- {'PASS' if passed else 'FAIL'} — `{name}`" for name, passed in gate.items())
    markdown.extend(["", "## Final verdict", "", "V2.1 DATA GATE PASS — MODEL TRAINING ALLOWED" if not failed else "V2.1 DATA GATE FAIL — MODEL TRAINING BLOCKED", ""])
    (reports / "v2_1_v1_4_data_gate.md").write_text("\n".join(markdown))
    return report


if __name__ == "__main__":
    result = run_data_gate(Path(__file__).resolve().parents[3])
    print(json.dumps({"status": result["status"], "failed_checks": result["failed_checks"], "headline": result["headline"]}, indent=2))
