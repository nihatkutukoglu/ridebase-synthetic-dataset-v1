# RideBase V3 Final Deployment & Live Audit

Deployment and live verification only. **No retraining, no artifact change, no
Maintenance Urgency change, and no code change was required.**

---

## 1. Deployment Target

| item | value |
|---|---|
| intended SHA | **`5ac8b9d`** |
| local HEAD | `5ac8b9d45ce6adc5489e5431eefc70f2128e7893` |
| `origin/main` | identical |
| working tree | clean |
| HEAD newer than the intended SHA? | no — HEAD **is** `5ac8b9d` |
| **actual deployed backend SHA** | **`9271065`** — one commit behind |
| Render service | `ridebase-inference-api` (existing; none created) |
| frontend | **live and current** on the existing Vercel project |

`5ac8b9d` was confirmed to be exactly HEAD, so it is the correct target — no stale
SHA was selected, and the previously-live `9271065` was never re-deployed.

## 2. Backend Deployment

**NOT PERFORMED — no authorized tooling exists in this environment.**

| probe | result |
|---|---|
| `render` CLI on PATH | absent |
| `~/.render` config | absent |
| `RENDER_*` / `RENDER_API_KEY` env var | absent |
| deploy-hook URL in the repo | none |
| `render.yaml` `autoDeploy` | **false** (`render.yaml:20`) |

This matches what earlier sessions recorded in
`reports/render_backend_deploy_audit.md`. **No deployment was attempted and none is
claimed.**

### Exact manual steps

1. Open the Render Dashboard
2. Open service **`ridebase-inference-api`**
3. Open **Environment**
4. Confirm **`RIDEBASE_ADMIN_TOKEN`** exists (never printed or echoed here), plus
   `RIDEBASE_V3_SOURCE_DIR=/app/app/v3_data`,
   `RIDEBASE_V3_LABEL_POLICY=/app/config/v3_product_label_policy.json`,
   `V3_ENABLED=true`
5. Save only if a value actually changed
6. Open **Manual Deploy**
7. Choose **Deploy latest commit**
8. Confirm the target SHA is **`5ac8b9d`** — never `9271065`
9. Wait until status is **Live**, then re-run the Phase 3 proof below

## 3. Verification of the Deployed Version

Deployment success was **not** inferred from `/health` returning 200. Two response
fields introduced in `98b80ed` act as discriminators:

| discriminator | live backend | code at `5ac8b9d` |
|---|---|---|
| `threshold_policy` block in the prediction response | **absent** | present |
| `history_provenance.straddling_history_service` | **absent** | present |

Both absent ⇒ the live service is running **`9271065`**, proven from response
content rather than assumed.

## 4. V3 Live API

| Route | HTTP | Latency | Result |
|---|---|---|---|
| `GET /health` | 200 | 458 ms | v3 ok · catboost · 44 labels · 277 features |
| `GET /api/v3/model/info` | 200 | 372 ms | V3_SYNTHETIC_PRODUCT_CANDIDATE / SYNTHETIC_ONLY / PENDING |
| `GET /api/v3/labels` | 200 | 940 ms | 44 labels · 12 / 13 / 4 / 15 |
| `GET /api/v3/metrics` | 200 | 423 ms | P@1 0.8014 · note says NOT an accuracy |
| `GET /api/v3/sample` | 200 | 795 ms | input-only pair, no target leakage |
| `POST /api/v3/predict/by-motorcycle` | 200 | 1165 ms | 200, full product contract |
| `POST /api/v3/predict (empty row)` | 422 | 1247 ms | 422 — never filled in |
| `POST /api/v3/predict/batch (over cap)` | 422 | 474 ms | 422 — bounded at 100 |
| `POST /api/v3/predict/scenario` | 404 | 357 ms | 404 — intentionally not implemented |
| `POST unknown motorcycle` | 404 | 403 ms | 404 |
| `POST pre-observation landmark` | 422 | 404 ms | 422, no fabricated prediction |

Cold start on the first probe took **62.6 s** — Render free-plan spin-up, not a
fault. Subsequent calls ran in 0.4–1.7 s.

## 5. V3 Serving Checks

