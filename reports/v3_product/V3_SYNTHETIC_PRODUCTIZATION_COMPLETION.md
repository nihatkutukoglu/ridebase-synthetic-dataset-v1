# RideBase V3 Synthetic Productization Completion

Productization of the already-frozen V3 research champion. **No retraining.**
Session date 2026-09-07.

---

## 1. Starting State

| item | value |
|---|---|
| start HEAD | `43d2ba3d0ca564eae1e7cf96fc377039e16b267d` |
| branch | `main`, in sync with `origin/main`, clean tree |
| V3 champion | **catboost**, binary relevance, 44 labels, 277 PIT-safe features |
| frozen threshold | global @ 0.31 |
| calibration | {'none': 28, 'isotonic': 14, 'sigmoid': 2} |
| V3 frozen hashes | 11 artifacts, recorded in [`01_v3_frozen_hashes.json`](01_v3_frozen_hashes.json) |
| V2.1 / Urgency hashes | 21 artifacts, re-verified identical |

Every figure the brief supplied about the V3 research state was checked against the
actual artifacts before being used. **All of them verified** — champion family,
label count, feature count, world, TEST Micro F1 0.5192, Micro PR-AUC 0.5611, mAP
0.1330, P@1 0.8014, unseen P@1 0.8035, ~15 weak labels, threshold 0.31. No
correction was needed ([`00_preflight.md`](00_preflight.md)).

## 2. Product Label Policy

Derived from frozen artifacts only. **Presentation policy — no label is removed
from the model**; all 44 remain in every response under `all_task_probabilities`.

| status | labels | treatment |
|---|---|---|
| PRIMARY | 12 | can lead the card, can reach YÜKSEK |
| SECONDARY | 13 | shown, capped below YÜKSEK |
| LOW_CONFIDENCE | 4 | shown, de-emphasised |
| HIDDEN_BY_DEFAULT | 15 | never leads; Phase-9 class E random-event tasks |
| **total** | **44** | |

**A bug worth recording.** The first draft judged reliability by lift over
prevalence alone and put `ENGINE_OIL_CHANGE` — TEST PR-AUC 0.854 on 4,626
positives, the most reliable label in the set — into `LOW_CONFIDENCE`, because at
78% prevalence there is no headroom for a large multiple. Caught while building the
policy, before commit. The rule now also accepts absolute separation, and
`test_high_prevalence_reliable_label_is_primary` pins it. The failure mode
generalises: any reliability rule expressed purely as a ratio buries whatever is
already common.

Leading PRIMARY labels: `ENGINE_OIL_CHANGE` (0.85), `CHAIN_CLEAN` (0.60), `CHAIN_LUBRICATE` (0.49), `CHAIN_INSPECTION` (0.30), `BATTERY_TEST` (0.30), `AIR_FILTER_INSPECTION` (0.29).

### Confidence tiers

`YÜKSEK` / `ORTA` / `DÜŞÜK` / `SINIRLI VERİ`, deterministic, ordered so a large
number cannot buy confidence:

1. feature coverage < 80% → `SINIRLI VERİ`
2. `HIDDEN_BY_DEFAULT` label → `DÜŞÜK` **regardless of probability**
3. `LOW_CONFIDENCE` label → capped at `ORTA`
4. only `PRIMARY` labels can reach `YÜKSEK`

Rule 2 is the point: a 99% score on `WHEEL_BALANCE` is `DÜŞÜK`, and the response
says why in `confidence_reason`.

## 3. Predictor

| item | value |
|---|---|
| model family | catboost, binary relevance (44 per-label models + shared preprocessor) |
| artifacts | `ridebase-ml/models/v3_research/` (read-only) |
| features | 277 | 
| labels | 44 |
| **parity** | **PASS — serving features reproduce the research matrix byte-for-byte** |

Parity is the load-bearing gate. `test_serving_features_match_the_research_matrix_exactly`
rebuilds the full 277-column vector from the history adapter for random landmarks
and compares against the research dataset: **0 mismatching columns**. If the two
builders disagreed, every frozen metric would stop describing what the API returns.

`predict_product()` returns raw model probabilities and the product-ranked list
side by side and never mixes them. No V2.1 output and no maintenance rule touches
either.

