# RideBase V3 Full Productization Completion Report

Resumed from an already-partially-productized repository, verified what was done,
and closed the remaining gaps. **No retraining of any kind.**

---

## 1. Starting State

| item | value |
|---|---|
| start HEAD | `927106512ed5f8e5bb4f7cba3a5da87380136d14` |
| branch | `main`, in sync with `origin/main` |
| working tree | **clean** — no unfinished or unrelated work to preserve |

**Already complete on arrival** (verified, not rebuilt): frozen V3 inventory and
hashes, V2.1/Urgency safety re-verification, product label policy, confidence and
top-K policy, packaged predictor product layer, serving feature builder, backend
API, Control Center module, scenario feasibility decision, deployment packaging,
and both deployments.

**Genuinely incomplete, and what this session did**: full research↔serving
*predictor* parity at scale (the prior session proved only feature parity on 12
rows), the history-serving audit report, the rule-vs-ML semantics doc, the
performance/security report, the extreme-overdue and same-day-duplicate audit
cases, the named Phase-3/15 validation tests, a top-level `threshold_policy` field,
the live V2.1 regression and live history examples, and this report.

Full DONE/PARTIAL/NOT-STARTED checklist: [`00_resume_preflight.md`](00_resume_preflight.md).

## 2. Frozen V3 Champion

| item | value |
|---|---|
| model family | **catboost**, binary relevance (one classifier per label) |
| label count | **44** |
| feature count | **277**, all point-in-time safe |
| threshold policy | `global` @ **0.31**, tuned on VALIDATION |
| calibration | per label: 28 none, 14 isotonic, 2 sigmoid |
| source world | synthetic v1.4, V2.1 landmark grid reused read-only |
| seed | 20260907 |

### Artifact hashes (unchanged before and after)

| artifact | SHA256 |
|---|---|
| `champion_model.joblib` | `2a1f0103c32a10bfcf56b6f7fd7073fa…` |
| `calibrator.joblib` | `f64c9dab5d2886645f7c80fe2c01d192…` |
| `feature_list.json` | `9566bf2439a3876c8569e359461c8dc0…` |
| `label_list.json` | `f1bd6d5c70d0776fbf76b1273510d411…` |
| `thresholds.json` | `12415d4f67cf62d9810aaaa0aecb42b5…` |
| `artifact_manifest.json` | `182d5ac7f4da9fe8fa8331a0aa337ce9…` |
| `selection_before_test.json` | `74735ab53e4d37ac9c1f0bb2955863b2…` |
| `calibration_report.json` | `8c92418ee0b68aa334951c174dff9bd3…` |
| `test_evaluation.json` | `bb0fdb031e66eba145d0b43c968bf52f…` |
| `v3_label_set.json` | `ab89e0099c0f0a2f21f28e8e0142ce46…` |
| `v3_target_contract.json` | `4bb810a9fe93654310d50487a740c968…` |

## 3. Product Label Policy

| status | labels | treatment |
|---|---|---|
| PRIMARY | **12** | may lead the card; may reach YÜKSEK |
| SECONDARY | **13** | shown, capped below YÜKSEK |
| LOW_CONFIDENCE | **4** | shown, de-emphasised, never YÜKSEK |
| HIDDEN_BY_DEFAULT | **15** | never leads; class-E random-event tasks |
| **total** | **44** | |

**Weak-label handling.** The 15 hidden labels are the Phase-9 random fault /
inspection-finding tasks with no learnable signal. They are excluded from the
product list, are **always DÜŞÜK regardless of probability**, and remain fully
present in `all_task_probabilities` and `binary_predictions` — presentation policy
never deletes a model output.

High-prevalence labels are **not** penalised for limited lift headroom:
`ENGINE_OIL_CHANGE` (TEST PR-AUC 0.854, lift only 1.09× at 78% prevalence) is
PRIMARY via the absolute-separation branch. Turkish names come from
`maintenance_tasks.canonical_name_tr`; none was invented.

## 4. Serving Parity

| item | value |
|---|---|
| feature parity | **277/277** |
| rows tested | **5,000** |
| prediction cells compared | **220,000** |
| feature cells compared | **1,385,000** |
| **max probability delta (unflagged landmarks)** | **0.0** |
| Top-K mismatches (unflagged) | **0** |
| threshold mismatches (unflagged) | **0** |
| unexplained divergent landmarks | **0** |

On **4,995 of 5,000** landmarks the packaged predictor reproduces the research
pipeline **bit-for-bit**. The 5 that diverge are exactly the landmarks the
serving layer independently flags.

### The skew this phase found and fixed