| check | result |
|---|---|
| status wording | PASS — `V3_SYNTHETIC_PRODUCT_CANDIDATE` |
| validation scope | PASS — `SYNTHETIC_ONLY` |
| real fleet | PASS — `PENDING` |
| label count | PASS — **44** (matches frozen) |
| feature count | PASS — **277** (matches frozen) |
| model family | PASS — **catboost** (matches frozen) |
| P@1 not called accuracy | PASS — note reads "ranking metric … NOT an accuracy" |
| probabilities finite and in [0,1] | PASS |
| Top-K deterministic | PASS — identical on repeat |
| all-label map deterministic | PASS |
| no duplicate task codes | PASS |
| confidence tier present | PASS |
| feature coverage present | PASS — 1.0 |
| warnings / provenance present | PASS |
| no NaN / null misuse | PASS |
| no fake prediction on error | PASS |
| **`threshold_policy` present** | **FAIL — old code deployed** |
| **straddle provenance present** | **FAIL — old code deployed** |

**13 of 15 behavioural checks pass.** The two failures are exactly the deployment
discriminators, not serving regressions: the deployed build predates them.

## 6. Straddle Regression

**Case.** `MC009503` @ `2023-04-30` — the fixture from the Phase-7 parity audit.
`SVC039193` arrives 22:52:36 and completes 01:43:36 the following day.

**Expected handling (code at `5ac8b9d`).** `straddling_history_service` detects the
condition, a Turkish warning is attached, `provenance.straddling_history_service`
is `true`, and history is gated on the parent service's arrival date so the served
features match training.

| | live (`9271065`) | local (`5ac8b9d`) |
|---|---|---|
| straddle flag in provenance | **absent** | **true** |
| straddle warning | **absent** | **present** |
| `threshold_policy` | absent | present |
| 3rd-ranked task | Hava Filtresi Kontrolü **43.0%** | Hava Filtresi Kontrolü **38.5%** |
| control landmark flagged (`MC000001` @ 2026-03-31) | — | **false**, correctly |

The 4.5-point gap on the third task is the skew itself: the live build still serves
the pre-fix answer on straddling landmarks, silently. The fix is verified working
locally on the same fixture, and does **not** over-trigger on a normal landmark.

The boundary does not silently widen: the 7-day fetch lookahead only pulls
candidate rows, and membership in `get_services_before` remains the binding gate —
asserted by `test_task_fetch_lookahead_never_admits_a_future_service`. Predictor
parity at 5,000 landmarks shows **0 unexplained divergences**.

## 7. V2.1 Regression

| endpoint | HTTP | result |
|---|---|---|
| `GET /api/v2_1/model/info` | 200 | unchanged |
| `GET /api/v2_1/metrics` | 200 | unchanged |
| `GET /api/v2_1/sample` | 200 | returns `motorcycle_id` + `landmark_at` |
| `POST /api/v2_1/predict/by-motorcycle` | 200 | P30 0.2072 ≤ P60 0.4279 ≤ P90 0.6238 ≤ P120 0.7469 — **monotone** |
| `POST /api/v2_1/predict/scenario` | 200 | coverage/warnings present |

- **No V3 field leaked into any V2.1 response** (`top_tasks`, `task_code`,
  `all_task_probabilities` all absent).
- V2.1 semantics wording intact: `risk_meaning` still states the horizon risk is
  "NOT maintenance-needed probability".
- `median_service_days` 71.04, consistent with the calibrated curve.

One 422 was recorded mid-audit and traced to **my own payload** — the V2.1 scenario
schema requires `landmark_date` and forbids extras, and I first sent
`snapshot_date`. Re-sent correctly it returns 200. Not a regression.

## 8. Maintenance Urgency Regression

Deterministic, via `POST /api/v2/predict/scenario` (same bike, only the service
history varied):

| case | score | level |
|---|---|---|
| recent service | 8 | NORMAL |
| due | 90 | KRİTİK |
| overdue | 97 | KRİTİK |
| extreme overdue | **100** | KRİTİK |

- bounded 0–100: **yes**
- monotone non-decreasing with overdue-ness: **yes**
- extreme overdue saturates at **100**: **yes**
- V3 and V2.1 probabilities are not forced by urgency: **confirmed** — no V3 route
  reads an urgency value, and no urgency field appears in any V3 or V2.1 payload

Semantic separation holds: Maintenance Due ≠ Maintenance Urgency ≠ Service-Return
Risk ≠ V3 Next-Service Task Probability.

## 9. Security / CORS / Docs

| check | result |
|---|---|
| CORS preflight from the Control Center origin | **PASS** — `allow-origin` echoed, methods `GET, POST, OPTIONS` |
| CORS simple GET from that origin | **PASS** |
| CORS from a foreign origin (`evil.example.com`) | **PASS** — no `allow-origin` header returned |
| `/docs` | 404 |
| `/openapi.json` | 404 |
| `/redoc` | 404 |
| `POST /admin/reload` with **no** token | **401** |
| `POST /admin/reload` with a **bad** token | **401** |

