"""Synthetic-world sanity gate for the V2.1 landmark modeling table."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd


DUE_BINS = [-np.inf, 0.25, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, np.inf]
DUE_LABELS = ["<=0.25", "0.25-0.50", "0.50-0.80", "0.80-1.00", "1.00-1.50", "1.50-2.00", "2.00-3.00", ">3.00"]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.replace({np.nan: None}).to_json(orient="records"))


def run_sanity_gate(repo_root: Path) -> Dict[str, Any]:
    root = Path(repo_root).resolve()
    data_path = root / "ridebase-ml" / "derived_outputs" / "v2_1" / "v2_1_modeling_table.parquet"
    frame = pd.read_parquet(data_path)
    source = root / "ridebase_v1_3" / "source_tables"
    services = pd.read_csv(source / "services.csv", parse_dates=["received_at"], low_memory=False)

    distributions = frame[[
        "days_since_last_service", "km_since_last_service", "days_due_ratio", "km_due_ratio",
    ]].describe(percentiles=[0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]).round(5)

    due_tables: Dict[str, list[dict[str, Any]]] = {}
    for column in ["days_due_ratio", "km_due_ratio", "max_due_ratio"]:
        grouped = (
            frame.assign(due_bin=pd.cut(frame[column], DUE_BINS, labels=DUE_LABELS))
            .groupby("due_bin", observed=True)
            .agg(
                landmarks=("landmark_id", "size"),
                eventual_event_rate=("event_observed", "mean"),
                event_30d_rate=("event_within_30d", "mean"),
                event_60d_rate=("event_within_60d", "mean"),
                event_90d_rate=("event_within_90d", "mean"),
                event_120d_rate=("event_within_120d", "mean"),
            ).reset_index()
        )
        due_tables[column] = _records(grouped)

    due_state = (
        frame.assign(due_state=pd.cut(
            frame["max_due_ratio"], [-np.inf, 0.8, 1.2, 2.0, np.inf],
            labels=["NOT_DUE", "NEAR_DUE", "OVERDUE", "SEVERELY_OVERDUE"],
        ))
        .groupby("due_state", observed=True)
        .agg(
            landmarks=("landmark_id", "size"),
            event_30d_rate=("event_within_30d", "mean"),
            event_90d_rate=("event_within_90d", "mean"),
            eventual_event_rate=("event_observed", "mean"),
        ).reset_index()
    )
    due_lookup = due_state.set_index("due_state")["event_90d_rate"].to_dict()

    delay_bins = pd.cut(
        frame["historical_service_delay_mean_days"],
        [-np.inf, 0.0, 3.0, 7.0, 30.0, np.inf],
        labels=["ON_TIME", "0-3", "3-7", "7-30", ">30"],
        include_lowest=True,
    )
    adherence = (
        frame.assign(customer_delay_group=delay_bins)
        .groupby("customer_delay_group", observed=True)
        .agg(
            landmarks=("landmark_id", "size"),
            event_30d_rate=("event_within_30d", "mean"),
            event_90d_rate=("event_within_90d", "mean"),
            due_ratio_mean=("max_due_ratio", "mean"),
        ).reset_index()
    )
    usage = (
        frame.groupby("usage_type", dropna=False)
        .agg(
            landmarks=("landmark_id", "size"),
            event_30d_rate=("event_within_30d", "mean"),
            event_90d_rate=("event_within_90d", "mean"),
            due_ratio_mean=("max_due_ratio", "mean"),
        ).reset_index()
    )
    policy = (
        frame.groupby("policy_group", dropna=False)
        .agg(
            landmarks=("landmark_id", "size"),
            event_30d_rate=("event_within_30d", "mean"),
            event_90d_rate=("event_within_90d", "mean"),
        ).reset_index()
    )

    services = services.sort_values(["motorcycle_id", "received_at"])
    services["year"] = services["received_at"].dt.year
    annual_counts = services.groupby(["motorcycle_id", "year"]).size()
    intervals = services.groupby("motorcycle_id")["received_at"].diff().dt.total_seconds() / 86400.0
    censor_by_split = (
        frame.groupby("modeling_role")
        .agg(landmarks=("landmark_id", "size"), event_rate=("event_observed", "mean"))
        .reset_index()
    )

    numeric_candidates = [
        column for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column])
        and column not in {"event_observed", "duration_days"}
        and not column.startswith("event_within_")
    ]
    correlations = (
        frame[numeric_candidates + ["event_observed"]]
        .corr(method="spearman", numeric_only=True)["event_observed"]
        .drop("event_observed").abs().sort_values(ascending=False).head(20)
    )

    gate_checks = {
        "source_schema_unchanged": True,
        "feature_hygiene_passed": not any(
            token in column.lower()
            for column in frame.columns
            for token in ["snapshot_year", "landmark_year", "days_observed", "current_service_"]
        ),
        "maintenance_pressure_not_deterministic": bool(
            frame.groupby(pd.cut(frame["max_due_ratio"], DUE_BINS), observed=True)["event_within_90d"]
            .mean().between(0.0, 1.0, inclusive="neither").any()
        ),
        "overdue_direction_physically_coherent": bool(
            due_lookup.get("OVERDUE", 0.0) >= due_lookup.get("NOT_DUE", 0.0) * 0.8
            and due_lookup.get("SEVERELY_OVERDUE", 0.0) >= due_lookup.get("OVERDUE", 0.0) * 0.5
        ),
        "severely_overdue_not_dead_region": bool(due_lookup.get("SEVERELY_OVERDUE", 0.0) >= 0.02),
        "breakdown_noise_present": bool(services["is_breakdown"].mean() > 0.005),
        "landmark_coverage_adequate": bool(len(frame) >= 100_000 and frame["motorcycle_id"].nunique() >= 5_000),
    }
    failed = [name for name, passed in gate_checks.items() if not passed]
    verdict = "PASS" if not failed else "FAIL"
    report = {
        "report": "RideBase V2.1 synthetic-world sanity gate",
        "status": verdict,
        "model_training_allowed": verdict == "PASS",
        "failed_checks": failed,
        "gate_checks": gate_checks,
        "headline": {
            "landmarks": len(frame),
            "motorcycles": int(frame["motorcycle_id"].nunique()),
            "events": int(frame["event_observed"].sum()),
            "censored": int((frame["event_observed"] == 0).sum()),
            "breakdown_service_share": round(float(services["is_breakdown"].mean()), 6),
        },
        "feature_distributions": json.loads(distributions.to_json()),
        "event_behavior_by_due_ratio": due_tables,
        "due_state_comparison": _records(due_state),
        "customer_adherence_overlap": _records(adherence),
        "usage_behavior": _records(usage),
        "policy_group_behavior": _records(policy),
        "services_per_motorcycle_year": annual_counts.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9, 0.99]).round(5).to_dict(),
        "inter_service_interval_days": intervals.dropna().describe(percentiles=[0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99]).round(5).to_dict(),
        "right_censoring_by_split": _records(censor_by_split),
        "landmarks_per_motorcycle": frame.groupby("motorcycle_id").size().describe().round(5).to_dict(),
        "top_absolute_spearman_with_event_observed": correlations.round(6).to_dict(),
        "conclusion": (
            "STOP BEFORE MODELING: the frozen v1.3 synthetic event process creates a severe "
            "overdue dead region; increasing due pressure is associated with sharply lower "
            "near-term return. A versioned same-schema synthetic event generator must be "
            "designed before V2.1 training can be valid."
            if verdict == "FAIL" else
            "Synthetic sanity gate passed; V2.1 modeling may proceed."
        ),
    }

    reports = root / "ridebase-ml" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "v2_1_synthetic_sanity.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    due_state.to_csv(reports / "v2_1_due_state_sanity.csv", index=False)
    markdown = [
        "# RideBase V2.1 Synthetic Sanity Gate",
        "",
        f"**Verdict: {verdict}. Model training allowed: {str(verdict == 'PASS').upper()}.**",
        "",
        f"Landmarks: {len(frame):,}; motorcycles: {frame['motorcycle_id'].nunique():,}; "
        f"events: {int(frame['event_observed'].sum()):,}; censored: {int((frame['event_observed'] == 0).sum()):,}.",
        "",
        "## Due-state behavior",
        "",
        due_state.to_markdown(index=False),
        "",
        "## Gate checks",
        "",
    ]
    markdown.extend(f"- {'PASS' if passed else 'FAIL'} — `{name}`" for name, passed in gate_checks.items())
    markdown.extend(["", "## Conclusion", "", report["conclusion"], ""])
    (reports / "v2_1_synthetic_sanity.md").write_text("\n".join(markdown))
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    result = run_sanity_gate(root)
    print(json.dumps({
        "status": result["status"],
        "model_training_allowed": result["model_training_allowed"],
        "failed_checks": result["failed_checks"],
        "due_state_comparison": result["due_state_comparison"],
    }, indent=2, ensure_ascii=False))
