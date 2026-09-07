# V3 Phase 8 — Leakage Audit

**GATE RESULT: PASS** — model training is unblocked.

Machine-readable: [`ridebase-ml/derived_outputs/v3/08_leakage_audit.json`](../../ridebase-ml/derived_outputs/v3/08_leakage_audit.json).
Re-runnable: `/usr/bin/python3 scripts/v3_research.py leakage`.

## Structural guarantee

Every V3 history feature flows through exactly one function,
`ridebase_ml.v3.features._asof_last`, which is a **backward** `merge_asof` keyed on
`landmark_at`. It is not *possible* for that join to return a row with
`event_at > landmark_at`. Concentrating all history access in one choke point is
what makes the empirical checks below meaningful — there is no second path a
future value could arrive by.

The policy-state block (F1) is derived from the history block plus the static
`maintenance_policies.csv` intervals, so it inherits the same guarantee. The base
block (F0) and behavioural block (F4) are the frozen V2.1 54-column contract,
already audited for production.

## Check 1 — name and identity screen

277 feature columns screened against 3 forbidden
tokens (`target`, `next_`, `future_`, `service_after`, `task_after`,
`duration_days`, `event_observed`, `censor`, `administrative_cutoff`, `split`,
`modeling_role`, every identifier, `snapshot_year`, `days_observed`,
`event_within_`, `is_unseen`, `lead_days`, and the generator latent tokens
`adherence`, `churn`, `frailty`, `latent`, `tendency`, `propensity_true`).

**Violations: 0.**

Three names trip the deliberately blunt substring screen and are allowlisted with
justification rather than the screen being narrowed — it is cheaper to justify
three names than to weaken the token list and let a real leak through later:

- **`days_until_next_scheduled_due`** — V2.1 contract feature: days until the next OEM *scheduled maintenance due date*, computed at the landmark from maintenance_policies intervals. It refers to a policy deadline, not to the next service event, and is unchanged by anything that happens after the landmark.
- **`km_until_next_scheduled_due`** — Same as above on the km axis.
- **`avg_parts_lead_days`** — Workshop-level average parts procurement lead time. Trips the screen only because V3's landmark-to-target gap is also called lead_days; the two are unrelated and this one is a workshop attribute known at the landmark.

No identifier reaches the model: `motorcycle_id`, `customer_id`, `workshop_id`,
`model_id`, `landmark_id`, `next_service_id`, `source_last_service_id`,
`v3_split` and the row index live in `V3Dataset.meta`, which is a separate frame
the model never sees. `model_id` is excluded even though it is tempting — the
motorcycle's *hardware* reaches the model through `brand`, `category`,
`powertrain_type` and `policy_group`, which generalise to unseen models, while the
raw id would be a lookup key.

## Check 2 — future-injection invariance

The strongest of the three, because it does not depend on anyone having named the
leaking column correctly.

**Method.** 4,000 landmarks (one per motorcycle — see below),
16,000 fabricated task events appended to the event log at
**+1, +7, +30 and +120 days** after each landmark. Each injected row is
indistinguishable from a genuine service line: same motorcycle, a real task code,
a plausibly higher odometer. Only its date makes it illegitimate. The entire
feature matrix (history + policy + aggregates) is rebuilt from the poisoned log.

**Result: byte-identical.** `0` columns changed.

- digest before: `44f4072646e28888014c1d9cfcc5fa2f02ff093436eaeaab15c1975d19e331b2`
- digest after:  `44f4072646e28888014c1d9cfcc5fa2f02ff093436eaeaab15c1975d19e331b2`

**Why one landmark per motorcycle.** The first run of this check reported 195
changed columns and looked like a catastrophic leak. It was not: with several
landmarks of the same motorcycle in the tested set, an event injected after the
*earlier* landmark is legitimately in the *past* of the later one, and the feature
matrix is *supposed* to change. Restricting the audit sample to one landmark per
motorcycle removes that confound, so any remaining change is real leakage. The
audit was wrong, not the builder — but the test as originally written would have
been useless in both directions, and `leakage.audit_sample` now enforces the
constraint.

## Check 3 — T-1 / T / T+1 boundary

An event of task `ENGINE_OIL_CHANGE` is injected at each offset relative to the
landmark, and the resulting `hist_count` is compared against the clean build.

| Offset | Rows whose features changed | Expected | Result |
|---|---|---|---|
| T-1 (day before) | 4,000 / 4,000 | all — the event is history | PASS |
| T (landmark day) | 4,000 / 4,000 | all — the target service is defined as *strictly* after the landmark, so a same-day service is history | PASS |
| T+1 (day after) | 0 / 4,000 | none — the event is the future | PASS |

### A real bug this check caught

The first run gave **3,986 / 4,000** for T-1 and T instead of 4,000. The 14
stragglers were motorcycles that already had a genuine task line on the exact
injected date. `merge_asof` returns the *last* tied row, and the occurrence index
`prior_n` was assigned after a non-stable `sort_values`, so which of the two tied
events won — and therefore the reported `hist_count` — depended on row arrival
order rather than on the data.

Fixed in `features.task_history_features` by sorting events on
`(motorcycle_id, task_code, event_at, service_id)` before the cumulative count and
using `kind="stable"` on every subsequent sort, so the highest occurrence index is
deterministically last among ties. This was a genuine non-determinism defect in
the feature builder, not a test artifact, and it is exactly the class of bug a
boundary test exists to find. Determinism is now covered by a regression test.

## Forbidden-input inventory

Confirmed absent from the feature matrix:

| Forbidden | Status |
|---|---|
| target service date / odometer / task list | absent — `meta` only, never `features` |
| `current_service_*` fields describing the target | absent — no such column is built |
| future appointment outcome | absent |
| any event after the landmark | absent — proven by Check 2 |
| censor / outcome fields (`event_observed`, `duration_days`) | absent |
| generator latent adherence / churn / frailty | absent — these live only in `ridebase_v1_5/reports/v1_5_generator_event_audit.parquet`, which V3 never loads |
| split indicator, row ID, motorcycle ID, service ID | absent — `meta` only |
| absolute future-year shortcut | absent — only `landmark_month_sin/cos` (cyclical, year-free) |

## Reproduction

```
/usr/bin/python3 scripts/v3_research.py leakage
```