Predictor parity at scale exposed a real train/serve divergence that 12-row and
500-row checks had passed cleanly. The V2.1 history adapter filters task lines by
each task's own completion timestamp; the V3 training builder keys history on the
parent service's **arrival** date. They disagree when a service straddles midnight
— 8.6% of v1.4 task lines finish on a later calendar day, across 5,085 of 52,700
services, affecting **48 of 39,451 landmarks (0.12%)**, where a single task's
probability could move up to 0.30.

*Fixed* for every block V3 owns: candidate rows are fetched with a bounded 7-day
lookahead and V3 applies the real PIT gate itself. The lookahead widens the fetch,
never the boundary — a test asserts that.

*Not fixed, deliberately*: three columns come from the frozen
`ridebase_ml/v2_1/history_features.py`, which also serves
`/api/v2_1/predict/by-motorcycle`. Mutating V2.1 to suit V3 is forbidden and would
be the wrong trade. The condition is instead detected, warned, and recorded in
provenance. Detail: [`07_predictor_parity.md`](07_predictor_parity.md).

## 5. V3 Predictor

| capability | status |
|---|---|
| artifacts loaded once at startup | yes — same object identity across 30 requests |
| exact feature order / 277-column contract validated | yes |
| one-row and batch prediction | yes (batch capped at 100) |
| all raw task probabilities exposed | yes — all 44, always |
| frozen threshold results exposed | yes, plus a top-level `threshold_policy` block |
| product-ranked Top-K | yes, default 3, bounded 10 |
| confidence / evidence tier | yes, deterministic |
| warnings, provenance, feature coverage | yes |
| deterministic repeat | yes — byte-identical |
| bounded finite probabilities | yes |

No V2.1 value and no urgency score enters a V3 probability at any point.

## 6. History Serving

| item | value |
|---|---|
| adapter | the **existing** V2.1 read-only SQLite store — no new data store |
| PIT boundary | parent service `received_at <= landmark` |
| deterministic repeat | 40/40 |
| future injection (no post-landmark event) | 40/40 |
| T-1 / T / T+1 monotonicity | 40/40 |
| same-day shuffle invariance | 40/40 |
| latency (sparse → rich history) | 27.22 → 32.88 ms p50 |
| feature coverage | **1.0** on every real landmark |

A second gap this audit surfaced: **15 landmarks** have service history but none of
the 44 modelled tasks, and previously produced *no* warning at all because the
builder only warned on a completely empty event list. Now warned explicitly.
Detail: [`08_history_serving_audit.md`](08_history_serving_audit.md).

## 7. Scenario Decision

**NOT IMPLEMENTED** (option D). `POST /api/v3/predict/scenario` returns 404 and a
test keeps it that way.

**223 of 277 features (80.5%)** depend on per-task service history natural input
cannot supply. Substituting what a scenario form would be forced to send changes
the top-3 answer on **97.3%** of real landmarks, with individual probabilities
moving up to **0.81**. Option C (partial, with coverage warnings) was also rejected:
at 19.5% coverage every response would correctly be `SINIRLI VERİ`, and a card whose
every answer is a disclaimer still renders percentages that read as answers.
Detail: [`09_scenario_feasibility.md`](09_scenario_feasibility.md).

## 8. Backend API

| Route | Implemented | Test | Live |
|---|---|---|---|
| `GET /api/v3/model/info` | yes | yes | **yes** (200) |
| `GET /api/v3/labels` | yes | yes | **yes** (200, 44 labels) |
| `GET /api/v3/metrics` | yes | yes | **yes** (200) |
| `GET /api/v3/sample` | yes | yes | **yes** (200) |
| `POST /api/v3/predict` | yes | yes | yes (422 on empty row, as designed) |
| `POST /api/v3/predict/batch` | yes | yes | yes (422 over cap) |
| `POST /api/v3/predict/by-motorcycle` | yes | yes | **yes** (200) |
| `POST /api/v3/predict/scenario` | **no, by decision** | yes (asserted absent) | 404 |

## 9. Control Center

| element | status |
|---|---|
| navigation / tab | live module, no longer a `soon` placeholder |
| status badge | backend `/health` probe with an explicit "V3 not deployed" state |
| by-motorcycle form + landmark date | yes |
| safe random-sample helper | yes, via `GET /api/v3/sample` (inputs only) |
| Top-3 (5 selectable) with probability bars | yes |
| confidence tier | yes, YÜKSEK / ORTA / DÜŞÜK / SINIRLI VERİ |
| feature coverage + warnings | yes |
| collapsed technical details, all 44 probabilities + binary | yes |
| frozen synthetic metrics as a secondary section | yes |
| synthetic-only disclaimer | yes |

