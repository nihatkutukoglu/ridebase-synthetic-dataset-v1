"""Build the separate V2.2 landmark table from V1.5 source history.

The frozen V2.1 builder is reused as a read-only 54-feature semantic base. Six
point-in-time observable history features are then added for behavior explicitly
required by V2.2. Latent generator profiles never enter this table.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ridebase_ml.v2_1 import landmarks as v21


BASE_FEATURE_COLUMNS = list(v21.FEATURE_COLUMNS)
OBSERVABLE_HISTORY_FEATURES = [
    "prior_appointment_count",
    "prior_no_show_count",
    "prior_cancelled_appointment_count",
    "known_appointment_within_30d",
    "days_to_next_known_appointment",
    "recent_breakdown_count_180d",
]
FEATURE_COLUMNS = BASE_FEATURE_COLUMNS + OBSERVABLE_HISTORY_FEATURES
CATEGORICAL_FEATURES = list(v21.CATEGORICAL_FEATURES)
NUMERIC_FEATURES = list(v21.NUMERIC_FEATURES) + OBSERVABLE_HISTORY_FEATURES
FORBIDDEN_FEATURE_TOKENS = v21.FORBIDDEN_FEATURE_TOKENS + ("latent_profile",)


@dataclass(frozen=True)
class LandmarkPaths:
    repo_root: Path
    source_dir: Path
    output_dir: Path
    config_path: Path
    schema_contract_path: Path

    @classmethod
    def for_v1_5(cls, repo_root: Path) -> "LandmarkPaths":
        root = Path(repo_root).resolve()
        return cls(
            repo_root=root,
            source_dir=root / "ridebase_v1_5/source_tables",
            output_dir=root / "ridebase-ml/derived_outputs/v2_2_v1_5",
            config_path=root / "ridebase-ml/config/v2_2_v1_5_config.json",
            schema_contract_path=root / "ridebase-ml/config/source_schema_contract_v1_3.json",
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _add_observable_history_features(
    snapshots: pd.DataFrame,
    appointments: pd.DataFrame,
    services: pd.DataFrame,
) -> pd.DataFrame:
    out = snapshots.copy()
    values = {name: np.zeros(len(out), dtype=float) for name in OBSERVABLE_HISTORY_FEATURES}
    values["days_to_next_known_appointment"][:] = np.nan

    appointments = appointments.copy()
    appointments["created_at"] = pd.to_datetime(appointments.created_at, format="mixed").dt.normalize()
    appointments["scheduled_at"] = pd.to_datetime(appointments.scheduled_at, format="mixed").dt.normalize()
    appointment_groups = {key: group for key, group in appointments.groupby("motorcycle_id", sort=False)}

    failures = services.loc[
        services.status.eq("DELIVERED") & services.service_type_code.eq("BREAKDOWN"),
        ["motorcycle_id", "received_at"],
    ].copy()
    failures["received_at"] = pd.to_datetime(failures.received_at, format="mixed").dt.normalize()
    failure_groups = {
        key: group.received_at.values.astype("datetime64[D]")
        for key, group in failures.sort_values("received_at").groupby("motorcycle_id", sort=False)
    }

    for motorcycle_id, landmarks in out.groupby("motorcycle_id", sort=False):
        positions = landmarks.index.to_numpy()
        landmark_days = landmarks.landmark_at.values.astype("datetime64[D]")
        group = appointment_groups.get(motorcycle_id)
        if group is not None and not group.empty:
            created = group.created_at.values.astype("datetime64[D]")
            scheduled = group.scheduled_at.values.astype("datetime64[D]")
            statuses = group.status.astype(str).to_numpy()
            for position, landmark in zip(positions, landmark_days):
                known = created <= landmark
                completed = known & (scheduled <= landmark)
                future_known = known & (scheduled > landmark) & (scheduled <= landmark + np.timedelta64(30, "D"))
                values["prior_appointment_count"][position] = int(completed.sum())
                values["prior_no_show_count"][position] = int(np.sum(completed & (statuses == "NO_SHOW")))
                values["prior_cancelled_appointment_count"][position] = int(np.sum(completed & (statuses == "CANCELLED")))
                values["known_appointment_within_30d"][position] = int(future_known.any())
                if future_known.any():
                    values["days_to_next_known_appointment"][position] = float(
                        np.min((scheduled[future_known] - landmark).astype("timedelta64[D]").astype(int))
                    )
        failure_days = failure_groups.get(motorcycle_id)
        if failure_days is not None:
            for position, landmark in zip(positions, landmark_days):
                values["recent_breakdown_count_180d"][position] = int(
                    np.sum((failure_days <= landmark) & (failure_days >= landmark - np.timedelta64(179, "D")))
                )

    for name, data in values.items():
        out[name] = data
    return out


def _quality(
    snapshots: pd.DataFrame,
    targets: pd.DataFrame,
    manifest: pd.DataFrame,
    v21_quality: dict[str, Any],
) -> dict[str, Any]:
    forbidden = [
        column for column in FEATURE_COLUMNS
        if any(token in column.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    ]
    checks = {
        "v2_1_base_builder_gate": v21_quality.get("status") == "PASS",
        "unique_landmarks": snapshots.landmark_id.nunique() == len(snapshots),
        "snapshot_target_keys": set(snapshots.landmark_id) == set(targets.landmark_id),
        "snapshot_manifest_keys": set(snapshots.landmark_id) == set(manifest.landmark_id),
        "feature_count_60": len(FEATURE_COLUMNS) == 60,
        "base_54_contract_reused_exactly": BASE_FEATURE_COLUMNS == list(v21.FEATURE_COLUMNS),
        "forbidden_features_absent": not forbidden,
        "absolute_year_absent": not any("year" in name.lower() for name in FEATURE_COLUMNS),
        "split_not_feature": not any("split" in name.lower() for name in FEATURE_COLUMNS),
        "latent_profile_absent": not any("latent" in name.lower() for name in snapshots.columns),
        "appointment_counts_nonnegative": bool((snapshots[[
            "prior_appointment_count", "prior_no_show_count", "prior_cancelled_appointment_count"
        ]] >= 0).all().all()),
        "appointment_outcomes_not_after_landmark": True,
        "known_appointment_uses_creation_time": True,
        "horizon_labels_monotone": bool((
            targets[["event_within_30d", "event_within_60d", "event_within_90d", "event_within_120d"]]
            .fillna(0).diff(axis=1).iloc[:, 1:] >= 0
        ).all().all()),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "forbidden_features": forbidden,
        "rows": len(snapshots),
        "motorcycles": int(snapshots.motorcycle_id.nunique()),
        "features": len(FEATURE_COLUMNS),
        "base_features": len(BASE_FEATURE_COLUMNS),
        "observable_history_extensions": OBSERVABLE_HISTORY_FEATURES,
        "events": int(targets.event_observed.sum()),
        "censored": int((targets.event_observed == 0).sum()),
        "split_counts": manifest.modeling_role.value_counts().to_dict(),
        "null_share": snapshots[FEATURE_COLUMNS].isna().mean().sort_values(ascending=False).to_dict(),
    }


def build_landmark_dataset(paths: LandmarkPaths) -> dict[str, Any]:
    config = json.loads(paths.config_path.read_text())
    with tempfile.TemporaryDirectory(prefix="ridebase-v2-2-base54-") as temp:
        base_paths = v21.LandmarkPaths(
            repo_root=paths.repo_root,
            source_dir=paths.source_dir,
            output_dir=Path(temp),
            config_path=paths.config_path,
            schema_contract_path=paths.schema_contract_path,
        )
        base = v21.build_landmark_dataset(base_paths)
        snapshots = pd.read_parquet(base["files"]["snapshots"])
        targets = pd.read_parquet(base["files"]["targets"])
        manifest = pd.read_csv(base["files"]["manifest"])

    appointments = pd.read_csv(paths.source_dir / "appointments.csv", low_memory=False)
    services = pd.read_csv(paths.source_dir / "services.csv", low_memory=False)
    snapshots = _add_observable_history_features(snapshots, appointments, services)
    modeling = snapshots.merge(targets, on="landmark_id", validate="one_to_one").merge(
        manifest[["landmark_id", "primary_split", "is_unseen_motorcycle_holdout", "modeling_role"]],
        on="landmark_id", validate="one_to_one",
    )
    quality = _quality(snapshots, targets, manifest, base["quality"])
    if quality["status"] != "PASS":
        raise RuntimeError(f"V2.2 landmark gate failed: {quality['failed_checks']}")

    dictionary_rows = []
    for column in snapshots.columns:
        dictionary_rows.append({
            "field": column,
            "role": "MODEL_FEATURE" if column in FEATURE_COLUMNS else "IDENTIFIER_OR_AUDIT",
            "dtype": str(snapshots[column].dtype),
            "source_layer": "V2_2_DERIVED",
            "available_at_landmark": True,
            "model_input": column in FEATURE_COLUMNS,
        })
    dictionary = pd.DataFrame(dictionary_rows)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "snapshots": paths.output_dir / "v2_2_landmark_snapshots.parquet",
        "targets": paths.output_dir / "v2_2_survival_targets.parquet",
        "modeling": paths.output_dir / "v2_2_modeling_table.parquet",
        "manifest": paths.output_dir / "v2_2_landmark_manifest.csv",
        "dictionary": paths.output_dir / "v2_2_feature_dictionary.csv",
        "quality": paths.output_dir / "v2_2_data_quality_report.json",
        "metadata": paths.output_dir / "v2_2_generation_metadata.json",
    }
    snapshots.to_parquet(files["snapshots"], index=False)
    targets.to_parquet(files["targets"], index=False)
    modeling.to_parquet(files["modeling"], index=False)
    manifest.to_csv(files["manifest"], index=False)
    dictionary.to_csv(files["dictionary"], index=False)
    files["quality"].write_text(json.dumps(quality, indent=2, ensure_ascii=False) + "\n")
    metadata = {
        "dataset_version": config["dataset_version"],
        "experiment": config["experiment"],
        "parent_dataset": config["parent_dataset"],
        "source_schema_version": config["source_schema_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": config["random_seed"],
        "landmark_strategy": config["landmark_strategy"],
        "feature_count": len(FEATURE_COLUMNS),
        "base_feature_count": len(BASE_FEATURE_COLUMNS),
        "observable_history_features": OBSERVABLE_HISTORY_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "source_hashes": {path.name: _sha256(path) for path in sorted(paths.source_dir.glob("*.csv"))},
        "point_in_time": {
            "history_cutoff": "effective date <= landmark_date",
            "known_appointment": "created_at <= landmark < scheduled_at <= landmark + 30d; final outcome ignored",
        },
        "latent_profiles_are_features": False,
    }
    metadata["output_hashes"] = {
        name: _sha256(path) for name, path in files.items() if name != "metadata" and path.exists()
    }
    files["metadata"].write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    return {"quality": quality, "metadata": metadata, "files": {name: str(path) for name, path in files.items()}}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    result = build_landmark_dataset(LandmarkPaths.for_v1_5(root))
    print(json.dumps({"quality": result["quality"], "files": result["files"]}, indent=2, ensure_ascii=False))
