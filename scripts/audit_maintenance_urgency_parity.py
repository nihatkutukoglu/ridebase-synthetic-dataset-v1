#!/usr/bin/env python3
"""Compare the canonical Python urgency policy with the actual frontend fallback."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
ML_ROOT = ROOT / "ridebase-ml"
RUNNER = ROOT / "ridebase-control-center" / "tests" / "maintenance_urgency_runner.cjs"
REPORT_JSON = ROOT / "reports" / "maintenance_urgency_frontend_backend_parity.json"
REPORT_MD = ROOT / "reports" / "maintenance_urgency_frontend_backend_parity.md"
TOLERANCE = 1e-9

sys.path.insert(0, str(ML_ROOT))
from ridebase_ml.policy.urgency import calculate_maintenance_urgency  # noqa: E402


RATIOS = [
    0.0, 0.10, 0.25, 0.50, 0.526, 0.75, 0.80, 0.90, 0.99,
    1.00, 1.10, 1.25, 1.50, 1.75, 2.00, 3.00, 5.00, 10.00,
]


def _case(
    name: str,
    progress_ratio: float,
    km_ratio: Optional[float] = None,
    day_ratio: Optional[float] = None,
    overdue_km: Optional[float] = None,
    overdue_days: Optional[float] = None,
) -> Dict[str, Any]:
    status = "OVERDUE" if progress_ratio >= 1 else "DUE_SOON" if progress_ratio >= 0.8 else "NOT_DUE"
    frontend: Dict[str, Any] = {
        "status": status,
        "progress_ratio": progress_ratio,
        "progress_pct": progress_ratio * 100,
        "overdue_km": overdue_km,
        "overdue_days": overdue_days,
    }
    if km_ratio is not None:
        frontend["km_progress_ratio"] = km_ratio
    if day_ratio is not None:
        frontend["time_progress_ratio"] = day_ratio
    return {
        "name": name,
        "python_args": {
            "progress_ratio": progress_ratio,
            "km_ratio": km_ratio,
            "day_ratio": day_ratio,
            "overdue_km": overdue_km,
            "overdue_days": overdue_days,
        },
        "frontend_input": frontend,
    }


def parity_cases() -> List[Dict[str, Any]]:
    cases = [_case(f"progress_ratio_{ratio:g}", ratio) for ratio in RATIOS]
    cases.extend([
        _case("km_dominant", 1.25, km_ratio=1.25, day_ratio=0.40, overdue_km=750),
        _case("time_dominant", 1.25, km_ratio=0.40, day_ratio=1.25, overdue_days=45),
        _case("both_within_tolerance", 1.25, km_ratio=1.250, day_ratio=1.245),
        _case("missing_optional_fields", 0.526),
        _case("extreme_overdue", 10.0, km_ratio=10.0, day_ratio=0.20, overdue_km=27000),
    ])
    return cases


def run_frontend(inputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    completed = subprocess.run(
        ["node", str(RUNNER)],
        input=json.dumps(inputs),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Frontend parity runner failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def audit() -> Dict[str, Any]:
    specs = parity_cases()
    frontend_results = run_frontend([case["frontend_input"] for case in specs])
    rows = []
    for spec, frontend in zip(specs, frontend_results):
        canonical = calculate_maintenance_urgency(**spec["python_args"])
        checks = {
            "score": abs(frontend["score"] - canonical["maintenance_urgency_score"]) <= TOLERANCE,
            "score_exact": abs(frontend["score_exact"] - canonical["maintenance_urgency_score_exact"]) <= TOLERANCE,
            "level": frontend["level"] == canonical["maintenance_urgency_level"],
            "determining_dimension": frontend["determining_dimension"] == canonical["determining_dimension"],
            "saturation": (frontend["score"] == 100) == (canonical["maintenance_urgency_score"] == 100),
            "fallback_source": frontend["source"] == "FRONTEND_FALLBACK",
        }
        rows.append({
            "name": spec["name"],
            "input": spec["python_args"],
            "canonical_python": {
                "score": canonical["maintenance_urgency_score"],
                "score_exact": canonical["maintenance_urgency_score_exact"],
                "level": canonical["maintenance_urgency_level"],
                "determining_dimension": canonical["determining_dimension"],
            },
            "frontend_fallback": {
                "score": frontend["score"],
                "score_exact": frontend["score_exact"],
                "level": frontend["level"],
                "determining_dimension": frontend["determining_dimension"],
                "source": frontend["source"],
            },
            "checks": checks,
            "pass": all(checks.values()),
        })
    passed = sum(row["pass"] for row in rows)
    return {
        "audit": "maintenance_urgency_frontend_backend_parity",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_source": "ridebase_ml.policy.urgency.calculate_maintenance_urgency",
        "frontend_source": "ridebase-control-center/template.html::v2CalculateUrgency",
        "tolerance": TOLERANCE,
        "cases_total": len(rows),
        "cases_passed": passed,
        "parity_percent": round(100.0 * passed / len(rows), 2),
        "status": "PASS" if passed == len(rows) else "FAIL",
        "cases": rows,
    }


def write_reports(result: Dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Maintenance Urgency Frontend ↔ Backend Parity",
        "",
        f"- Timestamp (UTC): `{result['timestamp_utc']}`",
        f"- Status: **{result['status']}**",
        f"- Coverage: **{result['cases_passed']}/{result['cases_total']} ({result['parity_percent']:.2f}%)**",
        f"- Numerical tolerance: `{result['tolerance']}`",
        "- Canonical source: `ridebase_ml.policy.urgency.calculate_maintenance_urgency`",
        "- Frontend fallback: actual `v2CalculateUrgency` extracted from `template.html` and executed with Node.js",
        "",
        "The matrix covers every requested progress ratio, KM/TIME/BOTH dominance, missing optional fields,",
        "boundary rounding, saturation, and extreme overdue behavior. Backend fields remain canonical; this",
        "audit only proves the behavior of the absence/error fallback.",
        "",
        "| Case | Python score | JS score | Level | Dimension | Result |",
        "|---|---:|---:|---|---|---|",
    ]
    for row in result["cases"]:
        py = row["canonical_python"]
        js = row["frontend_fallback"]
        lines.append(
            f"| {row['name']} | {py['score']} ({py['score_exact']:.1f}) | "
            f"{js['score']} ({js['score_exact']:.1f}) | {js['level']} | "
            f"{js['determining_dimension']} | {'PASS' if row['pass'] else 'FAIL'} |"
        )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write the JSON and Markdown audit reports")
    args = parser.parse_args()
    result = audit()
    if args.write:
        write_reports(result)
    print(json.dumps({key: result[key] for key in ("status", "cases_total", "cases_passed", "parity_percent")}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
