# V3 Phases 15, 16, 21 — Thresholds, Calibration and Champion Freeze

All decisions on this page were made on **VALIDATION only**, and every artifact was
written to disk **before** TEST was touched.

Artifacts: `ridebase-ml/models/v3_research/`.

## Champion selection (Phase 21)

The selection rule was fixed in `SELECTION_CRITERIA` before the tournament ran:

1. leakage gate PASS (a gate, not a score)
2. mAP must beat the projected rule baseline (0.0900)
3. mAP → 4. micro PR-AUC → 5. micro F1 → 6. P@3 → 7. simplicity

**Champion: `catboost`** — leads on both mAP (0.1699) and micro PR-AUC
(0.5823), the primary criterion and its first tie-break. All 9 ML families cleared
the rule-baseline gate.

`lightgbm_balanced` posts the best micro F1 in the tournament (0.4593) but is
eliminated at step 3, and its ranking metrics are materially worse (micro PR-AUC
0.4917 vs 0.5823). Had the criteria been ordered micro-F1-first it would have won
on a metric that misrepresents the product. Fixing the order in advance is what
prevented that.

## Fit / calibration split

To keep calibration honest the champion is fitted on the **first 80% of TRAIN by
landmark date** (22,552 rows) and calibrated on the **most recent 20%**
(5,639 rows). The split is temporal, not random: a calibrator fitted on
rows interleaved with the fitting rows sees the same motorcycles in the same months
and reports optimistic reliability. The cost is that the frozen champion is trained
on 80% of the data it could have used — an accepted, documented trade.

## Phase 15 — Threshold policy

Thresholds are **not** 0.5. Four policies were evaluated on VALIDATION.

Criterion, fixed before TEST: **maximise mean(micro F1, macro F1) subject to
predicted tasks per service ≤ 1.5× actual**.

| policy | micro F1 | macro F1 | mean | tasks predicted/service | ratio vs actual (3.30) | outcome |
|---|---|---|---|---|---|---|
| `global` | 0.5279 | 0.1264 | 0.3272 | 3.75 | 1.14 | **selected** |
| `per_label` | 0.3954 | 0.2201 | 0.3077 | 9.77 | 2.96 | rejected: predicts too many tasks |
| `precision_floor@0.3` | 0.3917 | 0.1762 | 0.2839 | 8.68 | 2.63 | rejected: predicts too many tasks |
| `precision_floor@0.5` | 0.3507 | 0.1402 | 0.2455 | 6.20 | 1.88 | rejected: predicts too many tasks |

**Why the count guard exists.** Per-label F1 maximisation is individually optimal
and collectively useless: for a 0.6%-prevalence label the F1-optimal threshold sits
near zero, and summed over 44 labels it predicts **9.77 tasks per service against an
actual 3.30**. A workshop handed ten predicted tasks when three will happen has been
given noise. The `precision_floor` policies from the brief were also tried, at 0.3
and 0.5; they fail the same way, because for the rare labels the model cannot reach
that precision at *any* threshold and falls back to the F1 optimum.

**Selected: a single global threshold of 0.31.** It predicts 3.75 tasks per
service — realistic — and wins the balanced criterion outright.

**The honest cost:** macro F1 falls to 0.1264. The single threshold
under-serves rare labels, whose binary flag rarely fires. This is stated plainly in
the product contract: **rare labels should be consumed as probabilities and ranks,
not as binary flags.** Critically, the ranked list — the actual product surface — is
threshold-independent: P@3 is **0.5006 under every policy in the table**.

## Phase 16 — Probability calibration

Fitted on the held-out calibration fold; the method is chosen **per label** on
VALIDATION by lowest Brier, rejecting any method that costs more than 0.01 PR-AUC.
Calibration must not buy reliability by wrecking ranking.

Labels with fewer than 50 positives in the calibration fold are left
**uncalibrated** — isotonic regression on 20 positives is a step function that is
confidently wrong.

| method | labels |
|---|---|
| none (insufficient support or no improvement) | 28 |
| isotonic | 14 |
| sigmoid / Platt | 2 |

