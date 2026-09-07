# V3 Phase 17 — Top-K Product Audit

**RESULT: PASS** — 0 failing checks.

Run against the **frozen** V3 champion. Nothing was retrained. Every scenario is a
**filter over real landmarks**, never a hand-built feature row: a synthetic row can
silently violate the joint distribution (100,000 km on a three-month-old bike) and
then "pass" a check that means nothing.

No expected probability is asserted anywhere. The checks are invariants; the
probability columns are reported for inspection, not compared to a target.

Data: [`17_topk_product_audit.json`](17_topk_product_audit.json).
Re-runnable: `/usr/bin/python3 scripts/v3_product_audit.py`.

## Scenario sweep (up to 2,000 landmarks each, VALIDATION + TEST)

| scenario | rows | finite | [0,1] | determ. | rank stable | no dupes | top-K count | hidden hidden | ranks ok | tier valid | YÜKSEK⊆PRIMARY | disclaimer | not-failure | no V2.1 field | 44 labels | mean top-1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `recent_service` | 2,000 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.858 |
| `near_maintenance` | 1,088 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.865 |
| `overdue` | 2,000 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.731 |
| `high_usage` | 791 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.836 |
| `low_usage` | 1,619 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.821 |
| `rich_task_history` | 2,000 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.791 |
| `sparse_task_history` | 1,318 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.859 |
| `no_task_history` | 10 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.756 |
| `unseen_motorcycle` | 1,725 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.826 |
| `older_motorcycle` | 145 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.806 |
| `newer_motorcycle` | 2,000 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.876 |
| `chain_drive` | 2,000 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.825 |
| `scooter` | 2,000 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 0.825 |

### What each column checks

| check | meaning |
|---|---|
| finite / [0,1] | every one of the 44 probabilities is finite and in range |
| determ. | identical input, run twice, produces byte-identical product output |
| rank stable | the ranked task order is identical on repeat |
| no dupes | a task code cannot appear twice in one top-K list |
| top-K count | `top_k=3` returns at most 3, `top_k=5` at most 5 |
| hidden hidden | no `HIDDEN_BY_DEFAULT` label ever appears in the product list |
| ranks ok | ranks are `1..n` with no gaps, probabilities strictly descending |
| tier valid | confidence is one of YÜKSEK / ORTA / DÜŞÜK / SINIRLI VERİ |
| YÜKSEK ⊆ PRIMARY | a YÜKSEK tier can only ever attach to a PRIMARY label |
| disclaimer | the synthetic-validation disclaimer is present on every response |
| not-failure | "bu yüzdeler mekanik arıza olasılığı değildir" present on every response |
| no V2.1 field | no urgency score and no V2.1 horizon probability in the payload |
| 44 labels | all 44 labels are returned in `all_task_probabilities` regardless of policy |

## Confidence tier distribution across the sweep

| tier | occurrences |
|---|---|
| YUKSEK | 22,509 |
| ORTA | 21,165 |
| DUSUK | 12,414 |

Most shown tasks land in DÜŞÜK or ORTA. That is the intended behaviour, not a
defect: outside the leading task the calibrated probabilities are genuinely modest,
and the tier is telling the truth about them rather than flattering the card.

## Leading task across the sweep

| task | times ranked #1 |
|---|---|
| `ENGINE_OIL_CHANGE` | 18,402 |
| `FRONT_TIRE_CHANGE` | 229 |
| `CHAIN_CLEAN` | 21 |
| `GENERAL_SAFETY_INSPECTION` | 20 |
| `CHAIN_LUBRICATE` | 18 |
| `CHAIN_INSPECTION` | 5 |
| `CVT_CASE_INSPECTION` | 1 |

`ENGINE_OIL_CHANGE` dominates rank 1, which matches its 78–88% prevalence in the
data. A product that did *not* lead with the oil change would be wrong.

## Weak-label probe (Phase 16)

4,000 landmarks were checked for a `HIDDEN_BY_DEFAULT` label scoring at or above the
shown leader:

| result | value |
|---|---|
| landmarks where a hidden label out-ranks the shown leader | **0** (0.00%) |
| handling if it happens | not shown in the product list; a reliability warning is attached and the tier stays DUSUK |

**Zero occurrences.** The frozen model does not assign high probability to the
random-event labels, which is consistent with the Phase-9 finding that they carry
almost no learnable signal — the model correctly declines to be confident about
them. The warning path exists and is tested regardless, because "it does not happen
today" is not a reason to ship without the guard.

## Sparse and absent history

`no_task_history` matched only **10** landmarks and `sparse_task_history` 1,318.
Both pass every invariant. The scarcity is itself informative: in this world almost
every landmark has some prior task history, so a completely cold motorcycle is a
genuine edge case rather than a common one. Its numbers are reported with the row
count attached and should not be read as an estimate.

## Subgroups that behave differently

`overdue` shows the lowest mean top-1 probability (0.731 against 0.858 for
`recent_service`). A bike far past its oil interval has usually *also* drifted from
its normal service pattern, so the model is less certain what the next visit will
contain — the uncertainty is real and the tier reflects it.
