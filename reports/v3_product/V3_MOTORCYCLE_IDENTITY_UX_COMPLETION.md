# V3 Motorcycle Identity UX Completion

Adds motorcycle identity and context to the V3 product surface. **The frozen V3
model and its 44 task probabilities were not changed.**

---

## 1. Problem

The V3 screen led straight into predictions:

```
MC000001
  Motor Yağı Değişimi     91.3%
  Hava Filtresi Değişimi  38.1%
```

Technically correct, product-wise incomplete. A synthetic ID answers *which row*,
not *which motorcycle*. A user could not tell the brand, the model, the year, how
many kilometres are on it, when it was last serviced, or what kilometre context the
prediction sits in — so the percentages had nothing to attach to.

## 2. Source Metadata

Every displayed field comes from real v1.4 source data; nothing is derived from the
ID and nothing is fabricated.

| Field | Source | PIT-safe rule | Displayed |
|---|---|---|---|
| `motorcycle_id` | `motorcycles.motorcycle_id` | identity row gated by `observation_start_date <= landmark` | yes |
| `brand` | `motorcycles.brand` | same | yes |
| `model` | `motorcycles.model_name` | same | yes |
| `model_year` | `motorcycles.production_year` | same | yes |
| `category` | `motorcycles.category` | same | technical only |
| `current_odometer_km` | latest `mileage_timeline_monthly.closing_odometer_km` | `period_end_date <= landmark` | yes |
| `last_service_date` | latest `DELIVERED` `services.received_at` | `received_at.date <= landmark` | yes |
| `last_service_odometer_km` | odometer on that same service row | same row, same boundary | yes |
| `km_since_last_service` | current odometer − last service odometer | both operands PIT-safe; hidden if negative | yes |
| `days_since_last_service` | landmark − last service date | both PIT-safe | yes |
| `annual_usage_km` | active `usage_profiles.annual_km_baseline` | `profile_start_date <= landmark`, active at landmark | yes |

Fields deliberately **not** shown: variant, engine cc, registration date, last
service type — real but not useful in a compact identity card.

## 3. API Change

`POST /api/v3/predict/by-motorcycle` and `GET /api/v3/sample` gained
`motorcycle_context`, `motorcycle_context_provenance`,
`motorcycle_context_warnings`, and (on `/sample`) `friendly_motorcycle_label`.

**Response enrichment only.** `app/v3_context.py` runs *after* the frozen 44
probabilities are produced and never supplies a predictor feature. Missing fields
are **omitted**, never defaulted — there is no `0 km`, no `01.01.1970`, no
`"N/A"`, no `null` padding.

### Probability parity — the critical gate

| check | result |
|---|---|
| `ridebase-ml/` touched by this change | **no files** |
| V3 frozen hashes | **11/11 identical** |
| V2.1 + Urgency frozen hashes | **21/21 identical** |
| API probabilities vs frozen research pipeline | **max delta 0.000e+00** across all 44 labels |
| research↔serving predictor parity re-run | **PASS**, 0 unexplained divergences |

A first pass appeared to show a 4.98e-05 delta. That was **response rounding**, not
a model change: `predict_product` has always emitted `round(v, 4)`, and comparing
against the reference rounded to the same 4 decimals gives exactly **0.0**. Recorded
here rather than quietly dropped, because a 5e-5 discrepancy is precisely the size
that gets hand-waved.

## 4. Frontend Change

A `MOTOSİKLET BİLGİLERİ` card now renders **above** the Top-K list:

```
MOTOSİKLET BİLGİLERİ                    SENTETİK MOTOSİKLET KAYDI
Bu tahmin, aşağıda bilgileri gösterilen sentetik motosikletin bir
sonraki tamamlanmış servis kaydı içindir.

Honda PCX125
2021 Model

MOTOR ID             MC006625
GÜNCEL KİLOMETRE     40.853 km
SON SERVİS TARİHİ    27.03.2026
SON SERVİS KİLOMETRESİ 40.495 km
SON SERVİSTEN BERİ   358 km · 34 gün
YILLIK KULLANIM      9.090 km/yıl
LANDMARK TARİHİ      30.04.2026
Kaynak: SYNTHETIC_HISTORY_V1_4
```

- Turkish locale formatting: `40.853 km`, `9.090 km/yıl`, `27.03.2026`, `34 gün`.
- Rows appear **only** when the field exists; unknown fields are hidden, not zeroed.
- `SENTETİK MOTOSİKLET KAYDI` keeps the user from reading it as their own bike,
  without shouting.
- The sample helper now returns `friendly_motorcycle_label`
  (`Mondial Wing 50i (2019) · MC009796`), degrading to `Brand Model · ID` without a
  year and to the bare ID with no identity at all.
- Existing V3 semantics, Top-K, confidence tiers and all three disclaimers are
  unchanged.

## 5. PIT / Leakage Audit

| check | result |
|---|---|
| current odometer never from a future record | PASS |
| last service is the latest eligible `DELIVERED` service ≤ landmark | PASS |
| last-service odometer belongs to that same row | PASS |
| future injection cannot change odometer or last service | PASS |
| T-1 / T / T+1 context boundaries | PASS |
| same-day services use a deterministic id tie-break | PASS |
| no target/next-service metadata in the card | PASS |
| context failure never blocks or changes a prediction | PASS |
| error paths (404 / 422) leak no context | PASS |

## 6. Regression

| item | result |
|---|---|
| V3 probabilities | **unchanged** (0.0 delta) |
| V3 frozen hashes | 11/11 identical |
| V2.1 frozen hashes | 21/21 identical |
| Maintenance Urgency implementation | unchanged |
| retraining | **NO** |

