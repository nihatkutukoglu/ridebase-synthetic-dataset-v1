# V3 Phase 22 — Frozen TEST Evaluation

**TEST was evaluated exactly once**, after the champion, its calibrators and its
thresholds were written to disk. Nothing was changed afterwards.

Provenance: `models/v3_research/test_evaluation.json` records
`thresholds_frozen_before_test: true` and
`model_changed_after_seeing_test: false`.

Data: [`22_test_per_label.csv`](22_test_per_label.csv),
[`22_test_unseen_per_label.csv`](22_test_unseen_per_label.csv).

## Headline

| Metric | VALIDATION | TEST | Unseen-motorcycle TEST |
|---|---|---|---|
| Micro F1 | 0.5279 | 0.5192 | 0.4931 |
| Macro F1 | 0.1264 | 0.1107 | 0.0958 |
| Weighted F1 | 0.4505 | 0.4647 | 0.4497 |
| mAP | 0.1627 | 0.1330 | 0.1282 |
| Micro PR-AUC | 0.5737 | 0.5611 | 0.5442 |
| P@1 | 0.8315 | 0.8014 | 0.8035 |
| P@3 | 0.5006 | 0.3994 | 0.3855 |
| R@3 | 0.5586 | 0.6799 | 0.6967 |
| P@5 | 0.3922 | 0.2912 | 0.2713 |
| R@5 | 0.6558 | 0.7394 | 0.7443 |
| Hamming loss | 0.0756 | 0.0575 | 0.0588 |
| Subset accuracy (secondary) | 0.1496 | 0.2983 | 0.2951 |

TEST rows: **44** labels over 5,906 landmarks.
Unseen-motorcycle TEST rows: **871**.

## Reading the result

**Micro F1 and micro PR-AUC hold up.** 0.5279 → 0.5192 and 0.5737 → 0.5611. The
model's behaviour on the high-prevalence labels that dominate a work order is
stable across a six-month temporal gap.

**mAP degrades meaningfully**, 0.1627 → 0.1330 (−18%). Macro-averaged metrics are
dominated by the low-frequency labels, and TEST is both thinner and
distribution-shifted for exactly those: `FRONT_TIRE_CHANGE` and the fault-driven
diagnostics rise sharply in the 2026 window (see
[`07_split_audit.md`](07_split_audit.md)). This is the honest cost of a temporal
holdout and it is not explained away.

**P@3 falls (0.5006 → 0.3994) while R@3 rises (0.5586 → 0.6799).** These move in
opposite directions because TEST target services carry **fewer tasks** than
VALIDATION ones — subset accuracy doubles (0.1496 → 0.2983) and Hamming loss drops
(0.0756 → 0.0575) for the same reason. With fewer true positives per row, a fixed
top-3 list necessarily contains more misses (lower precision) while covering more of
the (smaller) truth set (higher recall). P@1 remains high at **0.8014**: the single
most likely task is right four times in five.

## Unseen-motorcycle generalisation (Phase 18)

871 TEST landmarks on motorcycles absent from TRAIN.

Degradation is **mild and uniform**: micro F1 0.5192 → 0.4931 (−5.0%), mAP 0.1330 →
0.1282 (−3.6%), P@1 0.8014 → 0.8035 (unchanged), R@3 0.6799 → 0.6967 (slightly
better). The model is not memorising individual motorcycles — which is expected,
since no identifier is a feature and hardware reaches the model only through
`brand`, `category`, `powertrain_type` and `policy_group`.

## Subgroup breakdown

Reported whether or not it flatters V3.

| subgroup | TEST rows | micro F1 | macro F1 | mAP | P@3 | R@3 |
|---|---|---|---|---|---|---|
| low_history (<= 5 prior task lines) | 700 | 0.4923 | 0.1003 | 0.1487 | 0.4341 | 0.6313 |
| high_history (> 20 prior task lines) | 2947 | 0.5449 | 0.1216 | 0.1430 | 0.3891 | 0.7187 |
| scooter | 3603 | 0.4962 | 0.0743 | 0.1094 | 0.3758 | 0.6746 |
| non_scooter | 2303 | 0.5491 | 0.1075 | 0.1294 | 0.4365 | 0.6882 |
| newer_motorcycle (<= 5y) | 2910 | 0.5198 | 0.1143 | 0.1435 | 0.4269 | 0.6708 |
| older_motorcycle (> 10y) | 106 | 0.4714 | 0.0812 | 0.2283 | 0.3172 | 0.7064 |
| unseen_motorcycle | 871 | 0.4931 | 0.0958 | 0.1282 | 0.3855 | 0.6967 |
| target_PERIODIC | 4662 | 0.5822 | 0.1137 | 0.1494 | 0.4568 | 0.7641 |
| target_not_PERIODIC | 1244 | 0.1525 | 0.0580 | 0.1066 | 0.1553 | 0.3215 |

