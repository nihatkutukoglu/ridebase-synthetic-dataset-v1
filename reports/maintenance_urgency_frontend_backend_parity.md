# Maintenance Urgency Frontend ↔ Backend Parity

- Timestamp (UTC): `2026-09-04T15:46:31.978415+00:00`
- Status: **PASS**
- Coverage: **23/23 (100.00%)**
- Numerical tolerance: `1e-09`
- Canonical source: `ridebase_ml.policy.urgency.calculate_maintenance_urgency`
- Frontend fallback: actual `v2CalculateUrgency` extracted from `template.html` and executed with Node.js

The matrix covers every requested progress ratio, KM/TIME/BOTH dominance, missing optional fields,
boundary rounding, saturation, and extreme overdue behavior. Backend fields remain canonical; this
audit only proves the behavior of the absence/error fallback.

| Case | Python score | JS score | Level | Dimension | Result |
|---|---:|---:|---|---|---|
| progress_ratio_0 | 0 (0.0) | 0 (0.0) | NORMAL | KM | PASS |
| progress_ratio_0.1 | 5 (4.8) | 5 (4.8) | NORMAL | KM | PASS |
| progress_ratio_0.25 | 12 (11.9) | 12 (11.9) | NORMAL | KM | PASS |
| progress_ratio_0.5 | 24 (23.8) | 24 (23.8) | NORMAL | KM | PASS |
| progress_ratio_0.526 | 25 (25.0) | 25 (25.0) | YAKLAŞIYOR | KM | PASS |
| progress_ratio_0.75 | 36 (35.6) | 36 (35.6) | YAKLAŞIYOR | KM | PASS |
| progress_ratio_0.8 | 38 (38.0) | 38 (38.0) | YAKLAŞIYOR | KM | PASS |
| progress_ratio_0.9 | 44 (44.0) | 44 (44.0) | YAKLAŞIYOR | KM | PASS |
| progress_ratio_0.99 | 49 (49.4) | 49 (49.4) | YAKLAŞIYOR | KM | PASS |
| progress_ratio_1 | 50 (50.0) | 50 (50.0) | GECİKMİŞ | KM | PASS |
| progress_ratio_1.1 | 55 (55.0) | 55 (55.0) | GECİKMİŞ | KM | PASS |
| progress_ratio_1.25 | 62 (62.5) | 62 (62.5) | GECİKMİŞ | KM | PASS |
| progress_ratio_1.5 | 75 (75.0) | 75 (75.0) | ÇOK GECİKMİŞ | KM | PASS |
| progress_ratio_1.75 | 82 (82.5) | 82 (82.5) | ÇOK GECİKMİŞ | KM | PASS |
| progress_ratio_2 | 90 (90.0) | 90 (90.0) | KRİTİK | KM | PASS |
| progress_ratio_3 | 93 (93.3) | 93 (93.3) | KRİTİK | KM | PASS |
| progress_ratio_5 | 100 (100.0) | 100 (100.0) | KRİTİK | KM | PASS |
| progress_ratio_10 | 100 (100.0) | 100 (100.0) | KRİTİK | KM | PASS |
| km_dominant | 62 (62.5) | 62 (62.5) | GECİKMİŞ | KM | PASS |
| time_dominant | 62 (62.5) | 62 (62.5) | GECİKMİŞ | TIME | PASS |
| both_within_tolerance | 62 (62.5) | 62 (62.5) | GECİKMİŞ | BOTH | PASS |
| missing_optional_fields | 25 (25.0) | 25 (25.0) | YAKLAŞIYOR | KM | PASS |
| extreme_overdue | 100 (100.0) | 100 (100.0) | KRİTİK | KM | PASS |
