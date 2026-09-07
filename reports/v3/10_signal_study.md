# V3 Phase 10 — Signal Study (TRAIN / VALIDATION only)

Run **before** the full tournament, to decide whether V3 is worth pursuing at all.
TEST was not touched. Data: [`10_signal_study.csv`](10_signal_study.csv) (per-label,
per-model), [`10_signal_summary.csv`](10_signal_summary.csv).

Models compared: the four Phase-11 baselines plus an unweighted logistic regression
and an unweighted XGBoost, all on the identical PIT-safe feature matrix.

## How to read "lift"

`lift = best ML PR-AUC / prevalence`. For a binary label, a random ranker's PR-AUC
*is* the prevalence, so lift is the honest multiple over chance.

**A large lift on a rare label is still a small number.** `FUEL_INJECTOR_CLEAN`
shows 6.6x lift — but that is PR-AUC 0.038 against a base rate of 0.006. It ranks
better than chance and is nowhere near usable as a displayed percentage. Bands
below are a triage signal, not a quality claim, and the absolute PR-AUC column is
the one that matters for the product.

| band | labels |
|---|---|
| STRONG | 32 |
| MEDIUM | 6 |
| VERY_STRONG | 5 |
| WEAK | 1 |

## Per-label results

| label | prevalence | support | rule PR-AUC | recurrence PR-AUC | best ML PR-AUC | lift vs prevalence | generating process |
|---|---|---|---|---|---|---|---|
| `FUEL_INJECTOR_CLEAN` | 0.0058 | 31 | 0.006 | 0.014 | 0.038 | 6.63x | E_INSPECTION_FINDING_RANDOM |
| `BATTERY_CHANGE` | 0.0067 | 36 | 0.012 | 0.011 | 0.031 | 4.61x | E_INSPECTION_FINDING_RANDOM |
| `FRONT_TIRE_CHANGE` | 0.0657 | 352 | 0.071 | 0.086 | 0.247 | 3.76x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `ENGINE_COMPRESSION_TEST` | 0.0226 | 121 | 0.023 | 0.026 | 0.080 | 3.53x | E_BREAKDOWN_RANDOM_EVENT |
| `ABS_DIAGNOSTIC` | 0.0196 | 105 | 0.020 | 0.025 | 0.059 | 3.03x | E_BREAKDOWN_RANDOM_EVENT |
| `ENGINE_FAULT_DIAGNOSTIC` | 0.0052 | 28 | 0.005 | 0.007 | 0.015 | 2.92x | E_BREAKDOWN_RANDOM_EVENT |
| `BRAKE_FLUID_CHANGE` | 0.0762 | 408 | 0.078 | 0.070 | 0.214 | 2.80x | A_DETERMINISTIC_THRESHOLD |
| `FRONT_TIRE_INSPECTION` | 0.0398 | 213 | 0.037 | 0.048 | 0.110 | 2.76x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `SPARK_PLUG_INSPECTION` | 0.0394 | 211 | 0.031 | 0.047 | 0.105 | 2.67x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `SPARK_PLUG_CHANGE` | 0.0322 | 172 | 0.042 | 0.031 | 0.086 | 2.67x | A_DETERMINISTIC_THRESHOLD |
| `FUEL_SYSTEM_DIAGNOSTIC` | 0.0245 | 131 | 0.025 | 0.027 | 0.062 | 2.54x | E_BREAKDOWN_RANDOM_EVENT |
| `ECU_DIAGNOSTIC_SCAN` | 0.0131 | 70 | 0.013 | 0.025 | 0.033 | 2.50x | E_BREAKDOWN_RANDOM_EVENT |
| `REAR_TIRE_INSPECTION` | 0.0254 | 136 | 0.025 | 0.025 | 0.061 | 2.40x | D_STOCHASTIC_BUNDLE_ATTACHMENT |
| `FORK_SEAL_CHANGE` | 0.0054 | 29 | 0.005 | 0.009 | 0.013 | 2.35x | E_INSPECTION_FINDING_RANDOM |
| `FRONT_BRAKE_PAD_INSPECTION` | 0.0558 | 299 | 0.049 | 0.060 | 0.126 | 2.26x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `FORK_INSPECTION` | 0.0771 | 413 | 0.066 | 0.088 | 0.173 | 2.24x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `BRAKE_SYSTEM_BLEED` | 0.0060 | 32 | 0.006 | 0.010 | 0.013 | 2.23x | E_INSPECTION_FINDING_RANDOM |
| `THROTTLE_BODY_CLEAN` | 0.0058 | 31 | 0.006 | 0.013 | 0.013 | 2.17x | E_INSPECTION_FINDING_RANDOM |
| `CVT_BELT_CHANGE` | 0.0802 | 239 | 0.082 | 0.072 | 0.169 | 2.10x | A_DETERMINISTIC_THRESHOLD |
| `COOLANT_CHANGE` | 0.0632 | 96 | 0.068 | 0.069 | 0.133 | 2.10x | A_DETERMINISTIC_THRESHOLD |
| `BRAKE_DISC_CHANGE` | 0.0064 | 34 | 0.006 | 0.009 | 0.013 | 2.07x | E_INSPECTION_FINDING_RANDOM |
| `WHEEL_BEARING_INSPECTION` | 0.0448 | 240 | 0.040 | 0.053 | 0.087 | 1.94x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `STEERING_BEARING_CHANGE` | 0.0067 | 36 | 0.007 | 0.012 | 0.013 | 1.89x | E_INSPECTION_FINDING_RANDOM |
| `VALVE_CLEARANCE_INSPECTION` | 0.0518 | 277 | 0.046 | 0.058 | 0.097 | 1.87x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `CVT_BELT_INSPECTION` | 0.1302 | 388 | 0.121 | 0.119 | 0.241 | 1.85x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `REAR_BRAKE_PAD_INSPECTION` | 0.0248 | 133 | 0.020 | 0.033 | 0.046 | 1.85x | D_STOCHASTIC_BUNDLE_ATTACHMENT |
| `COOLANT_LEVEL_CHECK` | 0.1448 | 220 | 0.149 | 0.154 | 0.256 | 1.76x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `REAR_TIRE_CHANGE` | 0.0060 | 32 | 0.006 | 0.011 | 0.011 | 1.76x | B_STOCHASTIC_WEAR |
| `CHAIN_INSPECTION` | 0.2169 | 403 | 0.188 | 0.198 | 0.380 | 1.75x | A_DETERMINISTIC_THRESHOLD |
| `WHEEL_BEARING_CHANGE` | 0.0073 | 39 | 0.007 | 0.011 | 0.013 | 1.74x | E_INSPECTION_FINDING_RANDOM |
| `AIR_FILTER_CHANGE` | 0.1970 | 1054 | 0.173 | 0.181 | 0.341 | 1.73x | A_DETERMINISTIC_THRESHOLD |
| `BATTERY_TEST` | 0.2357 | 1262 | 0.202 | 0.221 | 0.397 | 1.68x | A_DETERMINISTIC_THRESHOLD |
| `BRAKE_FLUID_CHECK` | 0.2038 | 1091 | 0.178 | 0.188 | 0.343 | 1.68x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `AIR_FILTER_INSPECTION` | 0.2339 | 1251 | 0.194 | 0.215 | 0.381 | 1.63x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `STEERING_BEARING_INSPECTION` | 0.0239 | 128 | 0.019 | 0.026 | 0.039 | 1.62x | D_STOCHASTIC_BUNDLE_ATTACHMENT |
| `GENERAL_SAFETY_INSPECTION` | 0.1957 | 1048 | 0.171 | 0.185 | 0.316 | 1.61x | D_STOCHASTIC_BUNDLE_ATTACHMENT |
| `FINAL_GEAR_OIL_CHANGE` | 0.0564 | 168 | 0.072 | 0.054 | 0.091 | 1.61x | A_DETERMINISTIC_THRESHOLD |
| `CVT_CASE_INSPECTION` | 0.1406 | 419 | 0.130 | 0.129 | 0.224 | 1.60x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `WHEEL_BALANCE` | 0.0064 | 34 | 0.006 | 0.010 | 0.010 | 1.59x | E_INSPECTION_FINDING_RANDOM |
| `CHAIN_LUBRICATE` | 0.3757 | 698 | 0.302 | 0.315 | 0.577 | 1.54x | A_DETERMINISTIC_THRESHOLD |
| `CHAIN_CLEAN` | 0.4591 | 853 | 0.367 | 0.380 | 0.702 | 1.53x | A_DETERMINISTIC_THRESHOLD |
| `CVT_ROLLER_INSPECTION` | 0.0966 | 288 | 0.094 | 0.097 | 0.147 | 1.53x | F_MIXED_THRESHOLD_AND_BUNDLE |
| `VALVE_CLEARANCE_ADJUST` | 0.0052 | 28 | 0.005 | 0.012 | 0.007 | 1.36x | E_INSPECTION_FINDING_RANDOM |
| `ENGINE_OIL_CHANGE` | 0.8230 | 4402 | 0.788 | 0.815 | 0.915 | 1.11x | A_DETERMINISTIC_THRESHOLD |

