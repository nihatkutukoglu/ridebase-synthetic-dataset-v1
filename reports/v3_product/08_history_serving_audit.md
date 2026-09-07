# V3 Phase 8 — History Feature Serving Audit

**RESULT: PASS.** Data: [`08_history_serving_audit.json`](08_history_serving_audit.json).

## Path

```
motorcycle_id + landmark_date
  -> V2.1 read-only SQLite history adapter   (already audited and shipped)
  -> V2.1 build_features                     -> 54-column base contract (F0 + F4)
  -> V3 task history / recency / policy state -> 223 further columns
  -> frozen 277-column V3 feature vector
  -> frozen V3 predictor -> Top-K
```

**No new data store was introduced.** The prior session's finding that
`get_service_tasks_before` already exists on the V2.1 adapter was verified in the
current repo and is correct: `/api/v3/predict/by-motorcycle` reads the same
`v2_1_history_serving.sqlite` that already serves `/api/v2_1/predict/by-motorcycle`,
and never writes to it.

## Point-in-time battery (40 landmarks)

| check | result |
|---|---|
| deterministic repeat | **40/40** |
| no event after the landmark reaches the features | **40/40** |
| history counts monotone across T-1 / T / T+1 | **40/40** |
| same-day task-line shuffle invariance | **40/40** |

Shuffle invariance is checked with an adapter wrapper that deliberately reverses
the task rows — the regression for the determinism defect found during V3 research,
where two task lines on one date could swap and change `hist_count`.

Exact 277/277 feature parity and full predictor parity are covered separately in
[`07_predictor_parity.md`](07_predictor_parity.md): **4,995 of 5,000 landmarks
reproduce the research pipeline bit-for-bit**, and the 5 that do not are exactly
the ones the serving layer flags as midnight-straddling.

## Point-in-time rules enforced here

| rule | how |
|---|---|
| no future task rows | history gated on parent service `received_at <= landmark` |
| no target service | the target is by definition the first service *after* the landmark |
| current odometer PIT-safe | taken from the V2.1 base contract, itself built only from services at/before the landmark |
| no IDs as predictors | `motorcycle_id` is a lookup key, never a feature column |
| declined tasks excluded | a `DECLINED` line was recommended, not performed, and reset no interval |

The 7-day fetch lookahead widens only the *candidate row query*, never the
boundary: the binding filter is membership in `get_services_before`, so a task
whose service arrived after the landmark can never be admitted. A test asserts it.

## Latency by history depth

| history depth | rows | p50 | p95 |
|---|---|---|---|
| sparse (≤5 prior task lines) | 60 | 27.22 ms | 28.54 ms |
| typical (6–30) | 60 | 28.47 ms | 30.5 ms |
| rich (>30) | 60 | 32.88 ms | 37.96 ms |

Feature-build cost grows only mildly with history depth (27 → 33 ms p50), because
the per-task as-of lookups dominate and their count is fixed at 44.

## Sparse and absent history

**15 landmarks** have service history but **none of the 44 modelled tasks**.

This audit found a gap and it was fixed: those landmarks previously produced **no
warning at all**, because the builder only warned when the raw event list was
empty. A bike can have plenty of service history consisting entirely of task codes
outside the modelled set — every history and recency feature then sits on its
"never performed" sentinel while the response looked completely normal. The builder
now warns explicitly in that case.

Note that `feature_coverage` stays **1.0** for these rows, and that is correct: the
sentinels are legitimate reconstructed values, not missing data. Coverage measures
"could this be rebuilt from history", not "is there much history". The warning is
what carries the second meaning.

## Error behaviour

| input | result |
|---|---|
| landmark before the motorcycle's observation window | `UnknownMotorcycleError` → HTTP 422 |
| malformed landmark date | `HistoryInputError` → HTTP 422 |
| unknown `motorcycle_id` | HTTP 404 at the route |

**No failure path fabricates a prediction.** Missing history is an error or a
warning, never a filled-in guess.
