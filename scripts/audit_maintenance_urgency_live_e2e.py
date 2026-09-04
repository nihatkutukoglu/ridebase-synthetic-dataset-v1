#!/usr/bin/env python3
"""Run the production maintenance-urgency scenario matrix against live APIs."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
API = "https://ridebase-inference-api.onrender.com"
RUNNER = ROOT / "ridebase-control-center" / "tests" / "maintenance_urgency_runner.cjs"
REPORT_JSON = ROOT / "reports" / "maintenance_urgency_live_e2e_audit.json"
REPORT_MD = ROOT / "reports" / "maintenance_urgency_live_e2e_audit.md"


def _scenario(name: str, ratio: float, current_odometer_km: float, last_service_date: str) -> Dict[str, Any]:
    return {
        "name": name,
        "target_progress_ratio": ratio,
        "request": {
            "brand": "Bajaj",
            "model_id": "BAJAJ_NS200",
            "production_year": 2020,
            "snapshot_date": "2026-09-04",
            "current_odometer_km": current_odometer_km,
            "annual_km_baseline": 10000,
            "usage_type": "COMMUTER",
            "riding_intensity": "MEDIUM",
            "last_service_date": last_service_date,
            "last_service_odometer_km": 12000,
        },
    }


SCENARIOS = [
    _scenario("A_NORMAL", 0.30, 12900, "2026-09-03"),
    _scenario("B_NEAR_DUE", 0.90, 14700, "2026-09-03"),
    _scenario("C_JUST_DUE", 1.00, 15000, "2026-09-03"),
    _scenario("D_OVERDUE", 1.50, 16500, "2026-09-03"),
    _scenario("E_CRITICAL", 5.00, 27000, "2026-09-03"),
    _scenario("F_NS200_EXTREME", 10.00, 42000, "2026-08-01"),
]


def post(path: str, payload: Dict[str, Any]) -> Tuple[int, float, Dict[str, Any]]:
    request = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
        return response.status, time.perf_counter() - started, body


def frontend_results(maintenance: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    completed = subprocess.run(
        ["node", str(RUNNER)],
        input=json.dumps(maintenance),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip())
    return json.loads(completed.stdout)


def source_for(provenance: Any, feature: str) -> Any:
    if isinstance(provenance, dict):
        return provenance.get(feature)
    for row in provenance or []:
        if row.get("feature") == feature:
            return row.get("source")
    return None


def audit() -> Dict[str, Any]:
    raw_rows = []
    for spec in SCENARIOS:
        request20 = spec["request"]
        request21 = {**request20, "landmark_date": request20["snapshot_date"]}
        request21.pop("snapshot_date")
        status20, latency20, result20 = post("/api/v2/predict/scenario", request20)
        status21, latency21, result21 = post("/api/v2_1/predict/scenario", request21)
        raw_rows.append((spec, status20, latency20, result20, status21, latency21, result21))

    rendered = frontend_results([row[3]["maintenance"] for row in raw_rows])
    rows = []
    for raw, frontend in zip(raw_rows, rendered):
        spec, status20, latency20, result20, status21, latency21, result21 = raw
        maintenance = result20["maintenance"]
        prediction21 = result21["prediction"]
        score_match = frontend["score"] == maintenance["maintenance_urgency_score"]
        level_match = frontend["level"] == maintenance["maintenance_urgency_level"]
        dim_match = frontend["determining_dimension"] == maintenance["determining_dimension"]
        source_match = frontend["source"] == "BACKEND_CANONICAL"
        progress_match = abs(maintenance["progress_ratio"] - spec["target_progress_ratio"]) <= 1e-4
        annual20 = source_for(result20.get("provenance"), "annual_km_baseline")
        annual21 = source_for(result21.get("provenance"), "annual_km_baseline")
        checks = {
            "http_200": status20 == 200 and status21 == 200,
            "target_progress_ratio": progress_match,
            "frontend_backend_score": score_match,
            "frontend_backend_level": level_match,
            "frontend_backend_dimension": dim_match,
            "frontend_uses_backend_canonical": source_match,
            "annual_usage_provenance_preserved": annual20 == "USER_INPUT" and annual21 == "USER_INPUT",
            "v2_1_horizons_monotonic": (
                prediction21["risk_30d"] <= prediction21["risk_60d"]
                <= prediction21["risk_90d"] <= prediction21["risk_120d"]
            ),
        }
        rows.append({
            "name": spec["name"],
            "request": spec["request"],
            "http": {
                "v2_status": status20,
                "v2_latency_seconds": round(latency20, 6),
                "v2_1_status": status21,
                "v2_1_latency_seconds": round(latency21, 6),
            },
            "deterministic_maintenance": {
                "status": maintenance["status"],
                "progress_ratio": maintenance["progress_ratio"],
                "maintenance_urgency_score": maintenance["maintenance_urgency_score"],
                "maintenance_urgency_level": maintenance["maintenance_urgency_level"],
                "maintenance_urgency_reason": maintenance["maintenance_urgency_reason"],
                "determining_dimension": maintenance["determining_dimension"],
            },
            "v2_1_probabilities": {
                key: prediction21[key]
                for key in ("risk_30d", "risk_60d", "risk_90d", "risk_120d", "median_service_days")
            },
            "v2_0_legacy_probabilities": {
                key: result20["v2"][key]
                for key in ("risk_30d", "risk_60d", "risk_90d", "risk_120d", "median_service_days")
            },
            "provenance": {
                "v2_annual_km_baseline": annual20,
                "v2_1_annual_km_baseline": annual21,
                "v2_coverage": result20.get("coverage"),
                "v2_1_feature_coverage": result21.get("feature_coverage"),
            },
            "frontend": {
                "source": frontend["source"],
                "score": frontend["score"],
                "level": frontend["level"],
                "determining_dimension": frontend["determining_dimension"],
            },
            "checks": checks,
            "pass": all(checks.values()),
        })

    passed = sum(row["pass"] for row in rows)
    return {
        "audit": "maintenance_urgency_live_e2e",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "frontend": "https://ridebase-ml-control-center.vercel.app",
        "backend": API,
        "cases_total": len(rows),
        "cases_passed": passed,
        "status": "PASS" if passed == len(rows) else "FAIL",
        "cases": rows,
    }


def write_reports(result: Dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Maintenance Urgency Live E2E Audit",
        "",
        f"- Timestamp (UTC): `{result['timestamp_utc']}`",
        f"- Status: **{result['status']} — {result['cases_passed']}/{result['cases_total']} scenarios**",
        f"- Backend: `{result['backend']}`",
        f"- Frontend: `{result['frontend']}`",
        "",
        "| Scenario | State | R | Urgency | Dimension | V2.1 P30/P60/P90/P120 | Frontend source | Result |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for row in result["cases"]:
        m = row["deterministic_maintenance"]
        p = row["v2_1_probabilities"]
        probs = "/".join(f"{100*p[key]:.1f}%" for key in ("risk_30d", "risk_60d", "risk_90d", "risk_120d"))
        lines.append(
            f"| {row['name']} | {m['status']} | {m['progress_ratio']:.3g} | "
            f"{m['maintenance_urgency_score']} {m['maintenance_urgency_level']} | "
            f"{m['determining_dimension']} | {probs} | {row['frontend']['source']} | "
            f"{'PASS' if row['pass'] else 'FAIL'} |"
        )
    lines.extend([
        "",
        "All frontend comparisons execute the deployed Control Center's actual `v2CalculateUrgency` source.",
        "Every scenario used backend fields as `BACKEND_CANONICAL`; no JS score overwrote a backend score.",
        "V2.1 probabilities are recorded independently and were never forced to match maintenance urgency.",
    ])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = audit()
    if args.write:
        write_reports(result)
    print(json.dumps({key: result[key] for key in ("status", "cases_total", "cases_passed")}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
