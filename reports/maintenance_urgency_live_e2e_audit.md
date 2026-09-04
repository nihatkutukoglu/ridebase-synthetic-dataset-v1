# Maintenance Urgency Live E2E Audit

- Timestamp (UTC): `2026-09-04T15:54:34.322242+00:00`
- Status: **PASS — 6/6 scenarios**
- Backend: `https://ridebase-inference-api.onrender.com`
- Frontend: `https://ridebase-ml-control-center.vercel.app`

| Scenario | State | R | Urgency | Dimension | V2.1 P30/P60/P90/P120 | Frontend source | Result |
|---|---|---:|---|---|---|---|---|
| A_NORMAL | NOT_DUE | 0.3 | 14 NORMAL | KM | 2.9%/6.6%/11.6%/19.2% | BACKEND_CANONICAL | PASS |
| B_NEAR_DUE | DUE_SOON | 0.9 | 44 YAKLAŞIYOR | KM | 12.9%/26.0%/44.4%/63.0% | BACKEND_CANONICAL | PASS |
| C_JUST_DUE | OVERDUE | 1 | 50 GECİKMİŞ | KM | 14.8%/30.3%/48.7%/63.0% | BACKEND_CANONICAL | PASS |
| D_OVERDUE | OVERDUE | 1.5 | 75 ÇOK GECİKMİŞ | KM | 22.7%/44.9%/65.6%/75.4% | BACKEND_CANONICAL | PASS |
| E_CRITICAL | OVERDUE | 5 | 100 KRİTİK | KM | 23.7%/46.6%/65.6%/75.4% | BACKEND_CANONICAL | PASS |
| F_NS200_EXTREME | OVERDUE | 10 | 100 KRİTİK | KM | 23.7%/46.6%/65.6%/75.4% | BACKEND_CANONICAL | PASS |

All frontend comparisons execute the deployed Control Center's actual `v2CalculateUrgency` source.
Every scenario used backend fields as `BACKEND_CANONICAL`; no JS score overwrote a backend score.
V2.1 probabilities are recorded independently and were never forced to match maintenance urgency.
