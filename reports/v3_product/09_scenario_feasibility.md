# V3 Phase 9 — Scenario Feasibility Audit

**Decision: C — NO SCENARIO ROUTE.**

`POST /api/v3/predict/scenario` is **not implemented**. This is a scientific
decision backed by measurement, not a scoping shortcut.

## The question

V1 and V2.1 both offer a "scenario" route where a user types natural inputs
(brand, odometer, usage) and gets a prediction. Can the same be done for V3?

## Feature contract composition

| block | features | reconstructable from natural user input? |
|---|---|---|
| F0 base (motorcycle, odometer, time/km since last service) | 37 | yes |
| F4 behavioural (prior service counts, delays, spend, workshop) | 17 | partly, with effort |
| F1 policy state (`policy_due_ratio__X`, `policy_overdue__X`) | 88 | **no** — derived from per-task last-occurrence |
| F2 task history (`hist_count__X` + aggregates) | 47 | **no** |
| F3 task recency (`days_since__X`, `km_since__X`) | 88 | **no** |

**223/277 features (80.5%) depend on per-task service history.** Reconstructing
them from natural input would require the user to supply, for each of 44 task
codes, how many times it has been done and how long and how far ago. That is not
a form anyone fills in — it *is* the service history.

## What fabricating history would actually do

Rather than assert the harm, it was measured. On **1,500 real TEST
landmarks**, the F1/F2/F3 blocks were replaced with the same "no history" values a
scenario route would be forced to supply (counts 0, recency `-1`, policy ratio
`-1`), and the frozen model was re-run:

| effect | value |
|---|---|
| top-3 list unchanged | **2.7%** |
| mean top-3 overlap | 50.6% |
| mean absolute probability change | 0.0471 |
| **max absolute probability change** | **0.8134** |
| `ENGINE_OIL_CHANGE` mean probability | 0.805 → 0.612 |

**The top-3 answer changes in 97.3% of cases**, and a single task's probability
can move by 0.81. A scenario route would not be a slightly less precise V3 —
it would be a different model answering a different question, presented in the
same card with the same percentages.

## Why not offer it with a coverage warning (option B)?

Option B — partial scenario with explicit coverage warnings — was considered and
rejected. The confidence tier would correctly mark every such answer
`SINIRLI_VERI` at 19% coverage, which means the honest version of the feature is
a card that always says "we cannot really answer this". Shipping a route whose
every response is a disclaimer is worse than not shipping it: the percentages
would still be rendered, and a percentage on screen is read as an answer no
matter what the label beside it says.

The brief's own rule settles it: **never fake missing task history.**

## What is offered instead

`POST /api/v3/predict/by-motorcycle` is the primary product flow: a real
`motorcycle_id` plus a `landmark_date`, resolved through the audited V2.1
read-only history adapter into the exact frozen feature vector. It achieves
**100% feature coverage** and reproduces the research feature matrix
byte-for-byte (see the parity gate in
[`V3_SYNTHETIC_PRODUCTIZATION_COMPLETION.md`](V3_SYNTHETIC_PRODUCTIZATION_COMPLETION.md)).

`POST /api/v3/predict` remains available for callers that already hold a complete
feature vector — an ML-facing route, not a product surface.

## Revisiting this

A scenario route becomes defensible only if a real integration can supply genuine
per-task history (a dealer DMS export, a service book import). At that point the
input is history, not a scenario, and it belongs on the by-motorcycle path with a
different adapter — not on a hand-typed form.
