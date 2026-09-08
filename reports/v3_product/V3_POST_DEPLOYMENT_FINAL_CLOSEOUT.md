# RideBase V3 Post-Deployment Final Closeout

Audit and verification only. **No retraining, no artifact change, no threshold
tuning, no generator change, and no code change was required.**

---

## 1. Deployment Evidence

| item | value |
|---|---|
| Render service | `ridebase-inference-api` (existing; none created) |
| deployment status | **Live** |
| deployed source SHA | **`a397ca6`** |
| live URL | https://ridebase-inference-api.onrender.com |
| frontend URL | https://ridebase-ml-control-center.vercel.app |

**Evidence that the latest code is serving** — not inferred from `/health`
returning 200. Two response fields introduced in `98b80ed` (an ancestor of
`a397ca6`) act as discriminators, and both are now present:

| discriminator | previous build (`9271065`) | now |
|---|---|---|
| `threshold_policy` in the prediction response | absent | **present** — `{'policy': 'global', 'threshold': 0.31, 'per_label': False, 'tuned_on': 'VALIDATION'}` |
| `history_provenance.straddling_history_service` | absent | **present** |
| `history_provenance` keys | 6 | **7**, including `task_history_boundary` |
| `/health` `v3_enabled` field | absent | **present** (`True`) |

Only report files differ between `98b80ed` and `a397ca6`, so the deployed serving
code is exactly the audited code.

## 2. Git State

| item | value |
|---|---|
| start HEAD | `a397ca6557ae1529067e0a874bca9cd202beec31` |
| final HEAD | `a397ca6557ae1529067e0a874bca9cd202beec31` (this report commit) |
| `origin/main` | in sync |
| clean tree | yes |
| force push | none |
| `a397ca6` ancestor of HEAD | yes |

## 3. V3 Model Metadata

| item | live value |
|---|---|
| model family | **catboost** (binary relevance) |
| label count | **44** |
| feature count | **277** |
| model_version | `v3.0-research` |
| status | `V3_SYNTHETIC_PRODUCT_CANDIDATE` |
| validation_scope | `SYNTHETIC_ONLY` |
| real_fleet_validation | `PENDING` |
| deployed_as_production_model | `false` |
| threshold policy | `global` @ `0.31` |
| source world / seed | `v1_4` / `20260907` |

Forbidden wording scan (`REAL VALIDATED`, `PRODUCTION ACCURACY`, `real-fleet pass`,
`better than V2.1`, `%80 doğruluk`): **none found**.

## 4. V3 Live Routes

| Route | HTTP | Result |
|---|---|---|
| `GET /health` | 200 | v1/v2/v2_1/v3 all `ok`; catboost, 44 labels, 277 features |
| `GET /api/v3/model/info` | 200 | correct status/scope/pending wording |
| `GET /api/v3/labels` | 200 | 44 labels, 12 / 13 / 4 / 15 |
| `GET /api/v3/metrics` | 200 | matches frozen artifact to 1e-12 |
| `GET /api/v3/sample` | 200 | input-only (`motorcycle_id`, `landmark_date`, `split`) |
| `POST /api/v3/predict` | 200 | full 277-feature row accepted |
| `POST /api/v3/predict/batch` | 200 | 3-row batch; count matches, order preserved |
| `POST /api/v3/predict/by-motorcycle` | 200 | all 8 history cases |
| `POST /api/v3/predict/scenario` | 404 | **intentionally not implemented** |

Error paths: unknown motorcycle **404**; pre-observation landmark **422**;
malformed date **422**; missing field **422**; empty feature row **422**;
oversized batch (105) **422**; mismatched id length **422**; `top_k=99` **422**.
**No fabricated prediction was returned on any failure path.**

## 5. Deployment Discriminators

| check | result |
|---|---|
| `threshold_policy` present | **PASS** |
| latest provenance schema present | **PASS** — includes `task_history_boundary` and `straddling_history_service` |
| straddle support present | **PASS** — see §6 |

## 6. Straddle Regression

| item | value |
|---|---|
| case | `MC009503` @ `2023-04-30` |
| condition | `SVC039193` arrives 22:52:36, completes 01:43:36 next day |
| live `straddling_history_service` | **`true`** |
| live warning | **present** — "Bu landmark, gece yarısını aşan bir servisin içine denk geliyor…" |
| live `task_history_boundary` | `parent service received_at <= landmark` |
| live feature coverage | 1.0 |
| live Top-3 | Motor Yağı Değişimi 95.2% YÜKSEK · Arka Fren Balatası Kontrolü 50.0% DÜŞÜK · Hava Filtresi Kontrolü 38.5% ORTA |
| **control** `MC000001` @ `2026-03-31` | flag **`false`**, no warning — no false positive |

