# V3 Phase 7 — Research ↔ Serving PREDICTOR Parity

**RESULT: PASS.** Every divergence is confined to landmarks the serving layer
flags itself; **0 unexplained divergences.**

Feature parity alone is not enough: identical inputs can still diverge downstream
through preprocessing, calibration, applicability masking or threshold application.
This compares the two paths end to end, on predictions.

```
research path : frozen research feature matrix -> frozen model -> calibrator -> mask
serving path  : motorcycle_id + landmark -> V2.1 history adapter -> 277 features
                -> V3TaskPredictor -> calibrator -> mask
```

Re-runnable: `/usr/bin/python3 scripts/v3_predictor_parity.py --rows 5000`.
Data: [`07_predictor_parity.json`](07_predictor_parity.json).

## Scale

| item | value |
|---|---|
| rows tested | **5,000** |
| labels | 44 |
| prediction cells compared | **220,000** |
| feature cells compared | **1,385,000** |
| tolerance | 1e-09 |

Tolerance is 1e-9 because both paths run the *same* fitted objects in the same
process; anything above float-ordering noise would be real drift, not rounding.

## Result on unflagged landmarks — the headline

| metric | value |
|---|---|
| rows | **4,995** |
| **max probability delta** | **0.0** |
| ranking mismatches | 0 |
| threshold mismatches | 0 |

On 4,995 of 5,000 landmarks the packaged serving predictor reproduces the
research pipeline **exactly** — not within tolerance, but bit-for-bit identical
across all 44 labels, the full ranking, and every threshold decision.

## The 5 landmarks that do diverge

| item | value |
|---|---|
| landmarks flagged as straddling | 5 |
| landmarks with any divergence | 5 |
| divergence fully explained by the flag | **True** |
| unexplained divergent rows | **0** |

### What this is

A service that arrives late in the evening and finishes after midnight.

The **V2.1 history builder** keys its three task-derived features
(`due_task_count`, `critical_due_task_count`, `last_service_task_count`) on each
task line's own completion timestamp. The **V3 training feature builder** keys
history on the parent service's arrival date. For a landmark that falls inside such
a service, the two disagree.

Concretely — `MC009503` @ `2023-04-30`: `SVC039193` arrives 22:52:36 and completes
01:43:36 the following day. The adapter returns only the task lines finished before
midnight; the research pipeline counts the whole service.

### How big it is

Measured across the **entire** dataset, not just the sample:

| item | value |
|---|---|
| services straddling a calendar day | **5,085 of 52,700 (9.65%)** |
| task lines completing on a later day | **8.60%** |
| maximum arrival → completion gap | 5 days (120.8 h) |
| **landmarks affected** | **48 of 39,451 (0.12%)** |

On those 48 landmarks specifically: max single-task probability delta **0.296**,
mean 0.0067, top-3 identical on 37 of 48, 19 threshold flips.

### What was fixed, and what was not

**Fixed.** The V3-owned blocks (F1 policy, F2 history, F3 recency) originally
inherited the adapter's task-timestamp boundary and diverged on 25 feature cells.
`_completed_task_events` now fetches candidate rows with a bounded 7-day lookahead
and applies the real point-in-time gate itself — *parent service `received_at` ≤
landmark*, matching training exactly. The lookahead widens the **fetch**, never the
boundary: a task whose service arrived after the landmark is still dropped, because
that service is absent from `get_services_before`. A test asserts this.

**Not fixed, deliberately.** The remaining three columns are produced by
`ridebase_ml/v2_1/history_features.py`, a **frozen production contract** that also
serves `/api/v2_1/predict/by-motorcycle`. Changing it to suit V3 would mutate V2.1,
which is forbidden and would be the wrong trade regardless.

So the condition is **detected and reported** rather than hidden:
`serving.straddling_history_service()` flags it, the response carries a Turkish
warning, and `provenance.straddling_history_service` records it.

### Which semantics is actually "right"

Arguably the adapter's: standing at end-of-day 2023-04-30 you genuinely do not know
what a technician finishes at 01:43 the next morning. But the frozen model was
*trained* on the research semantics, so serving must match training or the model
receives out-of-distribution inputs. Parity with the frozen champion is the binding
requirement here; the philosophical question is noted, not silently resolved.

### Why this was not caught earlier

V2.1's own history parity report tested **300 golden landmarks** and reported
`EXACT_PARITY` on all 54 features. At roughly 1 landmark in 800 affected, a
300-row sample was very likely to miss it — as was this session's earlier 12-row
and 500-row V3 checks, both of which passed cleanly. It surfaced only at 2,000 rows.
That is the argument for running parity at scale rather than on a golden handful.

## Latency

| stage | value |
|---|---|
| history build p50 | 29.7 ms |
| history build p95 | 37.0 ms |
| batch inference (research path) | 211.1 ms / 5,000 rows |
| batch inference (serving path) | 191.3 ms / 5,000 rows |

Feature coverage was **1.0** on every row.

## Gate

The gate is *not* "few mismatches". It is: **every divergent landmark must be one
the serving layer independently flags**. Drift on an unflagged landmark fails the
gate outright. On 5,000 rows, 0 landmarks failed that test.
