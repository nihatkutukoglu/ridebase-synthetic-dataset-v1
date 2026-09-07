# V3 Target Contract — Multi-Label Next-Service Task Prediction

Status: **OFFLINE RESEARCH**. Not deployed, not mounted, not served.
Machine-readable copy: [`config/v3_target_contract.json`](../config/v3_target_contract.json).

## The question V3 answers

> At the next completed service, which maintenance tasks will be performed?

## What V3 is not

| Surface | Question it answers | Relationship to V3 |
|---|---|---|
| Maintenance Due | Does this motorcycle currently require scheduled maintenance? | Deterministic. Separate. |
| Maintenance Urgency | How overdue is the scheduled maintenance state (0–100)? | Deterministic. Separate. |
| V2.1 | Probability of returning for service within 30/60/90/120 days? | Frozen production champion. Separate. |
| **V3** | **Which tasks will be performed at the next completed service?** | **This document.** |

V3 probabilities are never synchronised with, derived from, or reconciled against
Maintenance Urgency or V2.1 P30/P60/P90/P120. A V3 response contains no urgency
score and no service-return probability. V3 probabilities are also **not**
mechanical-failure probabilities — `BRAKE_DISC_CHANGE = 0.21` means "a disc change
is likely to appear on the next work order", not "there is a 21% chance the disc
fails".

## Source world

RideBase Synthetic Dataset **v1.4** (`ridebase_v1_4/source_tables/`), the world the
frozen V2.1 production champion was trained and is served on. v1.5 exists but is
the V2.2 behavioural branch, which was never promoted; building V3 there would
make it incomparable with the live product surface. All source tables are read-only.

## Landmark

An end-of-month observation point for one motorcycle, taken **unchanged** from the
frozen V2.1 dynamic-landmark grid
(`ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet`, 256,841
landmarks × 74 columns, 8,907 motorcycles, 2021-01-31 → 2026-07-31).

V3 does not re-derive the grid. Its landmark placement, its point-in-time feature
semantics and its temporal split have already been leakage-audited and shipped for
production; inheriting them is both cheaper and safer than maintaining a parallel
copy that could drift.

## Target service

> The first service the motorcycle arrives at **strictly after** the landmark,
> within the motorcycle's administrative observation window.

In v1.4 **every** row of `services.csv` has `status = DELIVERED` — there is no such
thing as an incomplete service record. Arrival implies completion: `completed_at`
is never null, is always ≥ `received_at`, the median turnaround is 1.3 hours and
90.7% of services complete on the calendar day they arrive. Selecting on arrival
(`received_at`, as V2.1 does) and selecting on completion therefore give the same
service, and V3 reuses V2.1's `next_service_id` pointer directly.

**Right-censored landmarks are excluded, not labelled empty.** A landmark whose
motorcycle never returns has an *unknown* target, not an all-zero one. Encoding it
as all-zero would teach the model that "no service yet" means "no tasks", which is
false and would corrupt every label's base rate.

### Eligible target service types

All four `service_type_code` values are eligible: `PERIODIC` (46,542), `REPAIR`
(2,704), `TIRE` (1,790), `BREAKDOWN` (1,664).

The product question is "at the customer's next visit, what gets done" — not "at
the next *periodic* visit". Restricting to `PERIODIC` would condition the label on
an event type that is itself unknown at the landmark, which is a subtler form of
target leakage.

## Target labels

> A task code recorded on the target service with `service_tasks.status = COMPLETED`.

`DECLINED` task lines (1,415 of 215,182) are **negative**. A declined task was
recommended and *not performed*; V3 predicts what will be performed.

This is a deliberate departure from the generator's own
`derived_outputs/ml_next_task_targets.parquet`, whose
`target_definition = TASK_PRESENT_IN_NEXT_SERVICE_PLAN_COMPLETED_OR_DECLINED`
counts declined tasks as positive. That table also uses one landmark per service
event, which cannot be compared against alternative landmark strategies. It is
retained as a cross-check reference only.

### Label eligibility and applicability

Two separate filters:

1. **Eligibility** — `maintenance_tasks.can_be_next_service_target = 1` (93 of 98
   task codes). The taxonomy's own contract for what can be a next-service target.
2. **Applicability** — a task is scored on a motorcycle only if the taxonomy's
   `applicable_powertrain`, `required_final_drive`, `required_cooling_type` and
   `required_transmission_type` match that motorcycle's model spec.

Applicability is a hard, deterministic product rule, not a learned correction. A
chain task on a CVT scooter is forced to probability 0 for every model and every
baseline alike, and per-label metrics are computed only over applicable rows. Not
masking would let a label look "rare" merely because most of the fleet lacks the
part, and would penalise a model for correctly never predicting an impossible task.

## Event-type decisions (explicit, as required)

| Event | Counts as target service? | Notes |
|---|---|---|
| Completed scheduled maintenance | **Yes** | `PERIODIC`, 46,542 services |
| Workshop inspection | **Yes, as labels** | No separate inspection-only service type exists in v1.4; inspection tasks appear inside `PERIODIC`/`REPAIR` services |
| Oil change | **Yes** | `ENGINE_OIL_CHANGE`, modelled |
| Filter replacement | **Partly** | `AIR_FILTER_CHANGE` modelled; `OIL_FILTER_CHANGE` and `FUEL_FILTER_*` excluded on support — see Unresolved semantics |
| Chain service | **Yes** | `CHAIN_CLEAN` / `CHAIN_LUBRICATE` / `CHAIN_INSPECTION`, chain-drive bikes only |
| Tire replacement | **Yes** | `FRONT_TIRE_CHANGE`, `REAR_TIRE_CHANGE` |
| Brake work | **Yes** | pad inspect/change, fluid check/change, disc change, system bleed |
| Coolant | **Yes** | `COOLANT_LEVEL_CHECK` / `COOLANT_CHANGE`, liquid-cooled only |
| Battery | **Yes** | `BATTERY_TEST` / `BATTERY_CHANGE` |
| Clutch | **Excluded** | only 1,898 applicable rows (manual-transmission bikes) and <200 pre-TEST positives |
| Valve inspection | **Yes** | `VALVE_CLEARANCE_INSPECTION` (core), `VALVE_CLEARANCE_ADJUST` (low-frequency) |
| Breakdown repair | **Yes** | `BREAKDOWN` services are real visits; their task lines are labels like any other |
| Warranty service | **Yes, but see note** | in v1.4 `is_warranty` is *perfectly collinear* with `is_breakdown` (both exactly 1,664 rows) — warranty is not an independent event type in this world |
| Cancellation | **No** | 2,552 `CANCELLED` appointments never produce a service row |
| No-show | **No** | 2,052 `NO_SHOW` appointments never produce a service row |
| Appointment without completion | **No** | only `CONVERTED_TO_SERVICE` (30,901) reaches `services.csv`; `RESCHEDULED` (844) does not |

## Unresolved semantics (marked, not guessed)

1. **`OIL_FILTER_CHANGE` is decoupled from `ENGINE_OIL_CHANGE`.** 40 positives
   against 34,762 oil changes. Real workshops almost always pair them, and the V3
   brief's own example output shows "Oil filter 0.84". This generator does not
   model that coupling. Flagged as a data-semantics finding; the label is excluded
   on support, and **no coupling was invented to make the example output
   reproducible**.
2. **Warranty has no independent meaning** in v1.4 (perfectly collinear with
   breakdown), so no separate warranty contract line can be established from data.
3. **No pure-inspection service type exists.** Inspection visits are not
   separable from `PERIODIC`/`REPAIR` in this schema.

## Feature side of the contract

Predictors use **only** information available at or before the landmark. The
forbidden list, the point-in-time guarantee and the audit that enforces it are in
[`reports/v3/08_leakage_audit.md`](../reports/v3/08_leakage_audit.md). No
motorcycle ID, customer ID, workshop ID, service ID, split indicator, row ID,
target-service field, or generator latent variable is ever a feature.