P@1 is rendered as "P@1 (sıralama)" with "doğruluk oranı **değildir**". A test walks
every `P@1` occurrence in template and built HTML and requires a negation nearby.

## 10. Frozen Synthetic Metrics

Frozen artifact values only.

| metric | TEST | unseen-motorcycle TEST |
|---|---|---|
| Micro F1 | 0.5192 | 0.4931 |
| Micro PR-AUC | 0.5611 | 0.5442 |
| mAP | 0.1330 | 0.1282 |
| P@1 | 0.8014 | 0.8035 |
| P@3 | 0.3994 | 0.3855 |
| R@3 | 0.6799 | 0.6967 |
| Macro F1 | 0.1107 | 0.0958 |

**P@1 IS NOT ACCURACY.** It is the share of landmarks where the *highest-ranked*
task really was performed at the next completed service — a ranking metric. Macro F1
is low by design: one global threshold under-serves low-frequency labels, which the
product contract says to read as probabilities and ranks, not binary flags.

## 11. Product Audit

**15 scenarios, all PASS**, 0 failing checks.

| scenario | rows | result |
|---|---|---|
| `recent_service` | 2,000 | PASS |
| `near_maintenance` | 1,088 | PASS |
| `overdue` | 2,000 | PASS |
| `high_usage` | 791 | PASS |
| `low_usage` | 1,619 | PASS |
| `rich_task_history` | 2,000 | PASS |
| `sparse_task_history` | 1,318 | PASS |
| `no_task_history` | 10 | PASS |
| `unseen_motorcycle` | 1,725 | PASS |
| `older_motorcycle` | 145 | PASS |
| `newer_motorcycle` | 2,000 | PASS |
| `chain_drive` | 2,000 | PASS |
| `scooter` | 2,000 | PASS |
| `extreme_overdue` | 426 | PASS |
| `same_day_duplicate_records` | 9 | PASS |

Every scenario is a filter over **real** landmarks, never a hand-built row. Checks:
finite, bounded, byte-identical repeat, stable ranking, no duplicate codes, exact
top-K size, hidden labels never shown, dense ordered ranks, valid tiers, YÜKSEK only
on PRIMARY, both disclaimers, no urgency/V2.1 field, all 44 labels returned.

**Weak-label probe:** 4,000 landmarks, **0** cases of a hidden label
out-ranking the shown leader. The guard is implemented and tested regardless.

No real-world reasonableness is asserted — this is synthetic product behaviour only.

## 12. Security / Performance

| item | value |
|---|---|
| artifacts loaded once | yes; no per-request reload |
| cold start (full stack) | 2.13 s |
| warm `by-motorcycle` p50 / p95 | **58.9 / 65.8 ms** |
| RSS after startup → after 30 requests | 392.9 → 420.0 MB |
| **RSS growth over 30 requests** | **0.3 MB — no leak** |
| peak vs Render free limit | 420.0 MB of 512 MB |
| batch cap | 100 rows, schema **and** handler |
| request-controlled artifact path / traversal | none — `_MODEL_DIR` is a module constant |
| pickle or upload endpoint | none |
| stack traces to client | none |
| admin auth / docs gating / CORS | unaffected |

## 13. Regression Safety

| item | result |
|---|---|
| V2.1 frozen hashes before/after | **21/21 identical** |
| V3 frozen hashes before/after | **11/11 identical** |
| Maintenance Urgency logic | **unchanged** (`policy/urgency.py` hash identical) |
| V3 retraining | **NO** |
| V2.1 retraining | **NO** |
| real-fleet validation claimed | **NO** |

## 14. Tests

| Suite | Passed | Failed | Result |
|---|---|---|---|
| `ridebase-ml/tests` | 203 | 0 | PASS |
| `ridebase-v1-dashboard/backend/tests` | 130 | 0 | PASS |
| `ridebase-control-center/tests` | 110 | 0 | PASS |
| **total** | **443** | **0** | **PASS** |

Added this session: Phase-3 policy validation (no duplicate codes, no unknown
label, every frozen label accounted, valid statuses, metrics in range), Phase-15
weak-label behaviour, and three straddle-boundary regressions.

## 15. Git

| item | value |
|---|---|
| commits (this productization arc) | 8 |
| final HEAD | `98b80edef1f6697fa446c24d5d874f420d4e1d69` |
| `origin/main` | identical |
| clean tree | yes |
| force push | none |
| secrets / caches / node_modules committed | none |

