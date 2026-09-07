# V3 Phase 16 — Large Top-K Product Audit

**RESULT: PASS** — 0 failing checks across **15 scenarios**.

Run against the **frozen** V3 champion; nothing retrained. Every scenario is a
**filter over real landmarks**, never a hand-built feature row: a synthetic row can
violate the joint distribution and then "pass" a check that means nothing.

No expected probability is asserted. The probability columns are reported for
inspection only — this audit deliberately makes **no claim about real-world
reasonableness**, only about synthetic product behaviour.

Data: [`16_topk_product_audit.json`](16_topk_product_audit.json).
Re-runnable: `/usr/bin/python3 scripts/v3_product_audit.py`.
(Filed as `17_*` in the previous session; renamed here with history preserved.)

## Scenario sweep (up to 2,000 landmarks each, VALIDATION + TEST)

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
| `extreme_overdue` | 426 | PASS | 0.716 |
| `same_day_duplicate_records` | 9 | PASS | 0.905 |

Two scenarios were added in this pass, both named by the productization brief:

- **`extreme_overdue`** — oil due-ratio ≥ 4× interval (426 landmarks). Mean top-1
  drops to 0.716, the lowest of any scenario except plain `overdue` (0.731). A bike
  this far past its interval has usually also left its normal service pattern, so
  the model is genuinely less certain and the confidence tier reflects it.
- **`same_day_duplicate_records`** — landmarks sitting inside a service that
  straddles midnight (9 landmarks in the VALIDATION/TEST pool). These are exactly
  the rows where the V2.1 history builder and the V3 training builder disagree
  ([`07_predictor_parity.md`](07_predictor_parity.md)). The product still behaves:
  bounded, finite, deterministic, correctly warned.

## Checks applied to every scenario

finite probabilities · bounds [0,1] · byte-identical deterministic repeat · stable
ranking · no duplicate task codes · correct top-K size for k=3 and k=5 ·
`HIDDEN_BY_DEFAULT` never shown · dense ordered ranks · valid confidence tier ·
YÜKSEK only on PRIMARY labels · synthetic disclaimer present · not-a-failure
disclaimer present · no urgency or V2.1 field in the payload · all 44 labels
returned in `all_task_probabilities`.

## Confidence tier distribution

| tier | occurrences |
|---|---|
| YUKSEK | 22,887 |
| ORTA | 21,538 |
| DUSUK | 12,968 |

Most shown tasks land in DÜŞÜK or ORTA. That is intended, not a defect: outside the
leading task the calibrated probabilities are genuinely modest, and the tier says so
rather than flattering the card.

## Leading task across the sweep

| task | times ranked #1 |
|---|---|
| `ENGINE_OIL_CHANGE` | 18,804 |
| `FRONT_TIRE_CHANGE` | 261 |
| `CHAIN_CLEAN` | 21 |
| `GENERAL_SAFETY_INSPECTION` | 20 |
| `CHAIN_LUBRICATE` | 19 |
| `CHAIN_INSPECTION` | 5 |
| `CVT_CASE_INSPECTION` | 1 |

`ENGINE_OIL_CHANGE` dominates rank 1, consistent with its 78–88% prevalence. A
product that did *not* lead with the oil change would be wrong.

## Weak-label probe (Phase 15)

4,000 landmarks checked for a `HIDDEN_BY_DEFAULT` label scoring at or above the
shown leader:

| result | value |
|---|---|
| landmarks where a hidden label out-ranks the shown leader | **0** (0.00%) |
| handling if it happens | not shown in the product list; a reliability warning is attached and the tier stays DUSUK |

**Zero occurrences.** The frozen model does not assign high probability to the
random-event labels, consistent with Phase 9 of the research finding no learnable
signal in them — it correctly declines to be confident. The warning path is
implemented and unit-tested regardless: "it does not happen today" is not a reason
to ship without the guard.

## Small-sample honesty

`no_task_history` matched 10 landmarks and `same_day_duplicate_records` 9. Their row
counts are printed beside every number and they are **not** estimates. The scarcity
is itself the finding: in this world almost every landmark has some prior task
history, and midnight-straddling landmarks are ~0.12% of the population.
