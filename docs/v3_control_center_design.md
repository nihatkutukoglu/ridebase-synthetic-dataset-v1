# V3 Control Center Card — Design Specification

**STATUS: DESIGN ONLY. NOT DEPLOYED.** No frontend change was made. No route was
mounted. This document specifies what a future V3 card would look like if — and
only if — real-fleet validation is completed first.

## Placement

A fourth, clearly separated card in the Control Center, below the existing three.
It must not visually merge with them, because the three existing surfaces answer
questions about *whether and when*, while V3 answers *what*.

| Existing surface | Question | Output |
|---|---|---|
| Maintenance Due | does it need scheduled maintenance now? | deterministic yes/no |
| Maintenance Urgency | how overdue is it? | deterministic 0–100 |
| V2.1 Service Return | will it come back in 30/60/90/120 days? | calibrated probabilities |
| **V3 (this card)** | **what will be done when it does come back?** | **per-task probabilities** |

## Card

```
┌────────────────────────────────────────────────────────────┐
│  V3 — NEXT EXPECTED SERVICE TASKS          [RESEARCH ONLY] │
├────────────────────────────────────────────────────────────┤
│  Oil change                                     ████  91%  │
│  Air filter inspection                          ███   72%  │
│  Battery test                                   ██▌   64%  │
│  Chain clean                                    ██    43%  │
│  Front brake pad inspection            ⚠ low    █     21%  │
├────────────────────────────────────────────────────────────┤
│  These probabilities estimate which tasks may occur at the │
│  next completed service. They are not mechanical failure   │
│  probabilities.                                            │
│                                                            │
│  Landmark 2026-07-31 · 44 modelled tasks · 31 applicable   │
│  to this motorcycle · model v3.0-research                  │
└────────────────────────────────────────────────────────────┘
```

The percentages above are **illustrative layout figures, not model output.** Real
card values come from the frozen predictor at render time. No expected probability
is hardcoded anywhere in this spec or in the tests.

## Required semantics on the card

Verbatim, non-removable:

> These probabilities estimate which tasks may occur at the next completed
> service. They are not mechanical failure probabilities.

`BRAKE_DISC_CHANGE = 0.21` means "a disc change is likely to appear on the next
work order", **not** "there is a 21% chance the disc fails". The card is a parts
and labour planning aid, not a safety indicator, and a customer-facing variant
would need that distinction re-tested with real users.

## Display rules

1. **Rank by calibrated probability**, descending. Show the top 5 applicable tasks.
2. **Never show an inapplicable task.** Tasks the motorcycle's powertrain and
   drivetrain rule out are forced to 0.0 and omitted entirely — not shown at 0%,
   which reads as "due but not needed".
3. **Floor at 1%.** Below that the number is noise dressed as information.
4. **Flag low-support labels** with a `⚠ low` marker. The 19 `B_LOW_FREQUENCY`
   labels clear the modelling gate but have wide uncertainty.
5. **Never show the 15 random-event labels as confident predictions.** Breakdown
   diagnostics and inspection findings are, by construction in this dataset,
   unpredictable from anything observable at the landmark (Phase 9). If they
   surface at all it must be as a separate, explicitly hedged section.
6. **Show the landmark date.** A V3 answer is only meaningful relative to a point
   in time and the odometer reading at that point.
7. **No urgency score, no V2.1 probability in this card.** Cross-referencing
   invites a reader to multiply or reconcile numbers that have different
   denominators and different semantics.

## What the card must NOT do

- Must not sum task probabilities to a "total service probability".
- Must not synchronise or reconcile V3 numbers against Maintenance Urgency or
  V2.1 P30/P60/P90/P120.
- Must not present V3 as validated on real fleet data.
- Must not imply the listed tasks are a quote, a booking, or a commitment.

## Data path (when and if this is ever built)

The offline predictor is `ridebase_ml.v3.predictor.V3TaskPredictor`, whose response
schema is specified in [`docs/v3_product_output_contract.md`](v3_product_output_contract.md).
A future route would need its own history serving store, built the way the V2.1
store was, because V3's task-history features are not in the V2.1 store today. That
work is **not** part of this research session.

## Preconditions before any deployment

1. Real-fleet validation of the task labels (currently PENDING).
2. A V3-specific serving store with task-level history.
3. Product review of the failure-probability confusion risk with real users.
4. A decision on whether the 15 unlearnable random-event labels appear at all.