1. `e1f6e39 Package the frozen V3 product predictor: label policy and confidence tiers`
2. `1d8f112 Add V3 history API and response contract`
3. `6e012f0 Integrate V3 into the Control Center`
4. `cdc6496 Add V3 product audits and top-K behaviour gates`
5. `1f7a128 Ship V3 in the deploy bundle and document the synthetic product candidate`
6. `736ad8c Document V3 synthetic product candidate: productization completion report`
7. `9271065 Record V3 live verification: backend deployed, all routes audited`
8. `98b80ed Fix a real serving/training skew found by predictor parity at scale`

## 16. Deployment

### Frontend — LIVE and current

| item | value |
|---|---|
| URL | https://ridebase-ml-control-center.vercel.app |
| project | `ridebase-ml-control-center` (existing; no duplicate created) |
| deployed content | **byte-identical** to the committed `public/index.html` |
| deployed SHA | `1f7a128` (last commit touching the frontend) |
| status | Ready · Production |

The frontend was **not** changed in this session, so no redeploy was needed and the
live page remains current.

### Backend — LIVE, but one commit behind

| item | value |
|---|---|
| URL | https://ridebase-inference-api.onrender.com |
| status | live and serving all 7 V3 routes |
| deployed SHA | **`9271065`** |
| current `main` | **`98b80edef1f6697fa446c24d5d874f420d4e1d69`** |

**The live backend predates this session's serving/training-skew fix.** Proven from
the live response, not assumed: it returns no `threshold_policy` block and no
`history_provenance.straddling_history_service` flag, both added in `98b80ed`.

**Manual action required** — Render has `autoDeploy: false` and this environment has
no Render CLI or deploy token:

1. Render Dashboard
2. service `ridebase-inference-api`
3. Environment → confirm `RIDEBASE_ADMIN_TOKEN` is set, plus
   `RIDEBASE_V3_SOURCE_DIR=/app/app/v3_data`,
   `RIDEBASE_V3_LABEL_POLICY=/app/config/v3_product_label_policy.json`,
   `V3_ENABLED=true`
4. Manual Deploy → **Deploy latest commit `98b80edef1f6697fa446c24d5d874f420d4e1d69`**
5. Verify `GET /health` shows `v3_status: ok`, and that
   `POST /api/v3/predict/by-motorcycle` now returns a `threshold_policy` block

Until then the live V3 endpoint keeps the midnight-straddle skew on ~0.12% of
landmarks, and does not emit the accompanying warning. Everything else is current.

## 17. Live Audit

| Check | Result | Evidence |
|---|---|---|
| `GET /health` | PASS | 200; `v1/v2/v2_1/v3` all `ok`; v3 catboost, 44 labels, 277 features |
| `GET /api/v3/model/info` | PASS | `V3_SYNTHETIC_PRODUCT_CANDIDATE`, `SYNTHETIC_ONLY`, fleet `PENDING`, `deployed_as_production_model: false` |
| `GET /api/v3/labels` | PASS | 44 labels; 12/13/4/15 status split |
| `GET /api/v3/metrics` | PASS | P@1 0.8014; note contains "NOT an accuracy" |
| `GET /api/v3/sample` | PASS | input-only pair, no target or task leakage |
| `POST /api/v3/predict` | PASS | 422 on an empty feature row — never filled in |
| `POST /api/v3/predict/by-motorcycle` | PASS | 200; coverage 1.0; 44 probabilities; 4 warnings |
| `POST /api/v3/predict/scenario` | PASS | 404 — deliberately absent |
| deterministic repeat (live) | PASS | identical probability map on a second call |
| bounds / no NaN (live) | PASS | all 44 finite and within [0,1] |
| unknown motorcycle | PASS | 404 |
| pre-observation landmark | PASS | 422, no prediction body |
| CORS from the Control Center origin | PASS | preflight + simple GET both allowed |
| `/docs`, `/openapi.json` gating | PASS | 404 in production |
| `POST /admin/reload` without a token | **NOT RE-TESTED** | earlier probes were rate-limited by Cloudflare; not retried to avoid tripping the bot challenge again. Unchanged by V3 and covered by backend tests |
| V2.1 regression (`model/info`, `metrics`, `sample`, `by-motorcycle`) | PASS | all 200; P30 0.237 ≤ P60 0.467 ≤ P90 0.682 ≤ P120 0.790; **no V3 field present** |
| frontend V3 module | PASS | 19/19 static checks on the live page |
| frontend **visual** verification | **NOT PERFORMED** | static/HTTP inspection only — no browser automation was run |

## 18. Final Product Semantics

