# RideBase db90966 Final Live Verification

Audit date: 2026-09-10 (Europe/Istanbul)

Audit scope only. No training, threshold tuning, generator change, model-artifact
change, Maintenance Urgency change, or real-fleet validation claim was made.

## 1. Deployment Proof

| Item | Evidence | Result |
|---|---|---|
| Repository at audit start | `HEAD = origin/main = db909664620e8067a24683d1d4c0d24a8bd8258d`; clean | PASS |
| Live backend | `https://ridebase-inference-api.onrender.com` | HTTP 200 |
| Live frontend | `https://ridebase-ml-control-center.vercel.app/#v3` | HTTP 200 |
| db90966 behavioral discriminator | first successful cold-start health response: `v3_status=loading`, `v3_model_loaded=false`; next response: `v3_status=ok`, `v3_model_loaded=true` | PASS |
| Port availability | first cold wake completed with HTTP 200; no connection/port timeout | PASS |

The readiness transition is response-behavior proof, not a Render dashboard
label. The non-blocking `loading` state and readiness-only V3 health check were
introduced by `db90966`; the older generation forced V3 loading on the health
request and could not emit this transition.

## 2. Health and Warmup

The first request woke the Render free instance and took 51.942 seconds end to
end. Once the instance answered, the application reported its own health-handler
time as only 0.9 ms while V3 was still loading. Two seconds later V3 was ready.

| Probe | HTTP | Curl total | `x-response-time-ms` | V3 status | V3 loaded |
|---:|---:|---:|---:|---|---:|
| cold-wake first 200 | 200 | 51.942 s | 0.9 ms | `loading` | false |
| +2 seconds | 200 | 0.339 s | 0.9 ms | `ok` | true |
| ready repeat | 200 | 0.317 s | 0.8 ms | `ok` | true |

The first response also reported V1, V2.0, and V2.1 as ready. The transition
shows that `/health` observed V3 readiness without waiting for or triggering the
expensive V3 load on its request path.

## 3. V3 Metadata Routes

| Route | Live result |
|---|---|
| `GET /api/v3/model/info` | CatBoost, 277 features, 44 labels, global threshold policy, threshold 0.31 |
| `GET /api/v3/labels` | 44 labels: 12 PRIMARY, 13 SECONDARY, 4 LOW_CONFIDENCE, 15 HIDDEN_BY_DEFAULT |
| `GET /api/v3/metrics` | synthetic-only TEST metrics; real-fleet validation pending |
| `GET /api/v3/sample` | input-only sample plus friendly identity and PIT-safe context |

Live model status is `V3_SYNTHETIC_PRODUCT_CANDIDATE`, validation scope is
`SYNTHETIC_ONLY`, `deployed_as_production_model=false`, and
`real_fleet_validation=PENDING`. P@1 is 0.8014246004 and its live note explicitly
calls it a ranking metric and **not an accuracy figure**.

## 4. Motorcycle Context — Critical Gate

Live sample:

`Honda PCX125 (2021) · MC003223` at landmark `2025-11-30`.

| Field | Live value | Source/PIT evidence |
|---|---|---|
| `motorcycle_id` | `MC003223` | stable history key |
| brand/model | Honda / PCX125 | V1.4 motorcycle + model reference |
| `model_year` | 2021 | source production year |
| `current_odometer_km` | 36,034 | `MTL0109263`, period end 2025-11-30 ≤ landmark |
| `last_service_date` | 2025-03-22 | delivered `SVC013172` ≤ landmark |
| `last_service_odometer_km` | 30,875 | same eligible service row |
| `km_since_last_service` | 5,159 | PIT odometer minus eligible service odometer |
| `days_since_last_service` | 253 | landmark minus eligible service date |
| `annual_usage_km` | 8,523 | active `UP003223` profile |
| `landmark_date` | 2025-11-30 | explicit request date |
| context source | `SYNTHETIC_HISTORY_V1_4` | synthetic-only |

`future_records_used=false`; every cited record date is on or before the
landmark. Context warnings were empty. No missing value was converted to a fake
zero or fabricated default, and the API omitted absent optional fields rather
than presenting `null`/`undefined` as metadata.

## 5. V3 Integrity and Determinism

The same sample request was executed three times.

| Check | Result |
|---|---|
| Top-3 order | identical |
| all 44 probabilities | identical at response precision |
| binary decisions | identical |
| confidence labels | identical |
| motorcycle context | identical |
| feature coverage | 1.0, present |
| probability bounds | all finite and within [0,1] |
| history/context provenance | present and valid |

Stable Top-3:

1. Motor Yağı Değişimi — 0.9033 — YÜKSEK
2. Akü Testi — 0.4138 — ORTA
3. Hava Filtresi Kontrolü — 0.3423 — ORTA

## 6. Five-Motorcycle Live Test

