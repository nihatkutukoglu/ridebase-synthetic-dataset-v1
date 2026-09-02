"""Reproduce V2.0 live-scenario failures as a machine-readable regression spec."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def run_v2_0_audit(repo_root: Path) -> Dict[str, Any]:
    # Import lazily and add the existing backend package path so one reproducible
    # command works from the repository root.
    root = Path(repo_root).resolve()
    backend_path = str(root / "ridebase-v1-dashboard" / "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    from app.v2_scenario import derive_scenario
    from app.v2_schemas import V2ScenarioRequest
    from ridebase_ml.v2 import V2SurvivalPredictor

    predictor = V2SurvivalPredictor.load(root / "ridebase-ml" / "models")

    def score(**overrides: Any) -> Dict[str, Any]:
        payload = {
            "brand": "Bajaj",
            "model_id": "BAJAJ_NS200",
            "production_year": 2016,
            "snapshot_date": "2026-08-01",
            "current_odometer_km": 15_000,
            "annual_km_baseline": 10_000,
            "usage_type": "COMMUTER",
            "riding_intensity": "HIGH",
            "last_service_date": "2026-02-02",
            "last_service_odometer_km": 9_000,
        }
        payload.update(overrides)
        request = V2ScenarioRequest(**payload)
        built = derive_scenario(request, predictor)
        pred = predictor.predict(dict(built["features"], snapshot_date=request.snapshot_date.isoformat()))
        return {"input": payload, "prediction": pred, "maintenance": built["maintenance"], "features": built["features"]}

    km_cases = []
    for km_since in [500, 2_000, 6_000, 10_000, 20_000]:
        result = score(current_odometer_km=9_000 + km_since)
        km_cases.append({"km_since_last_service": km_since, **{
            key: result["prediction"][key] for key in ("risk_30d", "risk_60d", "risk_90d", "risk_120d")
        }})

    day_cases = []
    snapshot = pd.Timestamp("2026-08-01")
    for days_since in [30, 90, 180, 365, 730]:
        result = score(last_service_date=(snapshot - pd.Timedelta(days=days_since)).date().isoformat())
        day_cases.append({"days_since_last_service": days_since, **{
            key: result["prediction"][key] for key in ("risk_30d", "risk_60d", "risk_90d", "risk_120d")
        }})

    year_cases = []
    for year in [2023, 2024, 2025, 2026]:
        snap = pd.Timestamp(year=year, month=8, day=1)
        result = score(
            production_year=year - 10,
            snapshot_date=snap.date().isoformat(),
            last_service_date=(snap - pd.Timedelta(days=180)).date().isoformat(),
        )
        year_cases.append({"snapshot_year": year, **{
            key: result["prediction"][key] for key in ("risk_30d", "risk_60d", "risk_90d", "risk_120d")
        }})

    base = score()
    artifact_cases = []
    for days_observed in [100, 500, 1_000, 1_500]:
        features = dict(base["features"], days_observed=days_observed, snapshot_date="2026-08-01")
        pred = predictor.predict(features)
        artifact_cases.append({"days_observed": days_observed, **{
            key: pred[key] for key in ("risk_30d", "risk_60d", "risk_90d", "risk_120d")
        }})

    zero_grid = []
    for km_since in [500, 2_000, 6_000, 10_000, 20_000]:
        for days_since in [30, 90, 180, 365, 730]:
            for usage_type in ["COMMUTER", "COURIER", "TOURING", "WEEKEND"]:
                snap = pd.Timestamp("2026-08-01")
                result = score(
                    current_odometer_km=9_000 + km_since,
                    last_service_date=(snap - pd.Timedelta(days=days_since)).date().isoformat(),
                    usage_type=usage_type,
                )
                zero_grid.append({
                    "km": km_since, "days": days_since, "usage_type": usage_type,
                    "risk_30d": result["prediction"]["risk_30d"],
                })

    def spread(rows: List[Dict[str, Any]], key: str) -> float:
        values = [float(row[key]) for row in rows]
        return max(values) - min(values)

    checks = {
        "service_event_landmark_mismatch": {
            "status": "FAIL",
            "evidence": "v1.3 ml_snapshot_contract is post-service; scenario route serves arbitrary snapshot_date",
        },
        "exact_zero_30d_collapse": {
            "status": "FAIL" if sum(row["risk_30d"] == 0.0 for row in zero_grid) / len(zero_grid) >= 0.5 else "PASS",
            "exact_zero_count": sum(row["risk_30d"] == 0.0 for row in zero_grid),
            "case_count": len(zero_grid),
            "exact_zero_rate": round(sum(row["risk_30d"] == 0.0 for row in zero_grid) / len(zero_grid), 6),
        },
        "km_since_service_sensitivity": {
            "status": "FAIL" if spread(km_cases, "risk_90d") < 0.05 else "PASS",
            "risk_90d_spread": round(spread(km_cases, "risk_90d"), 8),
        },
        "elapsed_time_direction": {
            "status": "FAIL" if day_cases[-1]["risk_90d"] < day_cases[0]["risk_90d"] else "PASS",
            "risk_90d_first": day_cases[0]["risk_90d"],
            "risk_90d_last": day_cases[-1]["risk_90d"],
        },
        "absolute_calendar_invariance": {
            # The absolute spread is >3 percentage points in a low-risk regime
            # (more than a 3x relative swing), which is materially large.
            "status": "FAIL" if spread(year_cases, "risk_90d") > 0.02 else "PASS",
            "risk_90d_spread": round(spread(year_cases, "risk_90d"), 8),
        },
        "observation_artifact_invariance": {
            "status": "FAIL" if spread(artifact_cases, "risk_90d") > 0.05 else "PASS",
            "risk_90d_spread": round(spread(artifact_cases, "risk_90d"), 8),
        },
        "overdue_product_contradiction": {
            "status": "FAIL" if base["maintenance"]["status"] == "OVERDUE" and base["prediction"]["risk_90d"] < 0.05 else "PASS",
            "maintenance_status": base["maintenance"]["status"],
            "risk_90d": base["prediction"]["risk_90d"],
        },
    }
    failed = [name for name, check in checks.items() if check["status"] == "FAIL"]
    return {
        "audit": "V2.0 live-scenario regression audit",
        "model_status": "SYNTHETIC RESEARCH BASELINE — FAILED LIVE-SCENARIO AUDIT",
        "overall_status": "FAIL" if failed else "PASS",
        "failed_checks": failed,
        "checks": checks,
        "cases": {
            "km_since_last_service": km_cases,
            "days_since_last_service": day_cases,
            "calendar_year": year_cases,
            "days_observed_artifact": artifact_cases,
            "zero_30d_grid": zero_grid,
        },
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    report = run_v2_0_audit(root)
    output = root / "ridebase-ml" / "reports" / "v2_1_live_behavior_audit.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    matrix = []
    for name, check in report["checks"].items():
        matrix.append({
            "test": name,
            "system": "V2.0",
            "status": check["status"],
            "required_for_v2_1": "PASS",
        })
    for name in [
        "km_since_service_sensitivity", "elapsed_time_direction", "absolute_calendar_invariance",
        "annual_usage_plausibility", "due_vs_not_due", "same_input_determinism",
        "horizon_monotonicity", "exact_zero_30d_collapse", "observation_artifact_invariance",
        "input_validation",
    ]:
        matrix.append({
            "test": name,
            "system": "V2.1",
            "status": "BLOCKED_BY_SYNTHETIC_DATA_GATE",
            "required_for_v2_1": "PASS",
        })
    pd.DataFrame(matrix).to_csv(root / "ridebase-ml" / "reports" / "v2_1_metamorphic_tests.csv", index=False)
    print(json.dumps({"status": report["overall_status"], "failed_checks": report["failed_checks"]}, indent=2))
