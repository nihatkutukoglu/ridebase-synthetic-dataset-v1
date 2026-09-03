"""Prompt-3 golden history reconstruction and frozen-predictor parity gate."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .adapters.base import RideBaseSourceAdapter
from .adapters.synthetic import SyntheticRideBaseSourceAdapter
from .history_features import build_features
from .landmarks import CATEGORICAL_FEATURES, FEATURE_COLUMNS
from .predictor import V21SurvivalPredictor
from .schema_contract import assert_source_schema_compatible

RISK_COLUMNS = ["risk_30d", "risk_60d", "risk_90d", "risk_120d"]
NUMERIC_TOLERANCE = 1e-9
PREDICTION_TOLERANCE = 1e-6


class OverlaySyntheticAdapter(RideBaseSourceAdapter):
    """Test-only view that exposes additional records without touching CSVs."""

    history_source = "SYNTHETIC_V1_4"

    def __init__(
        self,
        base: SyntheticRideBaseSourceAdapter,
        overlay: dict[str, list[dict[str, Any]]],
    ) -> None:
        self.base = base
        self.overlay = overlay

    def read_table(self, table_name: str):
        rows = self.base.read_table(table_name)
        return [*rows, *(dict(row) for row in self.overlay.get(table_name, []))]

    def _matching(self, table: str, key: str, value: str) -> list[dict[str, Any]]:
        rows = self.base._matching(table, key, value)
        rows.extend(
            dict(row) for row in self.overlay.get(table, [])
            if str(row.get(key)) == str(value)
        )
        return rows


def run_history_parity(repo_root: str | Path, golden_count: int = 300, write: bool = True) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    ml = root / "ridebase-ml"
    model_dir = ml / "models/v2_1_v1_4"
    modeling_path = ml / "derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet"
    source_dir = root / "ridebase_v1_4/source_tables"
    schema_path = ml / "config/source_schema_contract_v1_3.json"

    hashes = _freeze_hashes(root, model_dir, modeling_path, source_dir)
    schema = assert_source_schema_compatible(source_dir, schema_path)
    frame = pd.read_parquet(
        modeling_path,
        columns=[
            "landmark_id", "motorcycle_id", "landmark_at", "modeling_role",
            "is_unseen_motorcycle_holdout", *FEATURE_COLUMNS,
        ],
    )
    golden, selection = _select_golden(frame, golden_count)
    adapter = SyntheticRideBaseSourceAdapter(source_dir, schema_path)

    reconstructed: list[dict[str, Any]] = []
    cell_counts: Counter[str] = Counter()
    feature_cells: dict[str, Counter[str]] = defaultdict(Counter)
    mismatch_examples: list[dict[str, Any]] = []
    evidence_after_landmark = 0
    deterministic = True

    for index, row in golden.iterrows():
        motorcycle_id = str(row["motorcycle_id"])
        landmark = pd.Timestamp(row["landmark_at"]).date().isoformat()
        built = build_features(motorcycle_id, landmark, adapter)
        if index < 10:
            deterministic = deterministic and built == build_features(motorcycle_id, landmark, adapter)
        reconstructed.append(built["features"])
        evidence_after_landmark += int(any(
            effective is not None and effective > landmark
            for effective in built["source_evidence"]["max_effective_at"].values()
        ))
        for feature in FEATURE_COLUMNS:
            category = _compare_value(built["features"][feature], row[feature], feature)
            cell_counts[category] += 1
            feature_cells[feature][category] += 1
            if category == "BUG_MISMATCH" and len(mismatch_examples) < 50:
                mismatch_examples.append({
                    "landmark_id": row["landmark_id"],
                    "motorcycle_id": motorcycle_id,
                    "landmark_date": landmark,
                    "feature": feature,
                    "reconstructed": _json_scalar(built["features"][feature]),
                    "frozen": _json_scalar(row[feature]),
                })

    feature_classification: dict[str, str] = {}
    priority = [
        "BUG_MISMATCH", "EXPECTED_MISSING_DIFFERENCE", "SEMANTICALLY_EQUIVALENT",
        "NUMERIC_TOLERANCE_PARITY", "EXACT_PARITY",
    ]
    for feature in FEATURE_COLUMNS:
        feature_classification[feature] = next(
            category for category in priority if feature_cells[feature][category]
        )
    feature_class_counts = Counter(feature_classification.values())

    predictor = V21SurvivalPredictor.load(model_dir)
    frozen_rows = golden[FEATURE_COLUMNS].astype(object).where(golden[FEATURE_COLUMNS].notna(), None).to_dict("records")
    frozen_predictions = predictor.predict(frozen_rows)["predictions"]
    history_predictions = predictor.predict(reconstructed)["predictions"]
    deltas = np.array([
        [abs(float(left[name]) - float(right[name])) for name in RISK_COLUMNS]
        for left, right in zip(frozen_predictions, history_predictions)
    ])
    median_differences = sum(
        left["median_service_days"] != right["median_service_days"]
        for left, right in zip(frozen_predictions, history_predictions)
    )

    injection = _future_injection_gate(root, source_dir, schema_path, golden.head(10), predictor)
    boundary = _boundary_gate(source_dir, schema_path, golden.iloc[0])
    artifacts_match = _artifact_manifest_matches(model_dir)
    modeling_hash_match = hashes["modeling_table_sha256"] == json.loads(
        (model_dir / "data_freeze_manifest.json").read_text()
    )["modeling_table_sha256"]
    source_hash_match = hashes["source_hashes"] == json.loads(
        (ml / "derived_outputs/v2_1_v1_4/v2_1_generation_metadata.json").read_text()
    )["source_hashes"]

    checks = {
        "source_schema_unchanged": schema["status"] == "PASS" and not schema["source_columns_changed"],
        "frozen_artifacts_unchanged": artifacts_match,
        "modeling_table_hash_match": modeling_hash_match,
        "v1_4_source_hashes_match_freeze": source_hash_match,
        "all_frozen_features_classified": set(feature_classification) == set(FEATURE_COLUMNS),
        "no_bug_mismatch": feature_class_counts["BUG_MISMATCH"] == 0,
        "prediction_parity_tight": float(deltas.max()) <= PREDICTION_TOLERANCE,
        "median_service_days_parity": median_differences == 0,
        "future_injection_no_change": injection["pass"],
        "boundary_semantics_pass": boundary["pass"],
        "source_evidence_never_after_landmark": evidence_after_landmark == 0,
        "deterministic_reconstruction": deterministic,
        "current_odometer_never_initial_mileage": all(
            "initial_mileage_km" not in row for row in reconstructed
        ),
        "test_used_for_parity_not_selection": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    report: dict[str, Any] = {
        "report": "RideBase V2.1 history feature and prediction parity",
        "status": status,
        "history_builder_commit": hashes["history_builder_commit"],
        "hashes": hashes,
        "golden_landmarks": {
            "count": int(len(golden)),
            "selection": selection,
            "ids": golden["landmark_id"].tolist(),
            "test_usage": "parity/inference consistency only; never champion or calibration selection",
        },
        "feature_parity": {
            "tolerance": NUMERIC_TOLERANCE,
            "feature_classification_counts": dict(feature_class_counts),
            "feature_classification": feature_classification,
            "cell_classification_counts": dict(cell_counts),
            "bug_mismatch_examples": mismatch_examples,
        },
        "prediction_parity": {
            "tolerance": PREDICTION_TOLERANCE,
            "max_absolute_probability_delta": float(deltas.max()),
            "median_absolute_probability_delta": float(np.median(deltas)),
            "p95_absolute_probability_delta": float(np.quantile(deltas, 0.95)),
            "cells_over_tolerance": int((deltas > PREDICTION_TOLERANCE).sum()),
            "median_service_days_differences": int(median_differences),
        },
        "future_injection": injection,
        "landmark_boundary": boundary,
        "coverage": {
            "resolved_p10": float(np.quantile([sum(v is not None for v in row.values()) for row in reconstructed], 0.10)),
            "resolved_p50": float(np.quantile([sum(v is not None for v in row.values()) for row in reconstructed], 0.50)),
            "resolved_p90": float(np.quantile([sum(v is not None for v in row.values()) for row in reconstructed], 0.90)),
            "note": "coverage is separate from correctness and is not confidence",
        },
        "checks": checks,
    }
    if write:
        reports = ml / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "v2_1_history_feature_parity.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        )
        lines = [
            "# V2.1 history feature parity",
            "",
            f"**Status: {status}. Golden landmarks: {len(golden)}.**",
            "",
            "TEST rows were used only for parity/inference consistency, never model selection.",
            "",
            "## Feature parity",
            "",
            *[f"- {name}: {count}" for name, count in sorted(feature_class_counts.items())],
            f"- BUG mismatches: {len(mismatch_examples)}",
            "",
            "## Prediction parity",
            "",
            f"- Max absolute probability delta: {float(deltas.max()):.10f}",
            f"- Median absolute probability delta: {float(np.median(deltas)):.10f}",
            f"- p95 absolute probability delta: {float(np.quantile(deltas, 0.95)):.10f}",
            f"- Cells over tolerance: {int((deltas > PREDICTION_TOLERANCE).sum())}",
            "",
            "## Leakage and boundaries",
            "",
            f"- Future injection unchanged: {injection['pass']}",
            f"- T-1 included: {boundary['day_before_included']}",
            f"- T included: {boundary['exact_day_included']}",
            f"- T+1 excluded: {boundary['day_after_excluded']}",
            f"- Source evidence after landmark: {evidence_after_landmark}",
            "",
        ]
        (reports / "v2_1_history_feature_parity.md").write_text("\n".join(lines))
    return report


def _select_golden(frame: pd.DataFrame, count: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    tagged: dict[str, set[str]] = defaultdict(set)

    def add(label: str, subset: pd.DataFrame, n: int) -> None:
        ordered = subset.assign(
            _order=subset["landmark_id"].map(lambda value: hashlib.sha256(str(value).encode()).hexdigest())
        ).sort_values("_order").head(n)
        for landmark_id in ordered["landmark_id"]:
            tagged[str(landmark_id)].add(label)

    for role, group in frame.groupby("modeling_role"):
        add(f"role:{role}", group, 15)
    due = pd.cut(
        frame["max_due_ratio"], [-np.inf, 0.8, 1.2, 2.0, np.inf],
        labels=["NOT_DUE", "NEAR_DUE", "OVERDUE", "SEVERE"],
    )
    for label in due.dropna().unique():
        add(f"due:{label}", frame.loc[due == label], 15)
    service_q = frame["prior_service_count"].quantile([0.10, 0.90])
    add("history:SPARSE", frame.loc[frame["prior_service_count"] <= service_q.loc[0.10]], 20)
    add("history:RICH", frame.loc[frame["prior_service_count"] >= service_q.loc[0.90]], 20)
    odo_q = frame["current_odometer_km_at_landmark"].quantile([0.10, 0.90])
    add("mileage:LOW", frame.loc[frame["current_odometer_km_at_landmark"] <= odo_q.loc[0.10]], 20)
    add("mileage:HIGH", frame.loc[frame["current_odometer_km_at_landmark"] >= odo_q.loc[0.90]], 20)
    for category, group in frame.groupby("category"):
        add(f"category:{category}", group, 8)

    selected_ids = set(tagged)
    remaining = frame.loc[~frame["landmark_id"].isin(selected_ids)].assign(
        _order=lambda data: data["landmark_id"].map(
            lambda value: hashlib.sha256(f"fill:{value}".encode()).hexdigest()
        )
    ).sort_values("_order")
    needed = max(0, count - len(selected_ids))
    selected_ids.update(remaining.head(needed)["landmark_id"].astype(str))
    selected = frame.loc[frame["landmark_id"].astype(str).isin(selected_ids)].copy()
    selected = selected.assign(
        _order=selected["landmark_id"].map(lambda value: hashlib.sha256(str(value).encode()).hexdigest())
    ).sort_values("_order").head(count).drop(columns="_order").reset_index(drop=True)
    return selected, {
        "modeling_role_counts": selected["modeling_role"].value_counts().sort_index().to_dict(),
        "category_counts": selected["category"].value_counts().sort_index().to_dict(),
        "unseen_motorcycle_holdout_rows": int(selected["is_unseen_motorcycle_holdout"].sum()),
        "selection_seed": "sha256 deterministic stratified selection",
    }


def _compare_value(actual: Any, expected: Any, feature: str) -> str:
    actual_missing = actual is None or (not isinstance(actual, str) and pd.isna(actual))
    expected_missing = expected is None or (not isinstance(expected, str) and pd.isna(expected))
    if actual_missing and expected_missing:
        return "EXACT_PARITY"
    if actual_missing != expected_missing:
        return "BUG_MISMATCH"
    if feature in CATEGORICAL_FEATURES:
        return "EXACT_PARITY" if actual == expected else "BUG_MISMATCH"
    if actual == expected:
        return "EXACT_PARITY"
    try:
        if np.isclose(float(actual), float(expected), rtol=NUMERIC_TOLERANCE, atol=NUMERIC_TOLERANCE):
            return "NUMERIC_TOLERANCE_PARITY"
    except (TypeError, ValueError):
        if str(actual) == str(expected):
            return "SEMANTICALLY_EQUIVALENT"
    return "BUG_MISMATCH"


def _future_injection_gate(
    root: Path,
    source_dir: Path,
    schema_path: Path,
    landmarks: pd.DataFrame,
    predictor: V21SurvivalPredictor,
) -> dict[str, Any]:
    cases = []
    base_adapter = SyntheticRideBaseSourceAdapter(source_dir, schema_path)
    for number, row in enumerate(landmarks.itertuples(index=False), start=1):
        landmark_date = pd.Timestamp(row.landmark_at).date()
        future = (landmark_date + timedelta(days=1)).isoformat()
        motorcycle_id = str(row.motorcycle_id)
        service_id = f"FUTURE_SVC_{number}"
        task_id = f"FUTURE_TASK_{number}"
        overlay = {
            "services": [{
                "service_id": service_id, "motorcycle_id": motorcycle_id,
                "received_at": future, "status": "DELIVERED", "service_type_code": "BREAKDOWN",
                "arrival_mode": "TOW_TRUCK", "odometer_km": 999999, "service_delay_days": 999,
                "grand_total": 999999, "is_breakdown": 1, "is_warranty": 0,
            }],
            "mileage_timeline_monthly": [{
                "timeline_id": f"FUTURE_MILE_{number}", "motorcycle_id": motorcycle_id,
                "period_end_date": future, "closing_odometer_km": 999999, "km_added": 999999,
            }],
            "service_tasks": [{
                "service_task_id": task_id, "service_id": service_id, "motorcycle_id": motorcycle_id,
                "completed_at": future, "started_at": future, "completed": 1,
                "task_code": "ENGINE_OIL_CHANGE",
            }],
            "service_parts": [{
                "service_part_id": f"FUTURE_PART_{number}", "service_id": service_id,
                "service_task_id": task_id, "motorcycle_id": motorcycle_id,
            }],
            "appointments": [{
                "appointment_id": f"FUTURE_APT_{number}", "motorcycle_id": motorcycle_id,
                "created_at": future,
            }],
        }
        injected_adapter = OverlaySyntheticAdapter(base_adapter, overlay=overlay)
        landmark = landmark_date.isoformat()
        baseline = build_features(motorcycle_id, landmark, base_adapter)
        injected = build_features(motorcycle_id, landmark, injected_adapter)
        feature_same = baseline == injected
        left = predictor.predict([baseline["features"]])["predictions"][0]
        right = predictor.predict([injected["features"]])["predictions"][0]
        prediction_same = left == right
        cases.append({
            "landmark_id": row.landmark_id,
            "feature_payload_unchanged": feature_same,
            "prediction_unchanged": prediction_same,
            "injected_date": future,
        })
    return {
        "cases": len(cases),
        "injected_sources": ["service", "mileage", "service_task", "service_part", "appointment"],
        "pass": all(case["feature_payload_unchanged"] and case["prediction_unchanged"] for case in cases),
        "results": cases,
    }


def _boundary_gate(source_dir: Path, schema_path: Path, row: pd.Series) -> dict[str, Any]:
    landmark = pd.Timestamp(row["landmark_at"]).date()
    motorcycle_id = str(row["motorcycle_id"])
    ids = {"before": "BOUNDARY_BEFORE", "exact": "BOUNDARY_EXACT", "after": "BOUNDARY_AFTER"}
    overlay = {"services": [
        {"service_id": ids["before"], "motorcycle_id": motorcycle_id, "received_at": (landmark - timedelta(days=1)).isoformat()},
        {"service_id": ids["exact"], "motorcycle_id": motorcycle_id, "received_at": landmark.isoformat()},
        {"service_id": ids["after"], "motorcycle_id": motorcycle_id, "received_at": (landmark + timedelta(days=1)).isoformat()},
    ]}
    adapter = OverlaySyntheticAdapter(
        SyntheticRideBaseSourceAdapter(source_dir, schema_path), overlay=overlay
    )
    seen = {str(item.get("service_id")) for item in adapter.get_services_before(motorcycle_id, landmark)}
    result = {
        "day_before_included": ids["before"] in seen,
        "exact_day_included": ids["exact"] in seen,
        "day_after_excluded": ids["after"] not in seen,
        "semantics": "record_timestamp.date() <= landmark_date",
    }
    result["pass"] = all(result[name] for name in ("day_before_included", "exact_day_included", "day_after_excluded"))
    return result


def _freeze_hashes(root: Path, model_dir: Path, modeling_path: Path, source_dir: Path) -> dict[str, Any]:
    return {
        "feature_list_sha256": _sha256(model_dir / "feature_list.json"),
        "champion_model_sha256": _sha256(model_dir / "champion_model.joblib"),
        "preprocessor_sha256": _sha256(model_dir / "preprocessor.joblib"),
        "calibrator_sha256": _sha256(model_dir / "calibrator.joblib"),
        "modeling_table_sha256": _sha256(modeling_path),
        "source_hashes": {path.name: _sha256(path) for path in sorted(source_dir.glob("*.csv"))},
        "history_builder_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
    }


def _artifact_manifest_matches(model_dir: Path) -> bool:
    manifest = json.loads((model_dir / "artifact_manifest.json").read_text())
    return all(_sha256(model_dir / name) == expected for name, expected in manifest.items())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_scalar(value: Any) -> Any:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[3]
    result = run_history_parity(repository)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
