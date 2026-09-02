"""Golden parity: the packaged V21SurvivalPredictor must reproduce the frozen
Phase-3 TEST predictions bit-for-bit (within float tolerance)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .landmarks import FEATURE_COLUMNS
from .predictor import V21SurvivalPredictor

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models" / "v2_1_v1_4"
MODELING_TABLE = ROOT / "derived_outputs" / "v2_1_v1_4" / "v2_1_modeling_table.parquet"
RISK_COLS = ["risk_30d", "risk_60d", "risk_90d", "risk_120d"]


def run(sample: int | None = 4000, tol: float = 5e-4) -> dict[str, Any]:
    frozen = pd.read_parquet(MODEL_DIR / "frozen_test_predictions.parquet")
    features = pd.read_parquet(
        MODELING_TABLE, filters=[("modeling_role", "==", "TEST")],
        columns=["landmark_id", *FEATURE_COLUMNS],
    )
    merged = frozen.merge(features, on="landmark_id", validate="one_to_one")
    if sample and len(merged) > sample:
        merged = merged.sample(sample, random_state=42).reset_index(drop=True)

    predictor = V21SurvivalPredictor.load(MODEL_DIR)
    rows = merged[FEATURE_COLUMNS].to_dict("records")
    first = predictor.predict(rows)["predictions"]
    second = predictor.predict(rows)["predictions"]

    got = np.array([[p[c] for c in RISK_COLS] for p in first])
    expected = merged[RISK_COLS].to_numpy(float)
    deltas = np.abs(got - expected)
    got2 = np.array([[p[c] for c in RISK_COLS] for p in second])

    result = {
        "rows": int(len(merged)),
        "max_probability_delta": float(deltas.max()),
        "mean_probability_delta": float(deltas.mean()),
        "risk_score_max_delta": float(np.abs(
            np.array([p["risk_score"] for p in first]) - merged["risk_score"].to_numpy(float)
        ).max()),
        "horizon_monotonic": bool(np.all(np.diff(got, axis=1) >= -1e-9)),
        "deterministic": bool(np.array_equal(got, got2)),
        "tolerance": tol,
    }
    result["parity_pass"] = (
        result["max_probability_delta"] <= tol
        and result["horizon_monotonic"]
        and result["deterministic"]
    )
    (MODEL_DIR / "golden_parity.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    raise SystemExit(0 if run()["parity_pass"] else 1)
