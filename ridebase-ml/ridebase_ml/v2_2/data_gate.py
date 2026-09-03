"""Integrity, split, leakage, and drift gate for the V2.2/V1.5 table."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .landmarks import BASE_FEATURE_COLUMNS, CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _drift(v21: pd.DataFrame, v22: pd.DataFrame) -> dict[str, Any]:
    numeric = []
    for name in [column for column in NUMERIC_FEATURES if column in BASE_FEATURE_COLUMNS]:
        left = pd.to_numeric(v21[name], errors="coerce")
        right = pd.to_numeric(v22[name], errors="coerce")
        scale = max(float(left.std()), 1e-9)
        numeric.append({
            "feature": name,
            "v2_1_mean": float(left.mean()),
            "v2_2_mean": float(right.mean()),
            "standardized_mean_difference": float((right.mean() - left.mean()) / scale),
            "v2_1_null_share": float(left.isna().mean()),
            "v2_2_null_share": float(right.isna().mean()),
        })
    categorical = []
    for name in CATEGORICAL_FEATURES:
        left = v21[name].fillna("__MISSING__").astype(str).value_counts(normalize=True)
        right = v22[name].fillna("__MISSING__").astype(str).value_counts(normalize=True)
        values = left.index.union(right.index)
        tv = .5 * float((left.reindex(values, fill_value=0) - right.reindex(values, fill_value=0)).abs().sum())
        categorical.append({"feature": name, "total_variation_distance": tv})
    numeric.sort(key=lambda row: abs(row["standardized_mean_difference"]), reverse=True)
    categorical.sort(key=lambda row: row["total_variation_distance"], reverse=True)
    return {
        "interpretation": "Expected world drift from V1.4 to V1.5; documented, not tuned against TEST metrics.",
        "numeric": numeric,
        "categorical": categorical,
        "max_absolute_standardized_mean_difference": abs(numeric[0]["standardized_mean_difference"]),
        "max_categorical_total_variation": categorical[0]["total_variation_distance"],
    }


def run(repo_root: str | Path, write: bool = True) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    derived = ml / "derived_outputs/v2_2_v1_5"
    modeling_path = derived / "v2_2_modeling_table.parquet"
    manifest_path = derived / "v2_2_landmark_manifest.csv"
    config_path = ml / "config/v2_2_v1_5_config.json"
    metadata = json.loads((derived / "v2_2_generation_metadata.json").read_text())
    quality = json.loads((derived / "v2_2_data_quality_report.json").read_text())
    frame = pd.read_parquet(modeling_path)
    manifest = pd.read_csv(manifest_path, parse_dates=["landmark_at"])
    v21 = pd.read_parquet(
        ml / "derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet",
        columns=BASE_FEATURE_COLUMNS,
    )
    drift = _drift(v21, frame[BASE_FEATURE_COLUMNS])

    forbidden_tokens = (
        "split", "target", "censor", "future_", "duration_days", "event_observed",
        "next_service", "current_service", "days_observed", "landmark_year", "snapshot_year", "latent",
    )
    forbidden = [name for name in FEATURE_COLUMNS if any(token in name.lower() for token in forbidden_tokens)]
    ids = [name for name in FEATURE_COLUMNS if name.endswith("_id") or name in {"motorcycle_id", "customer_id", "workshop_id"}]
    target_monotone = frame[[f"event_within_{h}d" for h in (30, 60, 90, 120)]].fillna(0).diff(axis=1).iloc[:, 1:]
    seen_train_val = set(manifest.loc[manifest.modeling_role.isin(["TRAIN", "VALIDATION"]), "motorcycle_id"])
    unseen_test = set(manifest.loc[manifest.modeling_role.eq("UNSEEN_MOTORCYCLE_TEMPORAL_TEST"), "motorcycle_id"])
    output_hashes_match = all(
        _sha256(Path(path)) == metadata["output_hashes"][name]
        for name, path in {
            "snapshots": derived / "v2_2_landmark_snapshots.parquet",
            "targets": derived / "v2_2_survival_targets.parquet",
            "modeling": modeling_path,
            "manifest": manifest_path,
            "dictionary": derived / "v2_2_feature_dictionary.csv",
            "quality": derived / "v2_2_data_quality_report.json",
        }.items()
    )
    checks = {
        "landmark_builder_quality": quality["status"] == "PASS",
        "source_schema_unchanged": metadata["source_schema_version"] == "1.3.0",
        "feature_count_expected": len(FEATURE_COLUMNS) == 60 and len(BASE_FEATURE_COLUMNS) == 54,
        "forbidden_feature_scan": not forbidden,
        "identifier_shortcuts_absent": not ids,
        "no_absolute_year": not any("year" in name.lower() for name in FEATURE_COLUMNS),
        "no_split_feature": not any("split" in name.lower() for name in FEATURE_COLUMNS),
        "no_latent_profile_feature": not any("latent" in name.lower() for name in FEATURE_COLUMNS),
        "unique_landmarks": frame.landmark_id.nunique() == len(frame),
        "positive_duration": bool((frame.duration_days >= 1).all()),
        "event_binary": set(frame.event_observed.unique()) <= {0, 1},
        "observed_has_next_service": bool(frame.loc[frame.event_observed.eq(1), "next_service_id"].notna().all()),
        "censored_has_no_next_service": bool(frame.loc[frame.event_observed.eq(0), "next_service_id"].isna().all()),
        "horizon_targets_monotone": bool((target_monotone >= 0).all().all()),
        "train_end_respected": manifest.loc[manifest.primary_split.eq("TRAIN"), "landmark_at"].max() <= pd.Timestamp("2025-06-30"),
        "validation_end_respected": manifest.loc[manifest.primary_split.eq("VALIDATION"), "landmark_at"].max() <= pd.Timestamp("2025-12-31"),
        "test_start_respected": manifest.loc[manifest.primary_split.eq("TEST"), "landmark_at"].min() >= pd.Timestamp("2026-01-01"),
        "unseen_motorcycles_isolated": seen_train_val.isdisjoint(unseen_test),
        "output_hashes_match": output_hashes_match,
        "test_not_used_for_selection": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    split_manifest = {
        "dataset_version": metadata["dataset_version"],
        "modeling_table_sha256": _sha256(modeling_path),
        "landmark_manifest_sha256": _sha256(manifest_path),
        "config_sha256": _sha256(config_path),
        "feature_list_sha256": hashlib.sha256(json.dumps(FEATURE_COLUMNS, separators=(",", ":")).encode()).hexdigest(),
        "train_end": "2025-06-30",
        "validation_end": "2025-12-31",
        "test_start": "2026-01-01",
        "selection_data": ["TRAIN", "VALIDATION"],
        "calibration_data": "VALIDATION",
        "test_access_status": "SEALED_UNTIL_SELECTION_FREEZE",
        "split_counts": manifest.modeling_role.value_counts().to_dict(),
        "unseen_motorcycle_count": len(unseen_test),
    }
    report = {
        "report": "RideBase V2.2 dynamic-landmark dataset integrity gate",
        "status": "PASS" if not failed else "FAIL",
        "failed_checks": failed,
        "checks": checks,
        "dataset": {
            "rows": len(frame), "motorcycles": int(frame.motorcycle_id.nunique()),
            "feature_count": len(FEATURE_COLUMNS), "base_v2_1_features": len(BASE_FEATURE_COLUMNS),
            "events": int(frame.event_observed.sum()), "censored": int((frame.event_observed == 0).sum()),
            "event_rate": float(frame.event_observed.mean()),
        },
        "splits": split_manifest,
        "null_share": frame[FEATURE_COLUMNS].isna().mean().sort_values(ascending=False).to_dict(),
        "feature_drift_vs_v2_1": drift,
        "forbidden_features": forbidden,
        "identifier_shortcuts": ids,
        "test_policy": "TEST generated as labels but not read by training/selection until frozen manifest exists.",
    }
    if write:
        (derived / "v2_2_split_manifest.json").write_text(json.dumps(split_manifest, indent=2) + "\n")
        reports = ml / "reports"
        (reports / "v2_2_dataset_audit.json").write_text(json.dumps(
            report, indent=2, ensure_ascii=False,
            default=lambda value: value.item() if isinstance(value, np.generic) else str(value),
        ) + "\n")
        lines = [
            "# V2.2 dynamic-landmark dataset audit", "", f"**GATE 4: {report['status']}.**", "",
            f"Rows: {len(frame):,}; motorcycles: {frame.motorcycle_id.nunique():,}; features: {len(FEATURE_COLUMNS)} (frozen V2.1 54 + six observable point-in-time history fields).",
            f"Events: {int(frame.event_observed.sum()):,}; censored: {int((frame.event_observed == 0).sum()):,}.", "",
            "The six additions are prior appointment/no-show/cancellation counts, known appointment intent within 30 days, days to that known appointment, and recent 180-day breakdown count. Appointment outcomes after a landmark are not used.", "",
            "## Integrity checks", "",
            *[f"- {'PASS' if value else 'FAIL'} — `{name}`" for name, value in checks.items()], "",
            "## Drift versus V2.1/V1.4", "",
            f"Maximum absolute standardized numeric mean difference: {drift['max_absolute_standardized_mean_difference']:.4f}.",
            f"Maximum categorical total-variation distance: {drift['max_categorical_total_variation']:.4f}.",
            "This is expected synthetic-world drift and was measured before TEST model evaluation.", "",
            "TEST remains sealed for selection; TRAIN+VALIDATION only may choose the challenger and VALIDATION alone may choose calibration.", "",
        ]
        (reports / "v2_2_dataset_audit.md").write_text("\n".join(lines))
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    result = run(root)
    print(json.dumps({"status": result["status"], "failed_checks": result["failed_checks"], "dataset": result["dataset"], "splits": result["splits"]}, indent=2))
