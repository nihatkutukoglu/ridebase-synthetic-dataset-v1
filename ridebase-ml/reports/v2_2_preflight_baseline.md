# RideBase V2.2 challenger preflight

**GATE 0: PASS.** The safe baseline is `main` at `a6b6501`, exactly synchronized with `origin/main`.

The frozen inventory records the V1.4 generator/source release, V2.1 modeling table, 54-feature list, champion, preprocessor, isotonic calibrator, baseline hazard, memory-safe SQLite history store, production backend service, and production Control Center hashes. These hashes are the end-of-workflow preservation gate.

Baseline regression suites passed:

- ML/data/history: 58
- backend/API: 83
- Control Center: 25
- total: 166

One untracked report, `ridebase-ml/reports/v2_1_prompt_6_memory_safe_serving.md`, was already present at preflight. It is preserved byte-for-byte and is not a V2.2 implementation change.

V2.1 remains the production champion, no deployment is authorized, real-fleet validation is pending, and V3 remains on hold.