Calibrated labels and their VALIDATION expected calibration error:

| label | calibration positives | method | ECE |
|---|---|---|---|
| `ENGINE_OIL_CHANGE` | 4947 | `isotonic` | 0.0201 |
| `AIR_FILTER_INSPECTION` | 1747 | `isotonic` | 0.0266 |
| `BRAKE_FLUID_CHECK` | 1529 | `isotonic` | 0.0212 |
| `CHAIN_CLEAN` | 1124 | `sigmoid` | 0.0432 |
| `CHAIN_INSPECTION` | 560 | `isotonic` | 0.0170 |
| `CVT_BELT_INSPECTION` | 543 | `isotonic` | 0.0150 |
| `CVT_CASE_INSPECTION` | 529 | `isotonic` | 0.0090 |
| `FRONT_BRAKE_PAD_INSPECTION` | 409 | `isotonic` | 0.0039 |
| `CVT_ROLLER_INSPECTION` | 383 | `isotonic` | 0.0153 |
| `COOLANT_LEVEL_CHECK` | 249 | `isotonic` | 0.0240 |
| `FINAL_GEAR_OIL_CHANGE` | 253 | `isotonic` | 0.0147 |
| `SPARK_PLUG_CHANGE` | 255 | `isotonic` | 0.0023 |
| `REAR_BRAKE_PAD_INSPECTION` | 131 | `isotonic` | 0.0052 |
| `FUEL_SYSTEM_DIAGNOSTIC` | 111 | `sigmoid` | 0.0048 |
| `ENGINE_COMPRESSION_TEST` | 95 | `isotonic` | 0.0017 |
| `ECU_DIAGNOSTIC_SCAN` | 80 | `isotonic` | 0.0005 |

Worst ECE overall (all labels, calibrated or not):

| label | ECE |
|---|---|
| `CHAIN_CLEAN` | 0.0432 |
| `CHAIN_LUBRICATE` | 0.0424 |
| `BATTERY_TEST` | 0.0332 |
| `GENERAL_SAFETY_INSPECTION` | 0.0306 |
| `FRONT_TIRE_CHANGE` | 0.0301 |
| `AIR_FILTER_CHANGE` | 0.0285 |
| `AIR_FILTER_INSPECTION` | 0.0266 |
| `COOLANT_LEVEL_CHECK` | 0.0240 |

Full per-label reliability tables are in `models/v3_research/calibration_report.json`.
Probabilities remain strictly label-specific — no cross-label normalisation is
applied at any point.

## Frozen VALIDATION performance

| metric | value |
|---|---|
| micro_f1 | 0.5279 |
| macro_f1 | 0.1264 |
| weighted_f1 | 0.4505 |
| micro_precision | 0.4965 |
| micro_recall | 0.5635 |
| hamming_loss | 0.0756 |
| subset_accuracy | 0.1496 |
| micro_pr_auc | 0.5737 |
| macro_pr_auc | 0.1627 |
| mean_average_precision | 0.1627 |
| precision_at_1 | 0.8315 |
| recall_at_1 | 0.3817 |
| precision_at_3 | 0.5006 |
| recall_at_3 | 0.5586 |
| precision_at_5 | 0.3922 |
| recall_at_5 | 0.6558 |

## What was frozen

| artifact | contents |
|---|---|
| `champion_model.joblib` | fitted catboost binary-relevance ensemble (44 per-label models + shared preprocessor) |
| `calibrator.joblib` | per-label calibrators with per-label method selection |
| `thresholds.json` | policy, criterion, chosen thresholds, and all rejected candidates |
| `feature_list.json` | the 277-column feature contract and its block structure |
| `label_list.json` | the 44 frozen labels and their support classes |
| `selection_before_test.json` | selection criteria, eligible families, VALIDATION metrics |
| `artifact_manifest.json` | dataset manifest, seed, split sizes, policies, `deployed: false` |

Seed: `20260907`. Landmark strategy: `random_one`. Source world: `v1_4`.

TEST was first read only after all of the above existed on disk.
