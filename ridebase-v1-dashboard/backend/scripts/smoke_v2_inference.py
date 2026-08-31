#!/usr/bin/env python3
"""End-to-end smoke for the V2 survival service.

    python scripts/smoke_v2_inference.py            # in-process (TestClient)
    python scripts/smoke_v2_inference.py --url http://localhost:8000

Checks: health -> model/info -> features -> sample -> predict -> probability bounds ->
monotonicity -> determinism -> batch(100) -> golden parity vs nb15 TEST predictions.
Exit 0 only if every check passes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _client(url: str | None):
    if url:
        import httpx

        class _C:
            def get(self, p, **k):
                return httpx.get(url + p, timeout=30, **k)

            def post(self, p, **k):
                return httpx.post(url + p, timeout=60, **k)

        return _C()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    args = ap.parse_args()
    c = _client(args.url)

    h = c.get("/health").json()
    check("health.v2_model_loaded", h.get("v2_model_loaded") is True, str(h.get("v2_status")))
    check("health.real_fleet_pending", h.get("v2_real_fleet_validation") == "PENDING")

    mi = c.get("/api/v2/model/info").json()
    check("model/info.family", mi.get("model_family") == "ENSEMBLE[XGB_COX+COXNET]")
    check("model/info.not_production_validated", mi.get("status") == "SYNTHETICALLY_VALIDATED")

    fe = c.get("/api/v2/features").json()
    check("features.count==117", fe.get("feature_count") == 117)

    sample = c.get("/api/v2/sample").json()["features"]
    pr = c.post("/api/v2/predict", json={"features": sample, "snapshot_date": "2026-03-01"})
    check("predict.status_200", pr.status_code == 200, str(pr.status_code))
    p = pr.json().get("prediction", {})
    seq = [p.get(f"risk_{k}d") for k in (30, 60, 90, 120)]
    check("predict.bounds", all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in seq), str(seq))
    check("predict.monotonic", seq == sorted(seq), str(seq))
    check("predict.has_group_and_median",
          p.get("risk_group_90d") in ("LOW", "MEDIUM", "HIGH") and "median_service_days" in p)

    p2 = c.post("/api/v2/predict", json={"features": sample}).json()["prediction"]
    check("predict.deterministic",
          [p2[f"risk_{k}d"] for k in (30, 60, 90, 120)] == [p[f"risk_{k}d"] for k in (30, 60, 90, 120)])

    lk = c.post("/api/v2/predict", json={"features": {**sample, "duration_days": 10}})
    check("predict.leakage_rejected", lk.status_code == 422, str(lk.status_code))

    bt = c.post("/api/v2/predict/batch", json={"items": [sample] * 100})
    check("batch.100", bt.status_code == 200 and bt.json().get("n") == 100)

    # golden parity vs nb15 (only when the frozen data + notebook predictions are local)
    try:
        import numpy as np
        import pandas as pd
        from app.config import settings
        cfg = json.loads((settings.MODEL_DIR / "v2_advanced_config.json").read_text())
        cols = [x for x in cfg["feature_cols"] if x != "split"]
        mt = pd.read_parquet(settings.OUTPUTS_DIR / "v2_survival_modeling_table.parquet")
        pq = pd.read_parquet(settings.OUTPUTS_DIR / "v2_advanced_test_predictions.parquet")
        _slice = mt[mt.split == "TEST"][cols].head(50)
        rows = _slice.astype(object).where(pd.notna(_slice), None).to_dict("records")
        got = np.array([[q[f"risk_{k}d"] for k in (30, 60, 90, 120)]
                        for q in c.post("/api/v2/predict/batch", json={"items": rows}).json()["predictions"]])
        want = pq[[f"champion_risk_{k}" for k in (30, 60, 90, 120)]].head(50).to_numpy()
        d = float(np.abs(got - want).max())
        check("golden.parity_vs_nb15", d < 1e-6, f"max|Δ| = {d:.2e}")
    except Exception as exc:  # pragma: no cover
        check("golden.parity_vs_nb15", False, f"skipped: {exc}")

    failed = [n for n, ok, _ in CHECKS if not ok]
    print(f"\n{'ALL PASS' if not failed else 'FAILED: ' + ', '.join(failed)}  ({len(CHECKS)} checks)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
