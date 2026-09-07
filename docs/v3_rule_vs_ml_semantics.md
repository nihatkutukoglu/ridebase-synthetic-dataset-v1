# Rule vs V3 — Explainability Semantics

The deterministic maintenance rule and the V3 model answer **different questions**
and may be shown side by side. **The rule never alters a V3 probability.**

## The two signals

| signal | question | source |
|---|---|---|
| **Bakım planı** | Is this task at or past its OEM interval *now*? | `maintenance_policies.csv`, deterministic |
| **V3** | Will this task appear on the work order of the next completed service? | frozen CatBoost multi-label model |

## Allowed presentation

```
Motor Yağı
  V3: 72%
  Bakım planı: DUE
```

Two labelled rows, two sources, no arithmetic between them. The rule may be shown
as **context**, never as a modifier, a multiplier, a confidence booster, or a
tie-break.

## Forbidden

- adjusting a V3 probability because the rule says DUE (or not DUE)
- averaging, multiplying or otherwise fusing the two into one number
- suppressing a V3 task because the rule disagrees
- promoting a task in the ranking because the rule agrees
- describing agreement as "confirmed" or disagreement as "model error"

## What the data actually says about disagreement

This is not a hypothetical caution. The research phase measured it over 8,000
landmarks ([`reports/v3/24_rule_vs_ml_analysis.md`](../reports/v3/24_rule_vs_ml_analysis.md)):

| case | firings | hit rate |
|---|---|---|
| rule says DUE, V3 disagrees | thousands per label | **0.02 – 0.10** |
| V3 says likely, rule disagrees | hundreds per label | **0.28 – 0.43** |

`BATTERY_TEST`: 4,354 rule-only firings hit **7.0%**; 548 V3-only firings hit
**38.3%**. On `ENGINE_OIL_CHANGE`, V3 fires on 1,773 landmarks the rule does not and
is right **81.6%** of the time.

**When the two disagree, the rule is usually the one that is wrong.** The Phase-9
generator audit explains why: the policy table is a *gate* on which tasks are
eligible for a work order, and a stochastic bundle draw decides which eligible ones
actually appear. A rarely-performed task's due-ratio grows without bound, so the
rule shouts "overdue" forever while the task keeps not happening.

So a UI that shows both must not imply the rule is ground truth and V3 is an
approximation of it. They are different claims, and on this data the model is the
better predictor of what gets done.

## Recommended wording

| situation | wording |
|---|---|
| both agree | "Bakım planına göre de bekleniyor" |
| V3 only | show the V3 probability alone; no rule row |
| rule only | "Bakım planına göre süresi geçmiş, ancak bu tür ziyaretlerde genelde yapılmıyor" |

The third row is genuinely useful to a workshop — it is a real fact about the
maintenance schedule — but it must not be presented with the same weight as a V3
prediction.

## Implementation status

**Not implemented in the shipped V3 card.** The V3 Control Center module currently
shows V3 probabilities only. This document defines the semantics *if* a rule column
is added later; adding it is a product decision, not a modelling one, and would
require no change to the frozen model or to any probability.

The one place the rule already legitimately enters V3 is as a **training feature**
(`policy_due_ratio__*`, `policy_overdue__*`, the F1 block). That is upstream of the
probability, was frozen at training time, and is not a post-hoc adjustment.
