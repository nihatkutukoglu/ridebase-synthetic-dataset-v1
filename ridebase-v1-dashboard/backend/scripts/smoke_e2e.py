#!/usr/bin/env python3
"""End-to-end smoke test: sample -> preprocessor -> DAYS model -> KM model -> response.

Runs against a live API (default http://localhost:8000). Exit 0 = PASS.
Usage:  API_BASE=http://localhost:8000 python scripts/smoke_e2e.py
        (or, with no server running, `python scripts/smoke_e2e.py --inproc`)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on path


def _client():
    if "--inproc" in sys.argv:
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app), "in-process"
    import httpx
    base = os.environ.get("API_BASE", "http://localhost:8000")
    return httpx.Client(base_url=base, timeout=30), base


def main() -> int:
    client, where = _client()
    print(f"→ target: {where}")
    checks: list[tuple[str, bool, str]] = []

    h = client.get("/health").json()
    if not (h.get("days_model_loaded") and h.get("km_model_loaded")):
        print("SKIP: model artifacts absent (ridebase-ml/models/v1_final_*); "
              "health + leakage-guard shape still verified.")
        ok_shape = h["status"] == "degraded" and h["leakage_guard"] in ("PASS", "FAIL")
        print(f"  [{'PASS' if ok_shape else 'FAIL'}] degraded health shape")
        return 0 if ok_shape else 1
    checks.append(("health ok", h["status"] in ("ok", "degraded"), h["status"]))
    checks.append(("days model loaded", h["days_model_loaded"], ""))
    checks.append(("km model loaded", h["km_model_loaded"], ""))
    checks.append(("leakage guard PASS", h["leakage_guard"] == "PASS", h["leakage_guard"]))

    info = client.get("/api/v1/model/info").json()
    checks.append(("prod validation pending shown",
                   info["production_validation_status"].upper().startswith("PENDING"),
                   info["production_validation_status"]))

    feats = client.get("/api/v1/features").json()
    names = {f["name"] for f in feats["features"]}
    leak = names & {"next_service_days", "km_to_next_service", "days_to_next_service"}
    checks.append(("no target field in schema", not leak, str(leak)))

    sample = client.get("/api/v1/sample").json()
    r = client.post("/api/v1/predict", json={"features": sample["features"],
                                             "snapshot_date": sample["snapshot_date"],
                                             "strict": True})
    ok = r.status_code == 200
    body = r.json() if ok else {}
    checks.append(("predict 200", ok, r.text[:200]))
    if ok:
        p = body["prediction"]
        checks.append(("days >= 0", p["next_service_days"] >= 0, str(p["next_service_days"])))
        checks.append(("km >= 0", p["next_service_km"] >= 0, str(p["next_service_km"])))
        checks.append(("synthetic warning present",
                       "synthetic" in body["warning"].lower(), body["warning"][:60]))
        if sample["snapshot_date"]:
            checks.append(("estimated date derived",
                           body["derived"]["estimated_service_date"] is not None, ""))

    # determinism
    r2 = client.post("/api/v1/predict", json={"features": sample["features"],
                                              "snapshot_date": sample["snapshot_date"]})
    checks.append(("deterministic", ok and r2.json()["prediction"] == body["prediction"], ""))

    # invalid + leakage rejection
    checks.append(("negative odo -> 422",
                   client.post("/api/v1/predict", json={"features": {"snapshot_odometer_km": -1}}).status_code == 422,
                   ""))
    checks.append(("target field -> 422",
                   client.post("/api/v1/predict", json={"features": {"next_service_km": 5}}).status_code == 422,
                   ""))

    print()
    passed = 0
    for name, ok_, extra in checks:
        print(f"  [{'PASS' if ok_ else 'FAIL'}] {name}" + (f"  ({extra})" if extra and not ok_ else ""))
        passed += bool(ok_)
    print(f"\n{passed}/{len(checks)} checks passed")
    if ok:
        print("prediction:", json.dumps(body["prediction"]),
              "| derived:", json.dumps(body["derived"]))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