The clearest degradation is on **non-`PERIODIC` target services** — repair,
breakdown and tyre visits. Their task content is driven by the random fault and
inspection-finding processes (Phase 9 class E), which no observable predicts.
Low-history motorcycles are also weaker, as expected when the task-history block has
nothing to say.

## Per-label TEST performance

`process` is the Phase-9 generating process. CORE / LOW is the frozen support class.

| label | class | support | prevalence | PR-AUC | ROC-AUC | precision | recall | F1 | Brier | process |
|---|---|---|---|---|---|---|---|---|---|---|
| `ENGINE_OIL_CHANGE` | CORE | 4626 | 0.7846 | 0.854 | 0.639 | 0.785 | 1.000 | 0.879 | 0.1666 | A rule |
| `BATTERY_TEST` | CORE | 780 | 0.1321 | 0.298 | 0.802 | 0.271 | 0.778 | 0.402 | 0.1081 | A rule |
| `AIR_FILTER_INSPECTION` | CORE | 774 | 0.1313 | 0.289 | 0.801 | 0.257 | 0.886 | 0.399 | 0.1060 | F mixed |
| `BRAKE_FLUID_CHECK` | CORE | 658 | 0.1114 | 0.251 | 0.794 | 0.245 | 0.622 | 0.351 | 0.0936 | F mixed |
| `AIR_FILTER_CHANGE` | CORE | 616 | 0.1045 | 0.265 | 0.793 | 0.243 | 0.487 | 0.325 | 0.0907 | A rule |
| `GENERAL_SAFETY_INSPECTION` | CORE | 611 | 0.1035 | 0.244 | 0.794 | 0.248 | 0.432 | 0.315 | 0.0896 | D bundle |
| `CHAIN_CLEAN` | CORE | 510 | 0.2519 | 0.603 | 0.860 | 0.468 | 0.971 | 0.631 | 0.1446 | A rule |
| `FRONT_TIRE_CHANGE` | LOW | 467 | 0.0791 | 0.198 | 0.750 | 0.248 | 0.135 | 0.175 | 0.0717 | F mixed |
| `CHAIN_LUBRICATE` | CORE | 433 | 0.2138 | 0.487 | 0.839 | 0.394 | 0.982 | 0.562 | 0.1407 | A rule |
| `BRAKE_FLUID_CHANGE` | CORE | 255 | 0.0432 | 0.229 | 0.851 | 0.397 | 0.090 | 0.147 | 0.0383 | A rule |
| `CVT_CASE_INSPECTION` | CORE | 254 | 0.0756 | 0.159 | 0.761 | 0.000 | 0.000 | 0.000 | 0.0677 | F mixed |
| `CHAIN_INSPECTION` | CORE | 249 | 0.1230 | 0.303 | 0.808 | 0.309 | 0.534 | 0.392 | 0.0969 | A rule |
| `CVT_BELT_INSPECTION` | CORE | 245 | 0.0730 | 0.174 | 0.779 | 0.222 | 0.033 | 0.057 | 0.0655 | F mixed |
| `FORK_INSPECTION` | CORE | 219 | 0.0371 | 0.116 | 0.794 | 0.203 | 0.069 | 0.102 | 0.0358 | F mixed |
| `FUEL_SYSTEM_DIAGNOSTIC` | LOW | 199 | 0.0338 | 0.053 | 0.565 | 0.000 | 0.000 | 0.000 | 0.0328 | E random fault |
| `ABS_DIAGNOSTIC` | LOW | 184 | 0.0312 | 0.041 | 0.576 | 0.000 | 0.000 | 0.000 | 0.0309 | E random fault |
| `VALVE_CLEARANCE_INSPECTION` | CORE | 183 | 0.0310 | 0.091 | 0.792 | 0.286 | 0.011 | 0.021 | 0.0294 | F mixed |
| `CVT_ROLLER_INSPECTION` | CORE | 182 | 0.0542 | 0.108 | 0.754 | 0.000 | 0.000 | 0.000 | 0.0504 | F mixed |
| `ENGINE_COMPRESSION_TEST` | LOW | 180 | 0.0305 | 0.044 | 0.615 | 0.000 | 0.000 | 0.000 | 0.0298 | E random fault |
| `FRONT_BRAKE_PAD_INSPECTION` | CORE | 176 | 0.0298 | 0.101 | 0.808 | 0.286 | 0.011 | 0.022 | 0.0280 | F mixed |
| `WHEEL_BEARING_INSPECTION` | CORE | 154 | 0.0261 | 0.067 | 0.781 | 0.000 | 0.000 | 0.000 | 0.0251 | F mixed |
| `COOLANT_LEVEL_CHECK` | CORE | 145 | 0.0831 | 0.144 | 0.725 | 0.000 | 0.000 | 0.000 | 0.0785 | F mixed |
| `CVT_BELT_CHANGE` | CORE | 136 | 0.0405 | 0.136 | 0.806 | 0.222 | 0.015 | 0.028 | 0.0376 | A rule |
| `FRONT_TIRE_INSPECTION` | CORE | 123 | 0.0208 | 0.081 | 0.789 | 0.200 | 0.016 | 0.030 | 0.0202 | F mixed |
| `SPARK_PLUG_INSPECTION` | CORE | 116 | 0.0197 | 0.096 | 0.835 | 0.222 | 0.017 | 0.032 | 0.0188 | F mixed |
| `FINAL_GEAR_OIL_CHANGE` | CORE | 112 | 0.0334 | 0.068 | 0.728 | 0.000 | 0.000 | 0.000 | 0.0323 | A rule |
| `SPARK_PLUG_CHANGE` | CORE | 83 | 0.0141 | 0.062 | 0.835 | 0.000 | 0.000 | 0.000 | 0.0136 | A rule |
| `REAR_TIRE_INSPECTION` | CORE | 75 | 0.0127 | 0.043 | 0.791 | 0.000 | 0.000 | 0.000 | 0.0125 | D bundle |
| `REAR_BRAKE_PAD_INSPECTION` | CORE | 69 | 0.0117 | 0.032 | 0.780 | 0.000 | 0.000 | 0.000 | 0.0117 | D bundle |
| `COOLANT_CHANGE` | LOW | 57 | 0.0327 | 0.058 | 0.691 | 0.000 | 0.000 | 0.000 | 0.0334 | A rule |
| `STEERING_BEARING_INSPECTION` | LOW | 55 | 0.0093 | 0.023 | 0.772 | 0.000 | 0.000 | 0.000 | 0.0093 | D bundle |
| `ECU_DIAGNOSTIC_SCAN` | LOW | 41 | 0.0069 | 0.011 | 0.671 | 0.000 | 0.000 | 0.000 | 0.0069 | E random fault |
| `BRAKE_SYSTEM_BLEED` | LOW | 29 | 0.0049 | 0.007 | 0.614 | 0.000 | 0.000 | 0.000 | 0.0049 | E random finding |
| `ENGINE_FAULT_DIAGNOSTIC` | LOW | 28 | 0.0047 | 0.023 | 0.766 | 0.000 | 0.000 | 0.000 | 0.0047 | E random fault |
| `BRAKE_DISC_CHANGE` | LOW | 27 | 0.0046 | 0.012 | 0.695 | 0.000 | 0.000 | 0.000 | 0.0046 | E random finding |
| `WHEEL_BALANCE` | LOW | 26 | 0.0044 | 0.020 | 0.726 | 0.000 | 0.000 | 0.000 | 0.0044 | E random finding |
| `WHEEL_BEARING_CHANGE` | LOW | 26 | 0.0044 | 0.008 | 0.696 | 0.000 | 0.000 | 0.000 | 0.0044 | E random finding |
| `VALVE_CLEARANCE_ADJUST` | LOW | 21 | 0.0036 | 0.008 | 0.671 | 0.000 | 0.000 | 0.000 | 0.0036 | E random finding |
| `REAR_TIRE_CHANGE` | LOW | 21 | 0.0036 | 0.011 | 0.682 | 0.000 | 0.000 | 0.000 | 0.0035 | B wear |
| `FUEL_INJECTOR_CLEAN` | LOW | 21 | 0.0036 | 0.004 | 0.575 | 0.000 | 0.000 | 0.000 | 0.0036 | E random finding |
| `THROTTLE_BODY_CLEAN` | LOW | 20 | 0.0034 | 0.016 | 0.761 | 0.000 | 0.000 | 0.000 | 0.0034 | E random finding |
| `STEERING_BEARING_CHANGE` | LOW | 17 | 0.0029 | 0.007 | 0.686 | 0.000 | 0.000 | 0.000 | 0.0029 | E random finding |
| `BATTERY_CHANGE` | LOW | 17 | 0.0029 | 0.004 | 0.571 | 0.000 | 0.000 | 0.000 | 0.0029 | E random finding |
| `FORK_SEAL_CHANGE` | LOW | 16 | 0.0027 | 0.004 | 0.666 | 0.000 | 0.000 | 0.000 | 0.0027 | E random finding |

## Stated limitation

**12 of 44 labels have fewer than 30 TEST positives.** Their metrics carry
wide uncertainty and must not be read as precise estimates. They were retained
because they cleared the frozen pre-TEST support gate; removing them after seeing
TEST support would be selection against TEST.

The labels with F1 of 0.000 are not a bug: under the single global threshold
(Phase 15) the rare labels' calibrated probabilities rarely cross 0.31, so their
binary flag almost never fires. Their **PR-AUC and ROC-AUC are still informative**,
which is exactly why the product contract says rare labels must be consumed as
probabilities and ranks rather than as binary predictions.