All rows came from live `/api/v3/sample` followed by live
`/api/v3/predict/by-motorcycle`. Each context ID matched the request, every
source date passed the landmark boundary, and every provenance block reported
`future_records_used=false`.

| ID | Brand/Model | Year | KM | Last Service | Landmark | Top1 |
|---|---|---:|---:|---|---|---|
| `MC000985` | Honda PCX125 | 2019 | 94,420 | 2025-01-16 | 2025-07-31 | Motor Yağı Değişimi 93.75% |
| `MC004934` | Kuba Blueberry 50 | 2018 | 191,776 | 2026-03-29 | 2026-03-31 | Motor Yağı Değişimi 55.43% |
| `MC006653` | Honda CB125F | 2020 | 81,299 | 2025-12-31 | 2026-02-28 | Motor Yağı Değişimi 93.31% |
| `MC008763` | Honda Dio 110 | 2020 | 57,033 | 2025-08-09 | 2026-01-31 | Motor Yağı Değişimi 93.75% |
| `MC002758` | Honda Dio 110 | 2022 | 77,769 | 2025-12-08 | 2026-01-31 | Motor Yağı Değişimi 93.64% |

API-level A→B→C identity and Top-K responses were distinct and internally
consistent. A browser-level stale-DOM assertion could not be run because browser
automation was unavailable; the deployed source contains both the generation
guard (`sampleGen!==v3Gen`) and immediate old-result clearing, covered by the
passing Control Center tests.

## 7. Straddle Regression

| Case | Flag | Warning | Top-3 summary | Result |
|---|---:|---:|---|---|
| `MC009503 @ 2023-04-30` | true | present | oil 0.9523; rear brake inspection 0.5000; air filter inspection 0.3849 | PASS |
| nearby control `MC009503 @ 2023-03-31` | false | absent | no straddle warning | PASS |
| nearby control `MC009503 @ 2023-05-31` | false | absent | no straddle warning | PASS |

The flagged response includes `task_history_boundary = parent service
received_at <= landmark` and the Turkish midnight-straddle warning. The two
adjacent monthly landmarks do not false-positive, so the fixed serving behavior
is active and the condition is not silent.

## 8. V2.1 Regression

All required live routes returned HTTP 200:

- `GET /api/v2_1/model/info`
- `GET /api/v2_1/metrics`
- `GET /api/v2_1/sample`
- `POST /api/v2_1/predict/scenario`
- `POST /api/v2_1/predict/by-motorcycle`

| Surface | P30 | P60 | P90 | P120 | Monotonic |
|---|---:|---:|---:|---:|---:|
| partial scenario | 0.227273 | 0.448630 | 0.656051 | 0.753960 | yes |
| history `MC005762 @ 2026-07-31` | 0.874618 | 0.941304 | 0.959032 | 0.970280 | yes |

V2.1 remains `xgb_cox + isotonic`, 54 features, synthetically validated, and
real-fleet pending. Metrics status and golden prediction parity are both PASS.
Neither response contained V3-only keys such as `top_tasks`, `task_code`,
`all_task_probabilities`, `threshold_policy`, or `motorcycle_context`; no semantic
drift was observed.

## 9. Maintenance Urgency Separation

An NS200-like extreme-overdue natural scenario was executed twice through the
live deterministic maintenance surface. It returned the same result both times.

| Layer | Live value | Meaning |
|---|---|---|
| Maintenance Due | `OVERDUE` | deterministic policy state |
| Maintenance Urgency | `100 / KRİTİK` | deterministic severity, bounded in 0..100 |
| reason | `27.000 km gecikmiş (kilometre periyodu 10.0× seviyesinde)` | deterministic explanation |
| V2.1 P30 | 0.236936 | service-return probability, not forced to 1.0 |
| V3 Top-1 on overdue fixture `MC000008 @ 2026-01-31` | Motor Yağı Değişimi 0.6984 | next-service task probability, not forced to 1.0 |

Required separation holds:

`Maintenance Due ≠ Maintenance Urgency ≠ V2.1 Service Return Probability ≠ V3 Next-Service Task Probability`

## 10. Security and CORS

| Check | Live result |
|---|---|
| Control Center preflight | 200; exact `access-control-allow-origin`; methods `GET, POST, OPTIONS` |
| Control Center simple GET | 200; exact allowed origin echoed |
| foreign-origin preflight | 400 `Disallowed CORS origin`; no allow-origin |
| foreign-origin simple GET | no allow-origin header |
| `/docs` | 404 |
| `/openapi.json` | 404 |
| `/redoc` | 404 |
| `/admin/reload` without token | 401 |
| `/admin/reload` with deliberately invalid token | 401 |

The real admin token was never requested, used, printed, or exposed. No
`cf-mitigated` challenge header appeared during these checks; the observed
responses came from the application/CORS middleware rather than a Cloudflare
challenge page.

## 11. Frontend Verification

Browser automation was unavailable in this environment, so only static and HTTP
verification is claimed.