The third-ranked task now reads **38.5%**. On the previous build the same
fixture returned **43.0%** with no flag and no warning. That 4.5-point shift is the
serving/training skew fix, now live, and the condition self-flags rather than
failing silently. The PIT boundary is not widened: the 7-day fetch lookahead only
pulls candidate rows while membership in `get_services_before` remains the binding
gate.

## 7. Top-K Product Behavior

| check | result |
|---|---|
| default K | 3 |
| `top_k=1 / 3 / 5` | returns exactly 1 / 3 / 5 |
| `top_k=99` | 422 — bounded by schema |
| duplicates | none in any case |
| deterministic order | identical across 3 repeated calls |
| probabilities in [0,1], finite | PASS |
| `HIDDEN_BY_DEFAULT` in any Top-5 | **none** |
| `LOW_CONFIDENCE` shown | yes (`REAR_BRAKE_PAD_INSPECTION`) — always at `DUSUK`, never `YUKSEK` |
| all 44 labels in technical output | PASS |
| hidden labels still returned raw | PASS — presentation policy deletes nothing |

A live illustration of the weak-label rule: on the straddle fixture
`Arka Fren Balatası Kontrolü` scores **50.0%** yet is displayed **DÜŞÜK**, because
it is a `LOW_CONFIDENCE` label. Probability and confidence stay separate.

## 8. Frozen Synthetic Metrics

Live `/api/v3/metrics` matched the local frozen artifact to 1e-12 on every field.

| metric | TEST | unseen-motorcycle TEST |
|---|---|---|
| Micro F1 | 0.5192 | 0.4931 |
| Micro PR-AUC | 0.5611 | 0.5442 |
| mAP | 0.1330 | 0.1282 |
| P@1 | 0.8014 | 0.8035 |
| P@3 | 0.3994 | 0.3855 |
| R@3 | 0.6799 | 0.6967 |

**P@1 IS A RANKING METRIC, NOT OVERALL ACCURACY.** It is the share of landmarks
where the highest-ranked task really was performed at the next completed service.
The live payload carries that statement in `metric_notes.precision_at_1`, and the
UI renders it as "P@1 (SIRALAMA) … doğruluk oranı değildir".

## 9. V2.1 Regression

| route | HTTP |
|---|---|
| `GET /api/v2_1/model/info` | 200 |
| `GET /api/v2_1/features` | 200 |
| `GET /api/v2_1/metrics` | 200 |
| `GET /api/v2_1/sample` | 200 |
| `POST /api/v2_1/predict` | 200 |
| `POST /api/v2_1/predict/batch` | 200 (count 2) |
| `POST /api/v2_1/predict/scenario` | 200 |
| `POST /api/v2_1/predict/by-motorcycle` | 200 |

- **Monotonicity holds:** P30 0.0291 ≤ P60 0.1155 ≤ P90 0.2183 ≤ P120 0.3436, all in [0,1].
- **No V3 leakage:** no `top_tasks`, `task_code`, `all_task_probabilities` or
  `threshold_policy` appears in any V2.1 response.
- Champion `xgb_cox`, dataset `1.4.0-v2.1-dynamic-landmark`, `real_fleet: PENDING`
  — unchanged.
- Artifact status: 21/21 frozen V2.1 hashes identical locally.

Two 422s recorded mid-audit were **my own payload errors**, not regressions: the
V2.1 scenario schema requires `landmark_date` (not `snapshot_date`) and forbids
extras, and the batch route takes `items` (not `rows`). Both return 200 when sent
correctly.

## 10. Maintenance Policy Regression

| case | urgency | level | due |
|---|---|---|---|
| recently serviced | 8 | NORMAL | NOT_DUE |
| approaching | 58 | GECİKMİŞ | OVERDUE |
| due | 90 | KRİTİK | OVERDUE |
| overdue | 97 | KRİTİK | OVERDUE |
| very overdue | 100 | KRİTİK | OVERDUE |
| extreme overdue | **100** | KRİTİK | OVERDUE |

Bounded 0–100: **yes**. Monotone with overdue-ness: **yes**. Extreme overdue
saturates at **100**: **yes**. Deterministic: **yes**.

### Semantic separation, demonstrated live

| layer | value |
|---|---|
| Maintenance Urgency (extreme overdue) | **100 / 100** |
| V2.1 P30 (overdue bike) | **0.3022** |
| V3 top task probability | **0.6619** (`Motor Yağı Değişimi`) |

Three different numbers answering three different questions on comparable inputs.
Urgency at 100 does **not** force V2.1 or V3 toward 1.0. **No fusion.**

## 11. Security