The admin-auth check is **conclusive this time**. An earlier probing round returned
429/502 with `cf-mitigated: challenge` and `server: cloudflare` — that was
Cloudflare's bot challenge triggered by rapid sequential requests, **not** an
application failure. After backing off and pacing requests, both admin probes
returned a clean 401. `RIDEBASE_ADMIN_TOKEN` was never printed, echoed or logged.

## 10. Frontend Verification

**Static/HTTP verification performed AND visual interaction verified** — browser
automation was available and used.

### Interactive verification (real browser)

Navigated to `#v3/predict` on the live site, clicked **RASTGELE GEÇERLİ ID GETİR**
(which called the live `/api/v3/sample` and populated `MC000062` / `2025-11-30`),
then clicked **V3 TAHMİNİNİ ÇALIŞTIR**. The live backend answered and the card
rendered:

```
V3 — SONRAKİ SERVİSTE BEKLENEN İŞLEMLER
landmark 2025-11-30 · MC000062
  1. Motor Yağı Değişimi     95.2%   YÜKSEK
  2. Zincir Temizliği        79.5%   YÜKSEK
  3. Zincir Yağlama          66.8%   YÜKSEK
özellik kapsamı 100.0% · kaynak SYNTHETIC_HISTORY_V1_4 · SYNTHETIC_ONLY · GERÇEK FİLO: PENDING
```

| check | result |
|---|---|
| V3 section reachable and renders | PASS |
| backend status row | PASS — "BACKEND API ONLINE · V3 LOADED · 44 etiket · 277 özellik · CHAMPION CATBOOST" |
| real by-motorcycle prediction through the UI | **PASS** |
| Top-3 with probabilities and confidence tiers | PASS |
| feature coverage and warnings visible | PASS |
| technical details accessible | PASS — **44 rows**, all labels present |
| no NaN / undefined in rendered output | PASS |
| synthetic disclaimer visible | PASS |
| "mekanik arıza olasılığı değildir" visible | PASS |
| urgency/due separation stated | PASS |
| P@1 shown as accuracy | **no** — rendered "P@1 (SIRALAMA)" with "doğruluk oranı değildir" |
| overview metrics match frozen artifacts | PASS — P@1 80.1%, P@3 39.9%, R@3 68.0%, Micro F1 51.9%, mAP 13.3%, unseen P@1 80.4% |
| label policy counts | PASS — 12 / 13 / 4 / 15 |
| V2.1 and Maintenance Urgency remain separate sections | PASS |

### One pre-existing defect found (not V3, not fixed here)

The only console error on the live site is a CSP violation blocking the inline SVG
favicon: `vercel.json` sets `default-src 'self'` without an `img-src` directive, so
the data-URI favicon is refused and the tab icon does not render. It is cosmetic,
predates V3, and is **not deployment-blocking**, so no code was changed for it in
this deployment-only task. Logged as a separate follow-up.

No other JS errors were observed.

## 11. Git Safety

| item | value |
|---|---|
| code changes required for deployment | **none** |
| working tree | clean |
| HEAD | `5ac8b9d45ce6adc5489e5431eefc70f2128e7893` |
| `origin/main` | identical |
| force push | none |
| V2.1 + Urgency frozen hashes | **21/21 identical** |
| V3 frozen hashes | **11/11 identical** |

## 12. Final Verdict

> **V3 DEPLOYMENT PARTIAL — MANUAL RENDER ACTION STILL REQUIRED**

Everything that can be verified without a Render deploy passes: the frontend is
live, current, and verified interactively end to end against the live backend; all
V3 routes respond correctly; V2.1, Maintenance Urgency, CORS, docs gating and admin
auth all pass; frozen hashes are untouched.

The backend remains on **`9271065`**. It is fully functional, but it predates
`98b80ed` and therefore still serves the pre-fix answer on midnight-straddling
landmarks (~0.12% of the population) without emitting the accompanying warning —
demonstrated live on the `MC009503` fixture. Deploying **`5ac8b9d`** by the manual
steps in §2 closes that gap; this environment holds no credentials to do it.

---

V3 USES THE FROZEN SYNTHETIC RESEARCH CHAMPION.
NO V3 OR V2.1 RETRAINING WAS PERFORMED.
MAINTENANCE DUE, MAINTENANCE URGENCY, V2.1, AND V3 REMAIN SEMANTICALLY SEPARATE.
NO REAL-FLEET VALIDATION IS CLAIMED.
