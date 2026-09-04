# Phase 7 — True Extreme Overdue Regression

The previous session's "extreme overdue" case was not actually overdue: it
used 3000 km since service against what turned out to be a 5000 km figure
(the broader OEM interval, not the actual live maintenance-policy interval).
This run queries the **real live endpoints** and uses whatever policy they
resolve, rather than assuming a number.

## Scenario

Bajaj Pulsar NS200 (`model_id: BAJAJ_NS200`), 2019, landmark/snapshot
2026-09-04, current odometer 40 000 km, last service 2026-08-01 at
10 000 km, user-supplied `annual_km_baseline` 24 000 km/yr, `riding_intensity: HIGH`.

## Real policy resolved live (not assumed)

`POST /api/v2/predict/scenario` resolved the actual RideBase Türkiye
operational policy for this model/year: **`interval_km: 3000`**,
`interval_months: 6` (`interval_days: 182.62`), task `ENGINE_OIL_CHANGE`,
`trigger_mode: WHICHEVER_FIRST`. This is different from the 5000 km OEM
figure seen in the previous session's V2.1 feature-resolution output — two
distinct fields in this codebase (broader OEM spec vs. RideBase's own
operational policy) — and it is this operational one that drives Maintenance
Due/Urgency.

## Deterministic maintenance result (live)

| Field | Value |
|---|---|
| km_since_service | 30,000 km |
| days_since_service | 34 |
| overdue_km | 27,000 km |
| km_progress_ratio | **10.0×** |
| time_progress_ratio | 0.186× |
| determining_dimension | KM |
| status | **OVERDUE** |
| maintenance_urgency_score | **100** |
| maintenance_urgency_level | **KRİTİK** |
| maintenance_urgency_reason | "27.000 km gecikmiş (kilometre periyodu 10.0× seviyesinde)" |

10.0× is well past the code's documented ≥5.0× saturation threshold
(`ridebase_ml/policy/urgency.py`) — the live score saturating at exactly
**100** is direct proof the deterministic rule fired correctly, not a
coincidence or a hand-set value.

Diagnostic-pace separation: the short-window annualized pace
(30,000 km / 34 days × 365 = **322,059 km/yr**) is reported as its own field
(`recent_annualized_km`) alongside — never merged into — the user's own
`annual_km_baseline` (24,000 km/yr, `annual_baseline_ratio: 13.4`). The two
stay visibly distinct in the response.

## V2.1 prediction (live, separate call, separate system)

`POST /api/v2_1/predict/scenario` with the same natural inputs:

| Horizon | Risk |
|---|---|
| P30 | 0.357798 |
| P60 | 0.702602 |
| P90 | 0.818792 |
| P120 | 0.887640 |

Monotonic ✅, no P30 exact-zero collapse ✅, identical on a repeated call
(byte-for-byte same JSON) ✅ — deterministic. `current_odometer_km_at_landmark`
provenance is `USER_INPUT`, distinct from `last_service_odometer_km` — the
two mileage figures are not confused.

## Semantic separation — the actual point of this phase

| Concept | Value | Source |
|---|---|---|
| Maintenance Due | `true` (`status: OVERDUE`) | deterministic policy math |
| Maintenance Urgency | `100` / `KRİTİK` | deterministic policy math, same source |
| Service Return Risk (V2.1, P30) | `0.358` (36%) | ML survival model, independent call |

The urgency score is pinned at its maximum (100) while V2.1's 30-day return
probability sits at only 36% — the two numbers visibly diverge. **No
artificial synchronization.** This confirms Maintenance Due/Urgency and
Service Return Risk remain architecturally and numerically independent, as
required. Model probabilities were not touched, adjusted, or retrained to
produce this result — every number above is a direct, unedited API response.

Full raw evidence: [`true_extreme_overdue_regression.json`](true_extreme_overdue_regression.json).