| check | result |
|---|---|
| CORS preflight from the Control Center origin | **200**, `allow-origin` echoed, methods `GET, POST, OPTIONS` |
| CORS simple GET from that origin | **200**, `allow-origin` echoed |
| CORS from a foreign origin (`evil.example.com`) | **no `allow-origin` header** — correctly refused |
| `/docs` | **404** |
| `/openapi.json` | **404** |
| `/redoc` | **404** |
| `POST /admin/reload` no token | **401** |
| `POST /admin/reload` bad token | **401** |
| `POST /admin/reload` valid token | **NOT TESTED** — the real token was never used, printed or echoed |

**Cloudflare behaviour.** In an earlier session, rapid sequential probing triggered
Cloudflare's bot challenge (`cf-mitigated: challenge`, `server: cloudflare`)
returning 429/502 that could easily be misread as application faults. This audit
paced every request and saw no challenge; the admin checks are therefore
**conclusive** this time.

## 12. Frontend Static Verification

| check | result |
|---|---|
| live page **byte-identical** to committed `public/index.html` | **PASS** (427,947 bytes) |
| V3 section/tab, title and copy | PASS |
| synthetic disclaimer | PASS |
| real-fleet pending wording | PASS |
| not-a-failure disclaimer | PASS |
| urgency/due separation stated | PASS |
| P@1 labelled ranking, negated as accuracy | PASS |
| no `%80 doğruluk` anywhere | PASS |
| technical details structure | PASS |
| no stale "V3 ON HOLD" copy | PASS |
| V2.1 and Maintenance Urgency remain separate | PASS |

## 13. Frontend Interactive Verification

**Browser automation available: YES.** Real interaction was performed.

| step | result |
|---|---|
| open live Control Center, navigate to V3 | PASS |
| click random/sample helper | PASS — called live `/api/v3/sample`, populated `MC000062` / `2025-11-30` |
| status row from live `/health` | "BACKEND API ONLINE · V3 LOADED · 44 etiket · 277 özellik · CHAMPION CATBOOST · REAL FLEET PENDING" |
| run real V3 prediction | PASS |
| Top-3 rendered | Motor Yağı Değişimi 95.2% YÜKSEK · Zincir Temizliği 79.5% YÜKSEK · Zincir Yağlama 66.8% YÜKSEK |
| percentages / confidence tiers | PASS |
| feature coverage | 100.0% |
| validation scope / real-fleet label | `SYNTHETIC_ONLY` · `GERÇEK FİLO: PENDING` |
| technical details opened | PASS — **44 rows**, threshold 0.31 shown |
| NaN / undefined in rendered output | **none** |
| disclaimers | all three present |
| V2.1 page still functions | PASS — horizons and history form intact, no V3 copy leaked |
| Maintenance Urgency function present | PASS |

**Console errors:** exactly one, the known CSP favicon violation (§18). No JS
errors related to V3.

## 14. Live Synthetic Examples

Synthetic serving examples. **These are not real-world predictions.**

| Motorcycle | Landmark | Top 1 | Top 2 | Top 3 | Coverage | Warnings |
|---|---|---|---|---|---|---|
| `MC000002` | 2026-03-31 | Motor Yağı Değişimi 86.3% | Hava Filtresi Kontrolü 38.5% | Akü Testi 36.9% | 1.0 | 4 |
| `MC000039` | 2026-03-31 | Motor Yağı Değişimi 93.3% | Akü Testi 39.0% | Hava Filtresi Kontrolü 36.7% | 1.0 | 4 |
| `MC000008` | 2025-07-31 | Motor Yağı Değişimi 95.2% | Akü Testi 59.2% | Hava Filtresi Değişimi 45.8% | 1.0 | 4 |
| `MC009503` (straddle) | 2023-04-30 | Motor Yağı Değişimi 95.2% | Arka Fren Balatası Kontrolü 50.0% | Hava Filtresi Kontrolü 38.5% | 1.0 | 5 |

Full 8-case sweep, all PASS:

| case | input | history used | coverage | result |
|---|---|---|---|---|
| `normal_history` | `MC000002` @ 2026-03-31 | 4 svc / 12 tasks | 1.0 | PASS |
| `sparse_history` | `MC000039` @ 2026-03-31 | 1 svc / 3 tasks | 1.0 | PASS |
| `recently_serviced` | `MC000008` @ 2025-07-31 | 29 svc / 155 tasks | 1.0 | PASS |
| `overdue` | `MC000008` @ 2026-01-31 | 31 svc / 162 tasks | 1.0 | PASS |
| `extreme_overdue` | `MC000008` @ 2026-05-31 | 32 svc / 163 tasks | 1.0 | PASS |
| `older_motorcycle` | `MC000046` @ 2026-02-28 | 5 svc / 18 tasks | 1.0 | PASS |
| `newer_motorcycle` | `MC000020` @ 2025-09-30 | 1 svc / 5 tasks | 1.0 | PASS |
| `unseen_motorcycle` | `MC000007` @ 2025-07-31 | 6 svc / 27 tasks | 1.0 | PASS |

