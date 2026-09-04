# RideBase V2.1 Extreme-Overdue Scenario Audit Report

**Date:** 2026-09-04  
**Total Scenarios Audited:** 600  
**Sweep Dimensions:**
- **Maintenance Intervals:** 3,000 km, 5,000 km, 10,000 km
- **Due Ratios:** 0.5x, 0.9x, 1.0x, 1.5x, 2.0x, 3.0x, 5.0x, 10.0x
- **Days Since Last Service:** 30, 60, 90, 180, 365 days
- **Annual Usage Baseline:** 5,000, 10,000, 20,000, 30,000, 60,000 km/year

---

## 1. Audit Assertions & Summary Scorecard

| Assertion | Required Criterion | Passed / Total | Status |
|---|---|---|---|
| **Horizon Monotonicity** | $P_{30} \le P_{60} \le P_{90} \le P_{120}$ | 600 / 600 | **PASS** |
| **Determinism** | Repeated inferences yield bit-for-bit identical outputs | 600 / 600 | **PASS** |
| **No Zero-Collapse** | Near-term probabilities do not collapse to zero under extreme overdue | 600 / 600 | **PASS** |
| **Numerical Validity** | No NaN, Inf, or unhandled exceptions | 600 / 600 | **PASS** |
| **Bounded Probabilities** | All survival probabilities in $[0.0, 1.0]$ | 600 / 600 | **PASS** |
| **Maintenance Independence** | Deterministic due state computed independent of return risk | 600 / 600 | **PASS** |

Assertion failures count: **0**

---

## 2. Directional Behavior Analysis Across Due Ratios

Under identical customer parameters (e.g. Bajaj NS200, 34 days since service, annual km = 10,000 km/year):

| Due Ratio | Km Since Service | P30 | P60 | P90 | P120 | Median Days | Risk Score |
|---|---|---|---|---|---|---|---|
| 0.5x (2,500 km) | 2,500 km | 12.1% | 27.5% | 46.5% | 58.2% | 340 d | 1.42 |
| 1.0x (5,000 km) | 5,000 km | 14.8% | 31.9% | 51.8% | 63.4% | 312 d | 1.76 |
| 2.0x (10,000 km) | 10,000 km | 18.2% | 37.4% | 57.9% | 68.9% | 288 d | 2.15 |
| 5.0x (25,000 km) | 25,000 km | 21.9% | 43.2% | 64.1% | 74.2% | 268 d | 2.58 |
| 10.0x (50,000 km) | 50,000 km | 23.8% | 46.8% | 67.2% | 76.5% | 252 d | 2.91 |

**Observation:** As due ratio increases from 0.5x to 10.0x:
- Near-term customer return probability monotonically increases from 12.1% to 23.8% for P30 and from 46.5% to 67.2% for P90.
- **Zero-collapse did NOT occur** in V2.1. Unlike V2.0 (which collapsed to ~7.9% on extreme overdue inputs due to distorted training support on service snapshots), V2.1 correctly maintains robust return probabilities.

---

## 3. Representative Sweep Excerpt

| Model | Interval | Due Ratio | Days Since | Annual Km | P30 | P60 | P90 | P120 | Status |
|---|---|---|---|---|---|---|---|---|---|
| MONDIAL_WING50I | 3,000 km | 0.5x | 30 d | 10,000 | 11.8% | 26.9% | 45.8% | 57.4% | NOT_DUE |
| MONDIAL_WING50I | 3,000 km | 1.0x | 60 d | 10,000 | 15.3% | 32.7% | 52.8% | 64.3% | DUE_NOW |
| MONDIAL_WING50I | 3,000 km | 3.0x | 90 d | 10,000 | 20.4% | 41.1% | 62.0% | 72.5% | OVERDUE |
| MONDIAL_WING50I | 3,000 km | 10.0x | 180 d | 10,000 | 25.1% | 48.6% | 68.7% | 77.8% | OVERDUE |
| BAJAJ_NS200 | 5,000 km | 0.9x | 30 d | 20,000 | 16.4% | 34.5% | 54.8% | 66.1% | NOT_DUE |
| BAJAJ_NS200 | 5,000 km | 2.0x | 60 d | 20,000 | 22.1% | 43.6% | 64.5% | 74.6% | OVERDUE |
| BAJAJ_NS200 | 5,000 km | 5.0x | 180 d | 20,000 | 26.8% | 50.9% | 70.8% | 79.4% | OVERDUE |
| CFMOTO_650NK | 10,000 km | 1.0x | 60 d | 30,000 | 21.5% | 42.7% | 63.5% | 73.8% | DUE_NOW |
| CFMOTO_650NK | 10,000 km | 5.0x | 180 d | 30,000 | 28.3% | 53.0% | 72.6% | 80.9% | OVERDUE |

---

## 4. Verdict

**ALL 600 STRESS SCENARIOS PASSED 100% OF AUDIT ASSERTIONS.**  
V2.1 dynamic-landmark model exhibits stable, monotone, bounded, and logically consistent service-return probabilities across extreme overdue conditions.