## 4. History Integration

| item | value |
|---|---|
| source | the **existing** V2.1 read-only SQLite history adapter — no second source of truth |
| boundary | task history gated on parent service `received_at <= landmark` |
| declined tasks | excluded — a declined recommendation reset no interval |
| feature coverage | **1.0** on real landmarks |
| future injection | no post-landmark event is reachable |
| T-1 / T / T+1 | counts monotone in landmark date |
| same-day shuffle | invariant — regression from the research-phase determinism bug |

The research session found a real non-determinism defect (two task lines on one day
could swap and change `hist_count`). The serving path re-asserts the fix with a
deliberately shuffling adapter wrapper.

## 5. Scenario Decision

**NOT IMPLEMENTED.** `POST /api/v3/predict/scenario` returns 404, and a test keeps
it that way.

Measured, not asserted: **223 of 277 features (80.5%)** depend on per-task service
history that natural input cannot supply. Replacing those blocks with what a
scenario form would be forced to send changes the top-3 answer on **97.3%** of real
TEST landmarks and moves individual probabilities by up to **0.81**.

Option B (partial scenario with coverage warnings) was rejected too: at 19.5%
coverage every response would correctly be `SINIRLI VERİ`, so the honest version of
the feature is a card that always says it cannot answer. The percentages would
still render, and a percentage on screen reads as an answer regardless of the label
beside it. Detail: [`09_scenario_feasibility.md`](09_scenario_feasibility.md).

## 6. API

| Route | Result | Tests |
|---|---|---|
| `GET /api/v3/model/info` | 200 | identity, counts, `does_not_predict`, scenario-not-implemented |
| `GET /api/v3/labels` | 200 | 44 labels, display names, policy, per-label frozen metrics |
| `GET /api/v3/metrics` | 200 | artifact-driven; P@1 never called accuracy |
| `GET /api/v3/sample` | 200 | input only — no task list, no target |
| `POST /api/v3/predict` | 200 / 422 | rejects incomplete rows rather than filling them |
| `POST /api/v3/predict/batch` | 200 / 422 | bounded at 100 rows |
| `POST /api/v3/predict/by-motorcycle` | 200 / 404 / 422 / 503 | primary product flow |
| `POST /api/v3/predict/scenario` | **404 (not implemented)** | asserted absent |

24 API tests. Unknown bike → clean 404; pre-observation or malformed landmark →
clean 422; disabled or missing artifacts → 503. **No failure path returns a
fabricated prediction.**

## 7. Control Center

V3 replaced a `soon:true` placeholder and became a real module. No other module was
redesigned; V1 / V2.0 / V2.1 / Maintenance Urgency copy is unchanged, asserted by test.

- **Canlı Tahmin** — ID + landmark date + random-valid-ID helper → top 3 (5
  selectable) with name, probability bar, percentage, confidence chip; feature
  coverage; warnings; collapsed technical section with all 44 probabilities and the
  binary decision at the frozen threshold.
- **Genel Bakış** — frozen synthetic TEST metrics, fetched not hard-coded.
- **Disclaimers** — synthetic-validation, not-a-failure-probability, and
  urgency/due-are-separate, all present and tested.
- **P@1** is rendered as "P@1 (sıralama)" with "doğruluk oranı **değildir**".
- The V3 section is asserted to contain **no time horizon** (`30 gün`, `90 gün`,
  `P30`, `P90`) — V3 has none.
- The tab probes `/health` first and, if the backend has no V3, says so plainly and
  refuses to run rather than failing with a generic network error.

16 frontend gates, driven by a Node runner that renders the real card from a fixed
payload and checks what a viewer would actually see.

## 8. Product Audit

Phase-17 sweep over 13 scenarios against the frozen model, each a **filter over
real landmarks** rather than a hand-built row. **RESULT: PASS**, 0 failures.

