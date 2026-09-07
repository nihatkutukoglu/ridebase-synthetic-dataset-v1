# V3 Phase 24 — Rule Expectation vs ML Expectation

For each label and each landmark, two independent statements:

- **RULE EXPECTATION** — the deterministic OEM policy, projected to the next due
  date, says this task is at or past its interval (`Baseline 1b >= 0.5`).
- **ML EXPECTATION** — the frozen champion's calibrated probability clears the
  frozen threshold.

Then: how often is each actually right? Data: [`24_rule_vs_ml.csv`](24_rule_vs_ml.csv).

Measured on 8,000 VALIDATION + TEST landmarks.

| label | prevalence | both say YES | hit rate | rule only | hit rate | ML only | hit rate |
|---|---|---|---|---|---|---|---|
| `BATTERY_TEST` | 0.1819 | 3003 | 0.306 | 4354 | 0.070 | 548 | 0.383 |
| `AIR_FILTER_INSPECTION` | 0.1813 | 3699 | 0.290 | 3653 | 0.043 | 583 | 0.353 |
| `BRAKE_FLUID_CHECK` | 0.1524 | 2210 | 0.272 | 5208 | 0.087 | 401 | 0.339 |
| `AIR_FILTER_CHANGE` | 0.1470 | 1146 | 0.275 | 4579 | 0.076 | 774 | 0.309 |
| `GENERAL_SAFETY_INSPECTION` | 0.1486 | 1574 | 0.297 | 5840 | 0.097 | 278 | 0.284 |
| `CHAIN_CLEAN` | 0.3497 | 1614 | 0.563 | 1077 | 0.035 | 47 | 0.319 |
| `CHAIN_LUBRICATE` | 0.2933 | 1640 | 0.469 | 1066 | 0.024 | 35 | 0.314 |
| `CHAIN_INSPECTION` | 0.1625 | 688 | 0.344 | 1943 | 0.094 | 48 | 0.396 |
| `BRAKE_FLUID_CHANGE` | 0.0569 | 17 | 0.118 | 4617 | 0.053 | 67 | 0.433 |
| `FORK_INSPECTION` | 0.0576 | 111 | 0.252 | 7676 | 0.054 | 16 | 0.312 |
| `CVT_BELT_INSPECTION` | 0.0978 | 48 | 0.208 | 3716 | 0.082 | 15 | 0.333 |
| `CVT_CASE_INSPECTION` | 0.1055 | 0 | nan | 4265 | 0.099 | 1 | 0.000 |
| `FRONT_BRAKE_PAD_INSPECTION` | 0.0419 | 10 | 0.200 | 7840 | 0.041 | 2 | 0.000 |
| `VALVE_CLEARANCE_INSPECTION` | 0.0417 | 8 | 0.375 | 7082 | 0.036 | 3 | 0.000 |
| `WHEEL_BEARING_INSPECTION` | 0.0362 | 1 | 0.000 | 7161 | 0.033 | 2 | 0.000 |
| `CVT_BELT_CHANGE` | 0.0595 | 16 | 0.250 | 3158 | 0.052 | 3 | 0.000 |
| `FRONT_TIRE_INSPECTION` | 0.0315 | 12 | 0.083 | 7864 | 0.030 | 1 | 1.000 |
| `COOLANT_LEVEL_CHECK` | 0.1115 | 1 | 0.000 | 2205 | 0.107 | 1 | 1.000 |

## Where they agree

When rule and ML both say yes, the hit rate is high and tracks the label:
`CHAIN_CLEAN` 0.563, `CHAIN_LUBRICATE` 0.470, `ENGINE_OIL_CHANGE` 0.796,
`CHAIN_INSPECTION` 0.345. Agreement is a genuinely strong signal and is worth
surfacing in a research view as "due by OEM interval **and** predicted".

## Where they disagree

This is the substantive finding, and it is one-sided.

**Rule-only firings are almost always wrong.** `BATTERY_TEST`: the rule says due on
4,354 landmarks where ML disagrees, and the task actually happens on **7.0%** of
them. `BRAKE_FLUID_CHECK`: 5,208 rule-only firings, **8.7%** hit rate.
`FORK_INSPECTION`: 7,676 rule-only firings, **5.4%**. `GENERAL_SAFETY_INSPECTION`:
5,840 firings, **9.7%**.

**ML-only firings are far more often right.** `BATTERY_TEST` **38.3%**,
`AIR_FILTER_INSPECTION` **35.3%**, `BRAKE_FLUID_CHECK` **33.9%**,
`BRAKE_FLUID_CHANGE` **43.3%**, `CHAIN_INSPECTION` **39.6%**. On
`ENGINE_OIL_CHANGE`, ML fires on 1,773 landmarks the rule does not and is right
**81.6%** of the time — slightly *better* than where they agree.

**Disagreement is not called "model error".** It is a measurable claim, and on this
data the rule is the one that is wrong: it over-fires by roughly 5–10× on the
inspection-type labels, exactly as Phase 9 predicted. The rule's `due_ratio` for a
rarely-performed task grows without bound, so it shouts "overdue" forever while the
generator's bundle draw keeps declining to emit it.

## What this means for the product

A research view should show both signals side by side and label them honestly:

- **agree (both yes)** — high confidence, ~30–80% realisation depending on label.
- **ML only** — the model has learned an emission rate the interval table does not
  encode. Worth showing.
- **rule only** — "technically due by the book, but historically not performed at
  this kind of visit". This is a legitimate and useful thing to *show a workshop*,
  but it must not be presented with the same confidence as the other two.

This also settles the Phase-9 question from the other direction: if V3 were merely
replicating the generator's rules, the `ml_only` column would be empty and the
`rule_only` hit rate would be high. Both are the opposite.
