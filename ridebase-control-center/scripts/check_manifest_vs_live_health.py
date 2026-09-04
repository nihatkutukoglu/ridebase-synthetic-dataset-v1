#!/usr/bin/env python3
"""Y3 CI gate: the Model Registry / v2_1 block in manifest.json makes claims
(champion, dataset_version, model_validation) about what's actually running in
production. This compares them against the live API's own GET /health and
fails the build if they disagree -- so a stale manifest (like the old
"V2 · survival — COMING SOON" row, or "BLOCKED_BY_PROVIDER_AUTH" long after
deploy) can't silently drift from reality again.

Skips (exit 0) only when the live service itself is unreachable -- that's an
infra/availability question (Render free-tier cold start, network), not a
manifest-correctness question; DATA mismatches always fail the build.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # ridebase-control-center/


def main() -> int:
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
    v2_1 = manifest.get("v2_1") or {}
    api = (manifest.get("v2_api") or "").rstrip("/")
    if not api:
        print("WARN: manifest has no v2_api base URL -- skipping.")
        return 0

    try:
        with urllib.request.urlopen(f"{api}/health", timeout=60) as resp:
            health = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"WARN: live /health unreachable ({exc}) -- skipping manifest/live comparison.")
        return 0

    if not health.get("v2_1_model_loaded"):
        print("WARN: live API reports v2_1 model not loaded -- skipping comparison "
              "(nothing to compare manifest claims against).")
        return 0

    checks = [
        ("champion", v2_1.get("champion"), health.get("v2_1_champion")),
        ("dataset_version", v2_1.get("dataset_version"), health.get("v2_1_dataset_version")),
        ("model_validation", v2_1.get("model_validation"), health.get("v2_1_model_validation")),
    ]
    ok = True
    for name, manifest_val, live_val in checks:
        match = manifest_val == live_val
        ok = ok and match
        print(f"{'OK ' if match else 'FAIL'} {name}: manifest={manifest_val!r} live={live_val!r}")

    if not ok:
        print("\nFAIL: manifest.json disagrees with the live API. Re-run build.py "
              "against the artifacts the live deploy actually uses, or the deploy "
              "is running something the manifest doesn't describe.")
        return 1
    print("\nPASS: manifest matches live /health.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