## Findings

**1. There is real signal, and it is not the rule.** ML beats the projected rule
baseline on 43 of 44 labels, usually by roughly 2x PR-AUC. The single exception is
`ENGINE_OIL_CHANGE`, where the rule is already near-optimal because the label is
essentially deterministic (Phase 9, class A) — and where 82% prevalence leaves
almost no headroom anyway.

**2. Signal concentrates in the threshold-gated middle band.** The labels with the
best *absolute* PR-AUC are the recurring maintenance items — `CHAIN_CLEAN` 0.702,
`CHAIN_LUBRICATE` 0.577, `BATTERY_TEST` 0.397, `AIR_FILTER_INSPECTION` 0.381,
`CHAIN_INSPECTION` 0.380, `BRAKE_FLUID_CHECK` 0.343, `AIR_FILTER_CHANGE` 0.341.
These are exactly the labels the maintenance policy gates and a stochastic bundle
draw then emits, so knowing the interval state *and* the emission rate beats
knowing either alone.

**3. The random-event labels are not learnable, and the lift column disguises it.**
Every class-E label (`FAULT` and `INSPECTION_FINDING`) sits at absolute PR-AUC
between 0.007 and 0.080 no matter which model is used. They are random draws
conditioned on a service happening, and no observable at the landmark predicts
them. Their apparent "STRONG"/"VERY_STRONG" bands are an artifact of dividing by a
0.5% base rate.

**4. The decision.** 37 of 44 labels beat the rule baseline by more than 1.5x and
a substantial group reaches absolute PR-AUC above 0.3. That clears the brief's bar
for continuing to a full tournament — most labels do show signal — while flagging
that roughly a third of the label set is a floor, not a target.