| scenario | rows | result | mean top-1 |
|---|---|---|---|
| `recent_service` | 2,000 | PASS | 0.858 |
| `near_maintenance` | 1,088 | PASS | 0.865 |
| `overdue` | 2,000 | PASS | 0.731 |
| `high_usage` | 791 | PASS | 0.836 |
| `low_usage` | 1,619 | PASS | 0.821 |
| `rich_task_history` | 2,000 | PASS | 0.791 |
| `sparse_task_history` | 1,318 | PASS | 0.859 |
| `no_task_history` | 10 | PASS | 0.756 |
| `unseen_motorcycle` | 1,725 | PASS | 0.826 |
| `older_motorcycle` | 145 | PASS | 0.806 |
| `newer_motorcycle` | 2,000 | PASS | 0.876 |
| `chain_drive` | 2,000 | PASS | 0.825 |
| `scooter` | 2,000 | PASS | 0.825 |

Checks per scenario: finite and in-range probabilities, byte-identical repeat,
stable ranking, no duplicate task codes, correct top-K counts, hidden labels never
shown, dense ordered ranks, valid tiers, YÜKSEK only on PRIMARY, both disclaimers
present, no urgency or V2.1 field, all 44 labels returned.

**Weak-label probe:** 4,000 landmarks, **0** cases where a hidden label
out-ranks the shown leader. The frozen model does not put high probability on
random-event labels, consistent with Phase 9 finding no learnable signal there. The
warning path is implemented and tested anyway.

Two honest notes: `no_task_history` matched only 10 landmarks, so its numbers carry
their row count and are not an estimate; and `overdue` has the lowest mean top-1
(0.731 vs 0.858 recently-serviced) because a bike far past its interval has usually
also drifted from its service pattern — the uncertainty is real.

## 9. Frozen Synthetic Metrics

Frozen artifact values only. **P@1 is a ranking metric and is never called accuracy.**

| metric | TEST | unseen-motorcycle TEST |
|---|---|---|
| P@1 *(ranking)* | 0.8014 | 0.8035 |
| P@3 | 0.3994 | 0.3855 |
| R@3 | 0.6799 | 0.6967 |
| Micro F1 | 0.5192 | 0.4931 |
| Macro F1 | 0.1107 | 0.0958 |
| Micro PR-AUC | 0.5611 | 0.5442 |
| mAP | 0.1330 | 0.1282 |
| Hamming loss | 0.0575 | 0.0588 |

P@1 is the share of landmarks where the **highest-ranked** task really was performed
at the next completed service. It is not a percentage of correct predictions.

Macro F1 is low by design: a single global threshold under-serves the low-frequency
labels, which the product contract says must be read as probabilities and ranks, not
binary flags.

## 10. Safety

| question | answer |
|---|---|
| V3 retrained? | **NO** — 11/11 frozen V3 hashes identical |
| V2.1 modified? | **NO** — 21/21 hashes identical |
| Maintenance Urgency modified? | **NO** — `policy/urgency.py` hash identical |
| real-fleet validation claimed? | **NO** — every payload carries `PENDING` |
| hardcoded probabilities? | **NO** — metrics read from artifacts, no expected value asserted anywhere |
| pending reconciliation work overwritten? | **NO** — this session only adds commits on top of `b25f3b7` |

## 11. Tests

| Suite | Passed | Failed |
|---|---|---|
| `ridebase-ml/tests` | 192 | 0 |
| `ridebase-v1-dashboard/backend/tests` | 130 | 0 |
| `ridebase-control-center/tests` | 110 | 0 |
| **total** | **432** | **0** |

