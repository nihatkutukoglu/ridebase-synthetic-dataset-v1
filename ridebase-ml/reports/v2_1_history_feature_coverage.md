# V2.1 synthetic history feature coverage

**Status: PASS. History source: `SYNTHETIC_V1_4`.**

Deterministic sample: 500 landmarks across 5 modeling roles.

Resolved features p10/p50/p90: 54 / 54 / 54 of 54.
Median coverage: 100.0%. Coverage is not confidence.

Warm latency p50/p95/max: 22.660 / 26.762 / 55.171 ms.

Commonly missing: none in frozen modeling-landmark sample.
Rarely available: none.

Frozen modeling landmarks are selected after a first service and have complete synthetic masters. Separate tests prove pre-service/empty history remains missing without initial-mileage fallback.

All point-in-time evidence checks passed.