| Layer | Question | Type |
|---|---|---|
| **Maintenance Due** | Bakım gerekiyor mu? | deterministic |
| **Maintenance Urgency** | Bakım ne kadar gecikmiş? | deterministic 0–100 |
| **V2.1** | 30/60/90/120 gün içinde servise dönüş olasılığı? | ML survival |
| **V3** | Bir sonraki tamamlanmış serviste hangi işlemler? | ML multi-label |

**No mathematical fusion.** V2.1 and V3 are never multiplied, averaged or
reconciled; V3 carries no time horizon; urgency never adjusts a V3 probability; a
V3 probability is never a mechanical-failure probability. A deterministic rule may
be shown beside V3 as context only —
[`docs/v3_rule_vs_ml_semantics.md`](../../docs/v3_rule_vs_ml_semantics.md).

## 19. Final Verdict

> **V3 SYNTHETIC PRODUCTIZATION COMPLETE — FRONTEND/CODE READY, BACKEND MANUAL
> RENDER DEPLOY REQUIRED**

Every acceptance gate passes: frozen V3 and V2.1 hashes, Urgency unchanged, 277/277
feature parity, predictor parity with zero unexplained divergence across 5,000
landmarks, PIT leakage audit, top-K behaviour over 15 scenarios, weak-label policy,
API contracts, frontend semantics, security and resource audit, 443/443 tests, and
no real-fleet claim anywhere.

The frontend is live and current. The backend is live and fully functional, but
runs `9271065` — one commit behind `98b80edef1f6697fa446c24d5d874f420d4e1d69` — so it does not yet carry this
session's serving/training-skew fix. Verdict B is chosen over A on that basis:
claiming "live" would imply the deployed code is the audited code, and it is not.

---

V3 USES THE FROZEN SYNTHETIC RESEARCH CHAMPION.
V3 PREDICTS TASKS AT THE NEXT COMPLETED SERVICE.
V2.1 CONTINUES TO PREDICT SERVICE-RETURN TIMING.
MAINTENANCE DUE AND MAINTENANCE URGENCY REMAIN DETERMINISTIC.
NO V3 OR V2.1 RETRAINING WAS PERFORMED.
NO REAL-FLEET VALIDATION IS CLAIMED.

---

## Appendix — Live V3 history examples (Phase 28)

Captured from the live service. Inputs only; no target labels were consulted.

**typical** — `MC000002` @ `2026-03-31` · coverage 1.0 · 4 prior services / 12 task lines

| rank | task | probability | confidence | status |
|---|---|---|---|---|
| 1 | Motor Yağı Değişimi | 86.3% | YÜKSEK | PRIMARY |
| 2 | Hava Filtresi Kontrolü | 38.5% | ORTA | PRIMARY |
| 3 | Akü Testi | 36.9% | ORTA | PRIMARY |

**sparse_history** — `MC000039` @ `2026-03-31` · coverage 1.0 · 1 prior services / 3 task lines

| rank | task | probability | confidence | status |
|---|---|---|---|---|
| 1 | Motor Yağı Değişimi | 93.3% | YÜKSEK | PRIMARY |
| 2 | Akü Testi | 39.0% | ORTA | PRIMARY |
| 3 | Hava Filtresi Kontrolü | 36.7% | ORTA | PRIMARY |

**overdue** — `MC000008` @ `2026-01-31` · coverage 1.0 · 31 prior services / 162 task lines

| rank | task | probability | confidence | status |
|---|---|---|---|---|
| 1 | Motor Yağı Değişimi | 69.8% | YÜKSEK | PRIMARY |
| 2 | Ön Lastik Değişimi | 19.0% | DÜŞÜK | SECONDARY |
| 3 | Hava Filtresi Değişimi | 4.3% | DÜŞÜK | PRIMARY |

**unseen_motorcycle** — `MC000007` @ `2025-07-31` · coverage 1.0 · 6 prior services / 27 task lines

| rank | task | probability | confidence | status |
|---|---|---|---|---|
| 1 | Motor Yağı Değişimi | 91.3% | YÜKSEK | PRIMARY |
| 2 | Hava Filtresi Kontrolü | 36.4% | ORTA | PRIMARY |
| 3 | Akü Testi | 34.1% | ORTA | PRIMARY |

Every example returned feature coverage **1.0** and the three mandatory disclaimers.
The `overdue` bike shows the pattern the audit found across the population: past its
interval, the leading probability drops (69.8% vs 86–93% elsewhere) and the second
and third tasks fall to DÜŞÜK — the model is genuinely less certain, and the tier
says so.