New this session: 23 product-policy gates, 10 serving/PIT gates, 24 API gates,
16 Control Center gates. Two pre-existing Control Center tests asserted exact
strings this change intentionally rewrites (the default-subroute line and the
manifest's V3 "planned" status); both were updated to assert the new truthful state.

## 12. Deployment

### Frontend — **LIVE**

| item | value |
|---|---|
| project | `ridebase-ml-control-center` (existing Vercel project, not duplicated) |
| production URL | https://ridebase-ml-control-center.vercel.app |
| deployment | `ridebase-ml-control-center-hdfagj615-…` · Ready · Production |
| commit | `1f7a128` |
| verification | 16/16 static checks pass on the live HTML |

### Backend — **MANUAL DEPLOY REQUIRED**

The live API at `https://ridebase-inference-api.onrender.com` serves V1, V2.0 and
V2.1 correctly but returns **404 on `/api/v3/*`** — it is running a pre-V3 commit.
`render.yaml` sets `autoDeploy: false`, there is no Render CLI and no deploy token
in this environment, so **the backend is not live and is not claimed to be.**

Three real blockers were found and fixed in code so that a deploy will work:

1. `collect_prod_artifacts.sh` excluded `models/v3_research/` from the bundle.
2. `Dockerfile.prod` never copied the V3 artifacts or the sample index.
3. `ridebase_ml.v3.sources` located its reference tables by walking up for a
   directory containing both `ridebase_v1_4/` and `.git/` — **neither exists in the
   container**, so V3 would have failed to load in production while passing every
   local test. Two env overrides (`RIDEBASE_V3_SOURCE_DIR`,
   `RIDEBASE_V3_LABEL_POLICY`) now make the package work with no repository
   checkout, verified by running it from a temp directory.

**Exact manual step:**

1. Open the Render dashboard → service `ridebase-inference-api`.
2. **Manual Deploy → Deploy latest commit** (`1f7a128` on `main`).
3. Confirm the env vars from `render.yaml` are present:
   `RIDEBASE_V3_SOURCE_DIR=/app/app/v3_data`,
   `RIDEBASE_V3_LABEL_POLICY=/app/config/v3_product_label_policy.json`,
   `V3_ENABLED=true`. `RIDEBASE_ADMIN_TOKEN` must remain set — it is unchanged and
   must not be bypassed.
4. Verify `GET /health` reports `v3_status: ok`, `v3_label_count: 44`,
   `v3_feature_count: 277`.

**Memory warning for that deploy.** V3 adds ~113 MB. The full stack peaks near
**452 MB against the free plan's 512 MB** — roughly 12% headroom, and this service
has been OOM-killed before. Loading was made lazy during this session (V3 alone went
from 473 MB to 113 MB by not reading the two large source tables the serving path
never touches), but if the deploy still runs out of memory, set **`V3_ENABLED=false`**
and redeploy: `/api/v3/*` degrades to 503 and V1/V2.0/V2.1 keep serving, with no
code change. Upgrading the Render plan is the durable fix.

Until that deploy happens the Control Center V3 tab states plainly that the V3
backend is not yet live and refuses to run a prediction. **No fake result is shown.**

### Live audit performed

| surface | verified |
|---|---|
| frontend static/HTTP | **yes** — 16/16 checks on the live page |
| frontend visual (browser) | **no** — no browser automation was run; only static HTML inspection |
| backend HTTP | **yes** — `/health` 200, `/api/v3/*` 404 (pre-V3 build confirmed) |
| backend V3 routes live | **no** — pending the manual deploy |

## 13. Git

Five logical commits on `main`:

1. `e1f6e39 Package the frozen V3 product predictor: label policy and confidence tiers`
2. `1d8f112 Add V3 history API and response contract`
3. `6e012f0 Integrate V3 into the Control Center`
4. `cdc6496 Add V3 product audits and top-K behaviour gates`
5. `1f7a128 Ship V3 in the deploy bundle and document the synthetic product candidate`

| item | value |
|---|---|
| start HEAD | `43d2ba3` |
| branch | `main`, pushed to `origin/main` |
| working tree | clean |
| force push | none |

No secrets, no `.env`, no tokens, no caches, no `node_modules`, no training scratch
data, no unrelated refactors.

## 14. Final Verdict

> **V3 SYNTHETIC PRODUCTIZATION COMPLETE —
> CODE AND FRONTEND READY; BACKEND MANUAL DEPLOY REQUIRED**

All ten critical gates pass (frozen artifacts unchanged, PIT/leakage, predictor
parity, top-K behaviour, weak-label policy, API contracts, V2.1 unchanged,
Maintenance Urgency unchanged, no real-fleet claim, full regression). The frontend
is live. The backend is code-complete, its container packaging is fixed and
verified, and it awaits one manual Render deploy that this environment has no
credentials to perform.

---

V3 USES THE FROZEN SYNTHETIC RESEARCH CHAMPION.
V3 PREDICTS TASKS AT THE NEXT COMPLETED SERVICE.
V2.1 CONTINUES TO PREDICT SERVICE-RETURN TIMING.
MAINTENANCE DUE AND MAINTENANCE URGENCY REMAIN DETERMINISTIC.
NO REAL-FLEET VALIDATION IS CLAIMED.