## 7. Tests

| Suite | Passed | Failed |
|---|---|---|
| `ridebase-ml/tests` | 203 | 0 |
| `ridebase-v1-dashboard/backend/tests` | 143 | 0 |
| `ridebase-control-center/tests` | 115 | 0 |
| **total** | **461** | **0** |

Up from 443 before this change: +13 backend context tests and +5 frontend tests.
Partial-metadata cases (brand+model+year, no year, model only, ID only, no service
history, no odometer, no usage) are covered by parametrized monkeypatched adapters,
because the real v1.4 world always has complete metadata and cannot exercise them.

## 8. Deployment

| surface | state |
|---|---|
| commit | `a14d8f9` — `feat(v3): add PIT-safe motorcycle context UX`, pushed to `origin/main` |
| **frontend** | **LIVE and current** — live page byte-identical to committed `public/index.html`; `v3ContextCard` present and called by `v3Result` |
| **backend** | **NOT deployed** — still serving `a397ca6`; `/api/v3/sample` returns no `motorcycle_context` |

**Manual Render action required** (no Render CLI, no `~/.render`, no `RENDER_*`
env var, and `autoDeploy: false`):

1. Render Dashboard → service `ridebase-inference-api`
2. Environment → confirm `RIDEBASE_ADMIN_TOKEN`, `RIDEBASE_V3_SOURCE_DIR`,
   `RIDEBASE_V3_LABEL_POLICY`, `V3_ENABLED=true`
3. Manual Deploy → **Deploy latest commit `a14d8f982815d78d5b0bb19fa726f152ac30c573`**
4. Verify `GET /api/v3/sample` returns `motorcycle_context` and
   `friendly_motorcycle_label`

### The version skew is safe

The live frontend already ships the card while the live backend does not yet send
the data. Verified in a real browser on the live site: the prediction still runs,
the card is simply absent, and there is **no NaN, no undefined, no null** — the
renderer treats missing context as "omit", exactly as designed. Nothing user-facing
is broken by the skew; the card simply appears once the backend deploy lands.

## 9. Live Examples

Produced by the current build (backend deploy pending). Synthetic serving examples —
**not real-world predictions.**

| Case | Motorcycle | ID | Year | Odometer | Last service | Landmark | Top 1 |
|---|---|---|---|---|---|---|---|
| normal | Honda PCX125 | `MC000002` | 2021 | 52.095 km | 2025-12-06 @ 49.231 km | 2026-03-31 | Motor Yağı Değişimi 86.3% YÜKSEK |
| sparse history | Kuba Blueberry 50 | `MC000039` | 2025 | 9.346 km | 2026-03-20 @ 8.909 km | 2026-03-31 | Motor Yağı Değişimi 93.3% YÜKSEK |
| overdue | Mondial Wing 50i | `MC000008` | 2019 | 134.835 km | 2025-10-03 @ 129.816 km | 2026-01-31 | Motor Yağı Değişimi 69.8% YÜKSEK |
| older bike | Honda Activa 125 | `MC000046` | 2015 | 86.201 km | 2025-08-28 @ 82.363 km | 2026-02-28 | Motor Yağı Değişimi 66.2% YÜKSEK |
| newer bike | Honda Dio 110 | `MC000020` | 2023 | 25.155 km | 2025-07-24 @ 19.456 km | 2025-09-30 | Motor Yağı Değişimi 95.2% YÜKSEK |
| unseen | Honda Activa 125 | `MC000007` | 2021 | 53.705 km | 2025-03-13 @ 50.460 km | 2025-07-31 | Motor Yağı Değişimi 91.3% YÜKSEK |

## 10. Additional QA Findings

| # | Finding | Severity | Note |
|---|---|---|---|
| 1 | Backend not yet deployed, so the card is not live | **P1** | code complete and safe; manual Render deploy required (§8) |
| 2 | A cached browser copy of the Control Center can serve a pre-card build | **P3** | reproduced: the card was absent until a cache-busted reload. Normal HTTP caching, resolves itself; noted because it can look like a failed deploy |
| 3 | Inline SVG favicon blocked by CSP | **P3** | pre-existing, cosmetic, unrelated to V3; already logged as a follow-up |
| 4 | Long model names, mobile layout | **EXPECTED** | at 375×812: no horizontal overflow, 0 clipped elements, card width 343 px; a 47-character model name wraps cleanly |
| 5 | Stale-state on motorcycle switch | **EXPECTED** | A→B replaces brand, model, year, ID, odometer, service rows and Top-K with zero leftovers from A |

## 11. Final Verdict

> **B. V3 MOTORCYCLE CONTEXT UX COMPLETE — MANUAL DEPLOYMENT REQUIRED**

The feature is implemented, tested (461/461), PIT-audited, probability-parity
proven, and the frontend is already live. Verdict A is not claimed because the
backend still runs `a397ca6`: until `a14d8f982815d78d5b0bb19fa726f152ac30c573` is deployed, the live card has no data
to render, and calling it "live" would be false.

---

THIS CHANGE ADDS MOTORCYCLE IDENTITY AND CONTEXT ONLY.
THE FROZEN V3 MODEL AND ITS TASK PROBABILITIES WERE NOT CHANGED.
ALL DISPLAYED MOTORCYCLE METADATA IS SOURCED FROM PIT-SAFE SYNTHETIC HISTORY.
NO REAL-FLEET VALIDATION IS CLAIMED.