## 15. Performance Smoke

| item | value |
|---|---|
| warm `by-motorcycle` (n=6) | p50 **1203 ms**, min 995, max 1810 |
| model reload per request | **none** — `v3_load_ms` stable within a process lifetime |
| batch path | bounded at 100 rows; oversized rejected 422 before allocation |
| cold start | 60–80 s on first request after free-tier spin-down |

**Free-tier respawns observed.** `v3_load_ms` changed across probes
(1208.7 → 1290.7 → 1199.2 ms), showing the process restarted between request
bursts. During one respawn window a burst of V2.1 routes returned **503**; on
re-probe `/health` was fully green (`v2_1_status: ok`, `v2_1_model_loaded: true`)
and every route returned 200. This is Render free-tier spin-down/respawn, **not an
application regression**, and is recorded as such rather than as a failure.

## 16. Frozen Artifact Safety

| item | result |
|---|---|
| V3 frozen hashes | **11/11 identical** |
| V2.1 frozen hashes | **21/21 identical** |
| Maintenance Urgency implementation | **unchanged** (`policy/urgency.py` hash identical) |
| retraining performed | **NO** |

## 17. Tests

| Suite | Passed | Failed | Result |
|---|---|---|---|
| `ridebase-ml/tests` | 203 | 0 | PASS |
| `ridebase-v1-dashboard/backend/tests` | 130 | 0 | PASS |
| `ridebase-control-center/tests` | 110 | 0 | PASS |
| **total** | **443** | **0** | **PASS** |

## 18. Outstanding Non-Blocking Issues

1. **Favicon CSP violation (cosmetic).** `ridebase-control-center/vercel.json` sets
   `default-src 'self'` without an `img-src` directive, so the inline SVG data-URI
   favicon is blocked and the tab icon does not render. Predates V3, affects no
   functionality, and was deliberately **not** fixed during an audit-only task.
   Logged as a separate follow-up.
2. **Free-tier spin-down latency.** First request after idle takes 60–80 s, and a
   respawn can briefly return 503. Inherent to the Render free plan. `V3_ENABLED=false`
   remains the documented escape hatch if memory ever becomes the cause.
3. **Admin valid-token branch not tested.** Verifying it would require using the
   real `RIDEBASE_ADMIN_TOKEN`, which was deliberately never used or exposed. The
   reject paths (no token, bad token) are both confirmed 401.
4. **Straddle landmarks retain a V2.1-owned residual.** On ~0.12% of landmarks,
   three V2.1-owned feature columns still follow the V2.1 task-timestamp boundary.
   V3 cannot change them without mutating a frozen contract, so it detects, warns
   and records the condition instead. Working as designed.

## 19. Final Product Semantics

| Layer | Question | Type |
|---|---|---|
| **Maintenance Due** | Bakım gerekiyor mu? | deterministic |
| **Maintenance Urgency** | Bakım ne kadar gecikmiş/acil? | deterministic 0–100 |
| **V2.1** | 30/60/90/120 gün içinde servise dönüş olasılığı? | ML survival |
| **V3** | Bir sonraki TAMAMLANMIŞ serviste hangi işlemler? | ML multi-label |

**No fusion.** Demonstrated live in §10: urgency 100 alongside V2.1 P30 = 0.3022
and a V3 top task of 0.6619 — three independent answers, never multiplied or
reconciled.

## 20. FINAL VERDICT

> **V3 SYNTHETIC PRODUCT CANDIDATE LIVE —
> SYNTHETICALLY VALIDATED, REAL FLEET VALIDATION PENDING**

The deployed backend is proven to be the audited code (`a397ca6`) by response
content, not by a health check. Every V3 route, error path, top-K rule, weak-label
rule and disclaimer behaves as audited; the straddle fix is live and self-flagging
with a correct control; V2.1, Maintenance Due and Maintenance Urgency are intact
and semantically separate; security gating holds; the frontend is byte-identical to
the committed build and was verified interactively end to end; frozen hashes are
untouched and 443/443 tests pass.

The outstanding items in §18 are cosmetic, infrastructural, or by-design, and none
affects V3 serving correctness.

---

V3 USES THE FROZEN SYNTHETIC RESEARCH CHAMPION.
V3 PREDICTS TASKS AT THE NEXT COMPLETED SERVICE.
V2.1 CONTINUES TO PREDICT SERVICE-RETURN TIMING.
MAINTENANCE DUE AND MAINTENANCE URGENCY REMAIN DETERMINISTIC.
NO V3 OR V2.1 RETRAINING WAS PERFORMED.
NO REAL-FLEET VALIDATION IS CLAIMED.
