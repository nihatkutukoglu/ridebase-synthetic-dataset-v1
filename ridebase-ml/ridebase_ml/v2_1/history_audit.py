"""Deterministic Prompt-2 coverage/performance audit for history reconstruction."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .adapters.synthetic import SyntheticRideBaseSourceAdapter
from .history_features import build_features
from .landmarks import FEATURE_COLUMNS


def run_coverage_audit(repo_root: str | Path, per_role: int = 100, write: bool = True) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    modeling_path = root / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet"
    frame = pd.read_parquet(modeling_path, columns=["motorcycle_id", "landmark_at", "modeling_role"])
    samples = [
        group.sample(min(per_role, len(group)), random_state=42)
        for _, group in frame.groupby("modeling_role", sort=True)
    ]
    sampled = (
        pd.concat(samples, ignore_index=True)
        .sort_values(["landmark_at", "motorcycle_id"])
        .reset_index(drop=True)
    )

    adapter = SyntheticRideBaseSourceAdapter(
        root / "ridebase_v1_4/source_tables",
        root / "ridebase-ml/config/source_schema_contract_v1_3.json",
    )
    resolved_counts: list[int] = []
    latency: list[float] = []
    missing = Counter()
    provenance = Counter()
    warning_counts = Counter()
    contract_violations = 0
    future_evidence_violations = 0

    for row in sampled.itertuples(index=False):
        landmark = pd.Timestamp(row.landmark_at).date().isoformat()
        started = time.perf_counter()
        result = build_features(row.motorcycle_id, landmark, adapter)
        latency.append((time.perf_counter() - started) * 1000.0)
        if list(result["features"]) != FEATURE_COLUMNS:
            contract_violations += 1
        resolved_counts.append(result["feature_coverage"]["resolved_count"])
        missing.update(result["feature_coverage"]["missing_features"])
        provenance.update(
            source for name, source in result["provenance"].items()
            if result["features"][name] is not None
        )
        warning_counts.update(result["warnings"])
        if any(
            effective is not None and effective > landmark
            for effective in result["source_evidence"]["max_effective_at"].values()
        ):
            future_evidence_violations += 1

    counts = pd.Series(resolved_counts, dtype=float)
    warm = pd.Series(latency[1:] if len(latency) > 1 else latency, dtype=float)
    availability = {
        name: round(1.0 - missing[name] / len(sampled), 6) for name in FEATURE_COLUMNS
    }
    report: dict[str, Any] = {
        "report": "RideBase V2.1 synthetic history feature coverage",
        "status": "PASS" if contract_violations == 0 and future_evidence_violations == 0 else "FAIL",
        "history_source": adapter.history_source,
        "sample": {
            "landmarks": int(len(sampled)),
            "per_role_requested": int(per_role),
            "modeling_role_counts": sampled["modeling_role"].value_counts().sort_index().to_dict(),
            "random_seed": 42,
        },
        "supported_motorcycles": adapter.supported_motorcycle_count,
        "supported_tables": list(adapter.supported_tables),
        "tables_loaded_by_builder": adapter.cache_info()["loaded_tables"],
        "feature_contract_count": len(FEATURE_COLUMNS),
        "resolved_feature_count": {
            "p10": float(counts.quantile(0.10)),
            "p50": float(counts.quantile(0.50)),
            "p90": float(counts.quantile(0.90)),
        },
        "median_coverage": round(float(counts.median() / len(FEATURE_COLUMNS)), 6),
        "most_commonly_missing": [
            {"feature": name, "missing_landmarks": int(count), "missing_rate": round(count / len(sampled), 6)}
            for name, count in missing.most_common(15)
        ],
        "features_resolved_over_90_percent": [name for name in FEATURE_COLUMNS if availability[name] > 0.90],
        "rarely_available_features": [name for name in FEATURE_COLUMNS if availability[name] < 0.10],
        "availability_by_feature": availability,
        "resolved_provenance_distribution": dict(sorted(provenance.items())),
        "warning_counts": dict(warning_counts),
        "latency_ms": {
            "cold_first": latency[0] if latency else None,
            "warm_p50": round(float(warm.quantile(0.50)), 3),
            "warm_p95": round(float(warm.quantile(0.95)), 3),
            "warm_max": round(float(warm.max()), 3),
        },
        "cache": adapter.cache_info(),
        "checks": {
            "exact_frozen_contract_every_row": contract_violations == 0,
            "no_future_source_evidence": future_evidence_violations == 0,
            "disk_read_once_per_loaded_table": all(
                count == 1 for count in adapter.cache_info()["disk_reads_by_table"].values()
            ),
            "coverage_is_not_confidence": True,
        },
        "sparse_history_note": (
            "Frozen modeling landmarks are selected after a first service and have complete synthetic masters. "
            "Separate tests prove pre-service/empty history remains missing without initial-mileage fallback."
        ),
    }
    if write:
        reports = root / "ridebase-ml/reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "v2_1_history_feature_coverage.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        )
        lines = [
            "# V2.1 synthetic history feature coverage",
            "",
            f"**Status: {report['status']}. History source: `{adapter.history_source}`.**",
            "",
            f"Deterministic sample: {len(sampled)} landmarks across "
            f"{len(report['sample']['modeling_role_counts'])} modeling roles.",
            "",
            f"Resolved features p10/p50/p90: {report['resolved_feature_count']['p10']:.0f} / "
            f"{report['resolved_feature_count']['p50']:.0f} / {report['resolved_feature_count']['p90']:.0f} of 54.",
            f"Median coverage: {report['median_coverage']:.1%}. Coverage is not confidence.",
            "",
            f"Warm latency p50/p95/max: {report['latency_ms']['warm_p50']:.3f} / "
            f"{report['latency_ms']['warm_p95']:.3f} / {report['latency_ms']['warm_max']:.3f} ms.",
            "",
            f"Commonly missing: {report['most_commonly_missing'] or 'none in frozen modeling-landmark sample'}.",
            f"Rarely available: {report['rarely_available_features'] or 'none'}.",
            "",
            report["sparse_history_note"],
            "",
            "All point-in-time evidence checks passed." if report["checks"]["no_future_source_evidence"] else "Future evidence violation detected.",
            "",
        ]
        (reports / "v2_1_history_feature_coverage.md").write_text("\n".join(lines))
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    result = run_coverage_audit(root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