The live frontend returned HTTP 200 and was byte-identical to committed
`ridebase-control-center/public/index.html`:

- bytes: 433,070 live and local;
- SHA-256: `12247874ee9f0e9fef9c4ec380222df9e123723e41eb23f861d3faccb65ece90`;
- `MOTOSİKLET BİLGİLERİ` and `SENTETİK MOTOSİKLET KAYDI` present;
- friendly sample label and random-helper copy present;
- context-card renderer is called before Top-K;
- technical-context renderer present;
- stale-generation guard and immediate previous-output clearing present;
- mechanical-failure and real-fleet-pending warnings present.

The 115 passing Control Center tests additionally exercise Turkish date/km
formatting, year-only-when-present, missing-field hiding, no rendered NaN or
undefined, fake-zero prevention, Top-3/confidence preservation, context
provenance, and stale-response suppression. An interactive browser A→B→C and
responsive viewport run remains the only non-blocking follow-up.

## 12. Frozen Hash Safety

Hashes were recomputed from disk and compared with the pre-recorded frozen
inventories; no training command was run.

### V3 — 11/11 identical

| Artifact | SHA-256 |
|---|---|
| champion model | `2a1f0103c32a10bfcf56b6f7fd7073fa9d49eac3b718df519378c0ebfbc16eb1` |
| calibrator | `f64c9dab5d2886645f7c80fe2c01d192d58abead376625c20115dc2ff5347bb4` |
| feature list | `9566bf2439a3876c8569e359461c8dc07f7883d486a2af7729b60c00184955ec` |
| label list | `f1bd6d5c70d0776fbf76b1273510d411e54e6a0d015e526e4ec498c62e5d1e56` |
| thresholds | `12415d4f67cf62d9810aaaa0aecb42b5546ff4ce4fac39f15fb3e406e22ff550` |
| artifact manifest | `182d5ac7f4da9fe8fa8331a0aa337ce98b5655ea53b8e9463116a75584c3e193` |
| selection before test | `74735ab53e4d37ac9c1f0bb2955863b20cb51d526bcd4731308ea5f58437d740` |
| calibration report | `8c92418ee0b68aa334951c174dff9bd34517e81e238cddf39cc6cdf94f3f8234` |
| test evaluation | `bb0fdb031e66eba145d0b43c968bf52f5ad3f6be2570fa5db76f42828f9c8f4b` |
| V3 label set | `ab89e0099c0f0a2f21f28e8e0142ce46799a4e628a2032a9e176f8420b46e08c` |
| V3 target contract | `4bb810a9fe93654310d50487a740c968bdf8352ac8f02870a5ee411e624748d6` |

### V2.1 + Maintenance Urgency — 21/21 identical

Representative binding hashes:

| Artifact | SHA-256 |
|---|---|
| V2.1 champion | `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def` |
| calibrator | `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945` |
| preprocessor | `6b24e0ebc027f52bebb52841ec551cadb14b63bf2f540687a69ee0445ec9f990` |
| baseline hazard | `70d87de08a6b44146a115134ddbd1e68b3972c5f5d5e94b9e7d4cebd732d2dc0` |
| feature list | `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a` |
| history SQLite | `a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657` |
| Maintenance Urgency implementation | `7e11476156d0a55544f326867f6089b0432debe33110b6bd472f173cdb7cfbcf` |

All other files in the 21-item V2.1/urgency inventory also matched exactly.

## 13. Test Totals

| Suite | Passed | Failed |
|---|---:|---:|
| `ridebase-ml/tests` | 203 | 0 |
| backend tests | 143 | 0 |
| Control Center tests | 115 | 0 |
| **current core total** | **461** | **0** |
| legacy frontend smoke | 5 | 0 |
| legacy frontend TypeScript | PASS | 0 |
| legacy frontend production build | PASS | 0 |

The ML suite emitted one non-failing XGBoost serialized-model compatibility
warning already covered by its offline/shadow test; no test failed.

## 14. Final Verdict

**V3 LIVE WITH NON-BLOCKING UX FOLLOW-UPS — CORE SERVING AND MOTORCYCLE CONTEXT PASS**

The only follow-up is an interactive browser pass for A→B→C DOM replacement and
responsive presentation. Core serving, live context, PIT provenance,
determinism, straddle handling, V2.1 separation, urgency separation, security,
frozen hashes, and the deployed static frontend all pass.

THE db90966 DEPLOYMENT IS LIVE AND VERIFIED ONLY IF THE ABOVE LIVE CHECKS PASS.
THE FROZEN V3 MODEL AND ITS TASK PROBABILITIES WERE NOT RETRAINED.
V2.1 REMAINS THE SERVICE-RETURN TIMING MODEL.
MAINTENANCE DUE AND MAINTENANCE URGENCY REMAIN DETERMINISTIC.
NO REAL-FLEET VALIDATION IS CLAIMED.
