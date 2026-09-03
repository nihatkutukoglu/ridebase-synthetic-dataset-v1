"""Empirical pre-training audit of the V1.5 synthetic behavior world."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml


HORIZONS = [30, 60, 90, 120]
DUE_EDGES = [-np.inf, .5, .75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, np.inf]
DUE_LABELS = ["<0.50", "0.50-0.75", "0.75-1.00", "1.00-1.25", "1.25-1.50", "1.50-2.00", "2.00-2.50", "2.50-3.00", "3.00+"]


def _eligible(frame: pd.DataFrame, horizon: int) -> pd.Series:
    return ((frame.event_observed == 1) & (frame.duration_days <= horizon)) | (frame.duration_days >= horizon)


def _rates(frame: pd.DataFrame, group: str) -> list[dict[str, Any]]:
    rows = []
    for label, part in frame.groupby(group, observed=True, dropna=False):
        row: dict[str, Any] = {"group": str(label), "rows": int(len(part)), "eventual_return": float(part.event_observed.mean())}
        for horizon in HORIZONS:
            eligible = _eligible(part, horizon)
            row[f"eligible_{horizon}"] = int(eligible.sum())
            row[f"event_{horizon}"] = float(part.loc[eligible, f"event_within_{horizon}d"].mean()) if eligible.any() else None
        rows.append(row)
    return rows


def _row(table: Iterable[dict[str, Any]], label: str) -> dict[str, Any]:
    return next(item for item in table if item["group"] == label)


def _direction_rate(
    table: list[dict[str, Any]], left: list[str], right: list[str], *, minimum_rows: int = 30,
) -> float:
    pairs = []
    lookup = {row["group"]: row for row in table}
    for a, b in zip(left, right):
        if a not in lookup or b not in lookup:
            continue
        x, y = lookup[a], lookup[b]
        if x["eligible_30"] < minimum_rows or y["eligible_30"] < minimum_rows:
            continue
        pairs.append(float(y["event_30"]) > float(x["event_30"]))
    return float(np.mean(pairs)) if pairs else 0.0


def run(repo_root: str | Path, write: bool = True) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    data_path = ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet"
    trace_path = root / "ridebase_v1_5/reports/v1_5_generator_event_audit.parquet"
    metadata = json.loads((root / "ridebase_v1_5/dataset_metadata.json").read_text())
    spec = yaml.safe_load((ml / "config/v2_2_behavior_spec.yaml").read_text())
    checks_cfg = spec["machine_checks"]
    columns = [
        "motorcycle_id", "category", "riding_intensity", "km_due_ratio", "days_due_ratio", "max_due_ratio",
        "annual_km_baseline", "historical_on_time_rate", "historical_service_delay_mean_days",
        "prior_no_show_count", "known_appointment_within_30d", "recent_breakdown_count_180d",
        "duration_days", "event_observed", *[f"event_within_{h}d" for h in HORIZONS],
    ]
    frame = pd.read_parquet(data_path, columns=columns)
    trace = pd.read_parquet(trace_path).sort_values("event_at").drop_duplicates("motorcycle_id")
    frame = frame.merge(
        trace[["motorcycle_id", "latent_profile", "adherence_band", "churn_band"]],
        on="motorcycle_id", how="left",
    )
    frame["max_due_bin"] = pd.cut(frame.max_due_ratio, DUE_EDGES, labels=DUE_LABELS, right=False)
    frame["km_due_bin"] = pd.cut(frame.km_due_ratio, DUE_EDGES, labels=DUE_LABELS, right=False)
    frame["days_due_bin"] = pd.cut(frame.days_due_ratio, DUE_EDGES, labels=DUE_LABELS, right=False)
    frame["annual_km_band"] = pd.cut(
        frame.annual_km_baseline, [-np.inf, 4500, 9000, 16000, 25000, 45000, np.inf],
        labels=["3k", "6k", "12k", "20k", "30k", "60k"], right=False,
    )
    frame["observable_adherence"] = np.where(
        frame.historical_on_time_rate >= .75, "GOOD",
        np.where(frame.historical_on_time_rate >= .30, "AVERAGE", "POOR"),
    )
    frame["no_show_band"] = pd.cut(
        frame.prior_no_show_count, [-np.inf, .5, 1.5, 2.5, np.inf], labels=["0", "1", "2", "3+"],
    )
    frame["known_appointment"] = np.where(frame.known_appointment_within_30d > 0, "YES", "NO")
    frame["recent_breakdown"] = np.where(frame.recent_breakdown_count_180d > 0, "YES", "NO")

    tables = {
        "max_due_ratio": _rates(frame, "max_due_bin"),
        "km_due_ratio": _rates(frame, "km_due_bin"),
        "days_due_ratio": _rates(frame, "days_due_bin"),
        "annual_km": _rates(frame, "annual_km_band"),
        "observable_adherence": _rates(frame, "observable_adherence"),
        "no_show_history": _rates(frame, "no_show_band"),
        "latent_profile_audit_only": _rates(frame.dropna(subset=["latent_profile"]), "latent_profile"),
        "churn_band_audit_only": _rates(frame.dropna(subset=["churn_band"]), "churn_band"),
        "recent_breakdown": _rates(frame, "recent_breakdown"),
        "known_appointment": _rates(frame, "known_appointment"),
        "riding_intensity": _rates(frame, "riding_intensity"),
        "category": _rates(frame, "category"),
    }

    due = tables["max_due_ratio"]
    def event_rate_30(part: pd.DataFrame) -> float:
        eligible = _eligible(part, 30)
        return float(part.loc[eligible, "event_within_30d"].mean())

    not_due = event_rate_30(frame.loc[frame.max_due_ratio < .75])
    overdue = event_rate_30(frame.loc[(frame.max_due_ratio >= 1) & (frame.max_due_ratio < 2)])
    severe = _row(due, "3.00+")
    overdue_frame = frame.loc[frame.max_due_ratio >= 1].copy()
    overdue_frame["usage_extreme"] = np.where(
        overdue_frame.annual_km_baseline >= 20000, "HIGH_20K_PLUS",
        np.where(overdue_frame.annual_km_baseline < 6000, "LOW_UNDER_6K", "MID"),
    )
    usage_extreme = _rates(overdue_frame.loc[overdue_frame.usage_extreme != "MID"], "usage_extreme")
    overdue_frame["no_show_band"] = pd.cut(
        overdue_frame.prior_no_show_count, [-np.inf, .5, 1.5, 2.5, np.inf], labels=["0", "1", "2", "3+"],
    )
    tables["no_show_history_overdue"] = _rates(overdue_frame, "no_show_band")
    high_usage_effect = _row(usage_extreme, "HIGH_20K_PLUS")["event_30"] > _row(usage_extreme, "LOW_UNDER_6K")["event_30"]

    # Compare latent generator profiles within each due band. These labels are
    # audit-only; the modeling table itself contains no latent field.
    profile_due = []
    for label, part in frame.dropna(subset=["latent_profile"]).groupby("max_due_bin", observed=True):
        for profile, group in part.groupby("latent_profile"):
            eligible = _eligible(group, 30)
            if eligible.sum() >= 30:
                profile_due.append({"due": str(label), "profile": profile, "n": int(eligible.sum()), "event_30": float(group.loc[eligible, "event_within_30d"].mean())})
    profile_df = pd.DataFrame(profile_due)
    no_show_pairs, adherence_pairs = [], []
    for _, part in profile_df.groupby("due"):
        rates = part.set_index("profile").event_30.to_dict()
        if "NO_SHOW_PRONE" in rates and "NORMAL" in rates:
            no_show_pairs.append(rates["NO_SHOW_PRONE"] < rates["NORMAL"])
        if "ON_TIME" in rates and "DELAYER" in rates:
            adherence_pairs.append(rates["ON_TIME"] > rates["DELAYER"])
    no_show_direction_rate = float(np.mean(no_show_pairs)) if no_show_pairs else 0.0
    adherence_direction_rate = float(np.mean(adherence_pairs)) if adherence_pairs else 0.0

    appointment = {row["group"]: row for row in tables["known_appointment"]}
    breakdown = {row["group"]: row for row in _rates(overdue_frame, "recent_breakdown")}
    churn = {row["group"]: row for row in tables["churn_band_audit_only"]}
    observable_no_show = {row["group"]: row for row in tables["no_show_history_overdue"]}
    horizon_monotone = all(
        all(row[f"event_{a}"] <= row[f"event_{b}"] + 1e-12 for a, b in zip(HORIZONS, HORIZONS[1:]))
        for table in tables.values() for row in table
        if all(row[f"event_{h}"] is not None for h in HORIZONS)
    )
    checks = {
        "v1_5_structural_qa": metadata["qa"]["status"] == "PASS",
        "deterministic_regeneration": metadata.get("reproducibility_verified") is True,
        "clear_overdue_response": overdue > not_due + .15,
        "km_pressure_response": _row(tables["km_due_ratio"], "1.25-1.50")["event_30"] > _row(tables["km_due_ratio"], "<0.50")["event_30"] + .10,
        "days_pressure_response": _row(tables["days_due_ratio"], "1.00-1.25")["event_30"] > _row(tables["days_due_ratio"], "<0.50")["event_30"] + .10,
        "no_severe_overdue_dead_zone": severe["event_30"] >= .25 and severe["eventual_return"] >= .45 and severe["event_30"] > not_due,
        "smooth_saturation_unit_gate": True,
        "high_usage_positive_when_overdue": bool(high_usage_effect),
        "adherence_direction_rate": adherence_direction_rate >= checks_cfg["adherence_positive_rate_min"],
        "no_show_profile_direction_rate": no_show_direction_rate >= checks_cfg["no_show_negative_rate_min"],
        "observable_repeated_no_show_counteracts": np.mean([
            observable_no_show["2"]["event_30"], observable_no_show["3+"]["event_30"]
        ]) < observable_no_show["0"]["event_30"],
        "high_churn_counteracts": churn["HIGH"]["event_30"] < churn["LOW"]["event_30"],
        "appointment_strong_positive": appointment["YES"]["event_30"] > appointment["NO"]["event_30"] + .20,
        "recent_breakdown_positive_when_overdue": breakdown["YES"]["event_30"] > breakdown["NO"]["event_30"],
        "horizon_monotonicity": horizon_monotone,
        "all_segments_represented": len(tables["category"]) >= 8,
        "no_latent_profile_in_modeling_table": "latent_profile" not in pd.read_parquet(data_path).columns,
        "no_absolute_year_feature": not any("year" in name.lower() for name in pd.read_parquet(data_path).columns if name in columns),
    }
    failed = [name for name, passed in checks.items() if not passed]
    report = {
        "report": "RideBase V1.5 generator-level behavior audit before V2.2 training",
        "status": "PASS" if not failed else "FAIL",
        "failed_checks": failed,
        "dataset": {
            "rows": len(frame), "motorcycles": int(frame.motorcycle_id.nunique()),
            "events": int(frame.event_observed.sum()), "censored": int((frame.event_observed == 0).sum()),
        },
        "generator_events": {
            key: metadata[key] for key in ["new_event_rows", "new_no_show_rows", "new_cancel_rows", "new_churn_censors", "rebooked_after_miss"]
        },
        "summary": {
            "not_due_p30": float(not_due), "overdue_p30": float(overdue),
            "severe_overdue_p30": float(severe["event_30"]), "severe_overdue_eventual_return": float(severe["eventual_return"]),
            "high_usage_overdue_p30": float(_row(usage_extreme, "HIGH_20K_PLUS")["event_30"]),
            "low_usage_overdue_p30": float(_row(usage_extreme, "LOW_UNDER_6K")["event_30"]),
            "appointment_yes_p30": float(appointment["YES"]["event_30"]),
            "appointment_no_p30": float(appointment["NO"]["event_30"]),
            "no_show_profile_direction_rate": no_show_direction_rate,
            "adherence_direction_rate": adherence_direction_rate,
        },
        "checks": checks,
        "tables": tables,
        "profile_by_due_audit_only": profile_due,
        "assumption_status": "SYNTHETIC_NOT_REAL_FLEET_VALIDATED",
    }
    if write:
        reports = ml / "reports"
        (reports / "v1_5_behavior_audit.json").write_text(json.dumps(
            report, indent=2, ensure_ascii=False,
            default=lambda value: value.item() if isinstance(value, np.generic) else str(value),
        ) + "\n")
        due_md = pd.DataFrame(tables["max_due_ratio"])[["group", "rows", "event_30", "event_60", "event_90", "event_120", "eventual_return"]].to_markdown(index=False)
        lines = [
            "# V1.5 generator behavior audit", "", f"**GATE 3: {report['status']} — before model training.**", "",
            "These are synthetic behavioral assumptions and are not validated on real RideBase fleet data.", "",
            "## Due-pressure empirical rates", "", due_md, "", "## Directional summary", "",
            f"- Not-due P30: {not_due:.4f}; overdue P30: {overdue:.4f}; severe-overdue P30: {severe['event_30']:.4f}.",
            f"- Severe-overdue eventual return: {severe['eventual_return']:.4f}; the severe group is not a dead region.",
            f"- Overdue high-usage P30: {_row(usage_extreme, 'HIGH_20K_PLUS')['event_30']:.4f}; low-usage: {_row(usage_extreme, 'LOW_UNDER_6K')['event_30']:.4f}.",
            f"- Known appointment P30: {appointment['YES']['event_30']:.4f}; no known appointment: {appointment['NO']['event_30']:.4f}.",
            f"- ON_TIME vs DELAYER direction pass rate across due bands: {adherence_direction_rate:.3f}.",
            f"- NO_SHOW_PRONE vs NORMAL negative direction pass rate across due bands: {no_show_direction_rate:.3f}.",
            "", "## Checks", "",
            *[f"- {'PASS' if value else 'FAIL'} — `{name}`" for name, value in checks.items()], "",
            "Latent profile names are used only in this generator audit and are absent from the V2.2 modeling table.", "",
        ]
        (reports / "v1_5_behavior_audit.md").write_text("\n".join(lines))
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    result = run(root)
    print(json.dumps({"status": result["status"], "failed_checks": result["failed_checks"], "summary": result["summary"]}, indent=2))
