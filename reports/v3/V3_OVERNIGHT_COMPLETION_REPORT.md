# RideBase V3 Overnight Completion Report

Multi-label next-service task prediction. **Offline research challenger.**
Session date 2026-09-07. Interpreter `/usr/bin/python3` (3.9.6).

---

## 1. Starting State

| item | value |
|---|---|
| start HEAD | `b25f3b7b1f870c995b1e133a76230537d83d7365` |
| branch | `main` (in sync with `origin/main`) |
| working tree at start | clean |
| source world chosen | RideBase Synthetic Dataset **v1.4** — the world the frozen V2.1 production champion is trained and served on |

V2.1 frozen hashes were recorded before any work
([`01_frozen_hashes.json`](01_frozen_hashes.json), 21 artifacts) and re-verified at
the end — see §17. The recorded `v2_1_modeling_table.parquet` hash matched the value
inside V2.1's own `data_freeze_manifest.json`, confirming the production freeze was
internally consistent at session start.

## 2. Target Contract

**Question:** at the next completed service, which maintenance tasks will be performed?

| element | definition |
|---|---|
| **Landmark** | end-of-month observation point, inherited unchanged from the frozen V2.1 dynamic-landmark grid (256,841 landmarks, 8,907 motorcycles, 2021-01 → 2026-07) |
| **Target service** | the first service the motorcycle arrives at strictly after the landmark. Every `services.csv` row in v1.4 has `status = DELIVERED`, so arrival implies completion (median turnaround 1.3 h, 90.7% same calendar day) |
| **Target labels** | task codes on that service with `service_tasks.status = COMPLETED` |
| **Censored landmarks** | **excluded**, not labelled empty — the target is unknown, not absent |

**Excluded event types:** `CANCELLED` (2,552), `NO_SHOW` (2,052) and `RESCHEDULED`
(844) appointments never produce a service row and therefore cannot be a target.
`DECLINED` task lines (1,415) are **negative** — recommended but not performed.

All four service types (`PERIODIC`, `REPAIR`, `TIRE`, `BREAKDOWN`) are eligible
targets: the product question is "at the next visit", not "at the next periodic
visit", and conditioning on visit type would condition on something unknown at the
landmark.

This deliberately differs from the generator's own
`ml_next_task_targets.parquet`, which counts declined tasks as positive and uses a
single landmark per service event.

Full contract: [`docs/v3_target_contract.md`](../../docs/v3_target_contract.md),
[`config/v3_target_contract.json`](../../config/v3_target_contract.json).

**Unresolved semantics, marked not guessed:** `OIL_FILTER_CHANGE` is decoupled from
`ENGINE_OIL_CHANGE` in this generator (40 vs 34,762 positives) though the V3 brief's
example output pairs them; `is_warranty` is perfectly collinear with `is_breakdown`
so warranty has no independent meaning; there is no pure-inspection service type.

## 3. Label Inventory

93 task codes are taxonomy-eligible (`can_be_next_service_target = 1`); 74 ever
occur. Support is measured over **applicable** rows only.

| class | count |
|---|---|
| A_CORE | 25 |
| B_LOW_FREQUENCY | 19 |
| C_TOO_RARE_FOR_MODELING (excluded) | 30 |
| **modelled in V3.0** | **44** |

Frozen gate, decided on **TRAIN+VALIDATION support only**: ≥1,000 applicable rows,
≥200 pre-TEST positives, ≥25 validation positives, ≥100 motorcycles, ≥4 years.
**No merges and no OTHER bucket** — every `task_code` joins exactly to a taxonomy
row, so there are no aliases, and merging unrelated tasks would be metric inflation.

Highest prevalence: `ENGINE_OIL_CHANGE` 0.882, `BATTERY_TEST` 0.302,
`AIR_FILTER_INSPECTION` 0.301, `BRAKE_FLUID_CHECK` 0.265, `AIR_FILTER_CHANGE` 0.250.
Details: [`03_label_inventory.md`](03_label_inventory.md).

## 4. Dataset

| item | value |
|---|---|
| rows (landmarks) | **39,451** |
| motorcycles | 7,276 |
| target services | 39,451 (exactly one landmark each) |
| features | 277 |
| labels | 44 |
| landmark date range | 2021-02-28 → 2026-07-31 |
| target service range | 2021-03-24 → 2026-08-01 |
| TRAIN / VALIDATION / TEST | 28,191 / 5,354 / 5,906 |
| unseen-motorcycle TEST | 871 |
| seed | 20260907 |
| lead time (landmark → target) | median 39 d, mean 61.3 d |

**Landmark strategy: `random_one`** — exactly one landmark per (motorcycle, target
service), seeded. Five strategies were built and modelled. `latest` (the landmark
immediately before the service) posts the best micro F1 in the table, 0.4392 vs
0.4215, purely because 98.1% of its landmarks sit within 30 days of the answer — the
trap the brief warns about, quantified rather than assumed. `all` leaves 4.0
landmarks per target service (max 31) and scores *worst*. See
[`06_landmark_design.md`](06_landmark_design.md).

**Split:** temporal, inherited from V2.1, plus a **target-bleed purge** — a TRAIN
landmark whose target service falls in the validation era is removed (11.5% of
TRAIN, 46.0% of VALIDATION). Purging the pool *before* sampling recovers VALIDATION
from 3,325 to 5,354 rows. A useful side effect: no target service can then be
reached from two splits. See [`07_split_audit.md`](07_split_audit.md).

## 5. Leakage Audit — **PASS**

All history flows through one backward `merge_asof`, so a post-landmark row cannot
be selected. Three checks ([`08_leakage_audit.md`](08_leakage_audit.md)):

| check | result |
|---|---|
| name / identifier screen (277 columns, 26 forbidden tokens) | **PASS** — 0 violations, 3 names allowlisted with written justification |
| future-injection invariance (4,000 landmarks, 16,000 fabricated events at +1/+7/+30/+120 d) | **PASS** — feature matrix byte-identical, digests equal |
| T-1 / T / T+1 boundary | **PASS** — 4000/4000 change at T-1 and T, **0/4000** at T+1 |

No identifier, target field, censoring field, split indicator, or generator latent
variable reaches the model; they live in a separate `meta` frame.

**Two defects this phase caught.** (1) The injection test initially reported 195
changed columns — a *test* bug: with several landmarks per motorcycle, an event
injected after the earlier one is legitimately in the later one's past. Fixed by
sampling one landmark per motorcycle. (2) The boundary test then reported 3,986/4,000
instead of 4,000 — a **real non-determinism bug in the feature builder**: when a
motorcycle had two task lines on the same date, `merge_asof` returned whichever
sorted last and the occurrence index depended on row arrival order. Fixed with an
explicit sort key and stable sorts; now covered by a regression test.

## 6. Generator Rule Audit

**The core generator is not in this repository** — `services.csv` and
`service_tasks.csv` come from a `MAINTENANCE_EVENT_SIM_V1` run whose code is absent
(a repo-wide search for `INSPECTION_BUNDLE` finds nothing). The audit is therefore
**empirical**, inferred from `trigger_reason` and `is_policy_due`. That is weaker
than reading source and is stated as such.

| generating process | labels | mean rule PR-AUC | mean ML PR-AUC |
|---|---|---|---|
| A — deterministic threshold | 11 | 0.2147 | 0.3640 |
| F — mixed threshold + bundle | 13 | 0.0928 | 0.1951 |
| D — stochastic bundle attachment | 4 | 0.0588 | 0.1153 |
| B — stochastic wear | 1 | 0.0061 | 0.0105 |
| E — random breakdown/fault | 5 | 0.0170 | 0.0498 |
| E — random inspection finding | 10 | 0.0067 | 0.0164 |

**This is not generator-rule replication.** Both rule baselines score *below* the
prevalence-only baseline on every ranking metric. The policy table is a **gate**,
not the emitter: it decides which tasks are *allowed* onto a work order, and a
stochastic bundle draw decides which allowed ones appear. `FORK_INSPECTION` carries
the same 6,000 km / 12-month policy as `ENGINE_OIL_CHANGE` but appears on 7.7% of
services against oil's 88%, so its due ratio is perpetually >1 while the truth stays
low.

The one genuinely deterministic label, `ENGINE_OIL_CHANGE`, is also the one where ML
adds least (PR-AUC 0.915 vs prevalence 0.823, lift 1.11×). Roughly a third of the
label set (15 class-E labels) is random-event driven and **not learnable from any
observable**. See [`09_generator_rule_audit.md`](09_generator_rule_audit.md).

## 7. Baselines (VALIDATION)

| Model | Micro F1 | Macro F1 | mAP | P@3 | R@3 |
|---|---|---|---|---|---|
| `baseline0_prevalence` | 0.2302 | 0.1501 | 0.0991 | 0.4377 | 0.4769 |
| `baseline2_recurrence` | 0.2977 | 0.1687 | 0.0966 | 0.4534 | 0.4895 |
| `baseline1b_rule_projected` | 0.2581 | 0.1518 | 0.0900 | 0.1318 | 0.0818 |
| `baseline1_rule` | 0.2591 | 0.1521 | 0.0898 | 0.1245 | 0.0775 |

## 8. Model Tournament (VALIDATION)

| Model | Micro F1 | Macro F1 | mAP | Micro PR-AUC | P@3 | R@3 |
|---|---|---|---|---|---|---|
| `catboost` | 0.4178 | 0.2276 | 0.1699 | 0.5823 | 0.5036 | 0.5654 |
| `extra_trees` | 0.4012 | 0.2231 | 0.1670 | 0.5786 | 0.5021 | 0.5512 |
| `random_forest` | 0.3951 | 0.2231 | 0.1666 | 0.5815 | 0.5059 | 0.5654 |
| `xgboost_balanced` | 0.4193 | 0.2260 | 0.1651 | 0.4036 | 0.4200 | 0.4972 |
| `xgboost` | 0.4215 | 0.2234 | 0.1650 | 0.5771 | 0.5008 | 0.5690 |
| `lightgbm` | 0.4425 | 0.2111 | 0.1644 | 0.5707 | 0.4904 | 0.5474 |
| `lightgbm_balanced` | 0.4593 | 0.2201 | 0.1635 | 0.4917 | 0.4585 | 0.5332 |
| `logreg` | 0.4105 | 0.2221 | 0.1600 | 0.5694 | 0.4986 | 0.5659 |
| `logreg_balanced` | 0.3930 | 0.2202 | 0.1586 | 0.1494 | 0.1381 | 0.1932 |

Classifier Chains (XGBoost base, prevalence-ordered) were built and measured:
mAP 0.1567, micro PR-AUC 0.5361, P@3 0.4759 — **worse than plain binary relevance**,
as [`17_label_cooccurrence.md`](17_label_cooccurrence.md) predicted, because the
dominant label dependence is already carried by shared maintenance-interval features.

**Class imbalance is the most consequential finding.** Every family was run
rebalanced and not. Rebalancing leaves per-label separation unchanged (mAP moves
<0.002) but rescales each label's probability by its own positive rate, destroying
cross-label comparability: `logreg_balanced` collapses to P@3 = 0.138, *below* the
constant-prevalence baseline's 0.438. All champion candidates are **unweighted**.
SMOTE was not used — interpolating temporal multi-label rows invents maintenance
histories and risks crossing the time boundary.

## 9. Calibration

Fitted on the **most recent 20% of TRAIN by landmark date** (temporal, not random),
method chosen per label on VALIDATION by lowest Brier, rejecting any method costing
>0.01 PR-AUC. Labels with <50 calibration positives are left uncalibrated.

| method | labels |
|---|---|
| none | 28 |
| isotonic | 14 |
| sigmoid | 2 |

Per-label Brier and reliability tables: `models/v3_research/calibration_report.json`
and [`21_champion.md`](21_champion.md). Probabilities remain strictly label-specific;
no cross-label normalisation is applied.

## 10. Champion

| item | value |
|---|---|
| model | **catboost**, binary relevance (44 per-label models + shared preprocessor) |
| feature set | 277 columns — F0 base 37, F1 policy 88, F2 history 47, F3 recency 88, F4 behaviour 17 |
| labels | 44 |
| threshold policy | **global**, single threshold 0.31 |
| fit / calibration rows | 22,552 / 5,639 |
| seed | 20260907 |

Selected on VALIDATION by a rule fixed **before** the tournament: leakage gate →
beat rule baseline → mAP → micro PR-AUC → micro F1 → P@3 → simplicity. CatBoost
leads mAP (0.1699) *and* micro PR-AUC (0.5823). `lightgbm_balanced` has the best
micro F1 (0.4593) but is eliminated at the mAP step — had the order been micro-F1
first it would have won on a metric that misrepresents the product.

**Threshold honesty.** Per-label F1 maximisation predicts **9.77 tasks per service
against an actual 3.30** — individually optimal, collectively useless. The frozen
criterion (max mean(micro F1, macro F1) subject to predicted count ≤1.5× actual)
selects a single global threshold predicting 3.75. The cost is macro F1 falling to
0.1264: **rare labels must be consumed as probabilities and ranks, not binary
flags.** The ranked list itself is threshold-independent — P@3 is 0.5006 under
every policy tested.

## 11. Frozen TEST

Evaluated **once**, after all artifacts were on disk.

| Metric | TEST | Unseen-motorcycle TEST |
|---|---|---|
| Micro F1 | 0.5192 | 0.4931 |
| Macro F1 | 0.1107 | 0.0958 |
| mAP | 0.1330 | 0.1282 |
| Micro PR-AUC | 0.5611 | 0.5442 |
| P@1 | 0.8014 | 0.8035 |
| P@3 | 0.3994 | 0.3855 |
| R@3 | 0.6799 | 0.6967 |
| Hamming loss | 0.0575 | 0.0588 |

VALIDATION → TEST: micro F1 0.5279 → 0.5192, micro PR-AUC 0.5737 → 0.5611,
mAP 0.1627 → 0.1330.

Micro metrics hold; **mAP degrades 18%** because macro averaging is dominated by the
low-frequency labels, and TEST is both thinner and distribution-shifted for exactly
those. P@3 falls while R@3 rises because TEST target services carry fewer tasks
(subset accuracy doubles, Hamming loss drops). **P@1 stays at 0.80** — the single
most likely task is right four times in five.

**Unseen motorcycles degrade only mildly** (micro F1 −5.0%, mAP −3.6%, P@1
unchanged): no identifier is a feature, so there is nothing to memorise.

### Subgroups

| subgroup | rows | micro F1 | mAP | P@3 |
|---|---|---|---|---|
| low_history (<= 5 prior task lines) | 700 | 0.4923 | 0.1487 | 0.4341 |
| high_history (> 20 prior task lines) | 2947 | 0.5449 | 0.1430 | 0.3891 |
| scooter | 3603 | 0.4962 | 0.1094 | 0.3758 |
| non_scooter | 2303 | 0.5491 | 0.1294 | 0.4365 |
| newer_motorcycle (<= 5y) | 2910 | 0.5198 | 0.1435 | 0.4269 |
| older_motorcycle (> 10y) | 106 | 0.4714 | 0.2283 | 0.3172 |
| unseen_motorcycle | 871 | 0.4931 | 0.1282 | 0.3855 |
| target_PERIODIC | 4662 | 0.5822 | 0.1494 | 0.4568 |
| target_not_PERIODIC | 1244 | 0.1525 | 0.1066 | 0.1553 |

Weakest: **non-`PERIODIC` target services**, whose content is driven by the
unlearnable random-event processes, and low-history motorcycles.

## 12. Per-Label TEST Performance

| label | class | support | prevalence | PR-AUC | ROC-AUC | precision | recall | F1 | Brier |
|---|---|---|---|---|---|---|---|---|---|
| `ENGINE_OIL_CHANGE` | CORE | 4626 | 0.7846 | 0.854 | 0.639 | 0.785 | 1.000 | 0.879 | 0.1666 |
| `BATTERY_TEST` | CORE | 780 | 0.1321 | 0.298 | 0.802 | 0.271 | 0.778 | 0.402 | 0.1081 |
| `AIR_FILTER_INSPECTION` | CORE | 774 | 0.1313 | 0.289 | 0.801 | 0.257 | 0.886 | 0.399 | 0.1060 |
| `BRAKE_FLUID_CHECK` | CORE | 658 | 0.1114 | 0.251 | 0.794 | 0.245 | 0.622 | 0.351 | 0.0936 |
| `AIR_FILTER_CHANGE` | CORE | 616 | 0.1045 | 0.265 | 0.793 | 0.243 | 0.487 | 0.325 | 0.0907 |
| `GENERAL_SAFETY_INSPECTION` | CORE | 611 | 0.1035 | 0.244 | 0.794 | 0.248 | 0.432 | 0.315 | 0.0896 |
| `CHAIN_CLEAN` | CORE | 510 | 0.2519 | 0.603 | 0.860 | 0.468 | 0.971 | 0.631 | 0.1446 |
| `FRONT_TIRE_CHANGE` | LOW_FREQUENCY | 467 | 0.0791 | 0.198 | 0.750 | 0.248 | 0.135 | 0.175 | 0.0717 |
| `CHAIN_LUBRICATE` | CORE | 433 | 0.2138 | 0.487 | 0.839 | 0.394 | 0.982 | 0.562 | 0.1407 |
| `BRAKE_FLUID_CHANGE` | CORE | 255 | 0.0432 | 0.229 | 0.851 | 0.397 | 0.090 | 0.147 | 0.0383 |
| `CVT_CASE_INSPECTION` | CORE | 254 | 0.0756 | 0.159 | 0.761 | 0.000 | 0.000 | 0.000 | 0.0677 |
| `CHAIN_INSPECTION` | CORE | 249 | 0.1230 | 0.303 | 0.808 | 0.309 | 0.534 | 0.392 | 0.0969 |
| `CVT_BELT_INSPECTION` | CORE | 245 | 0.0730 | 0.174 | 0.779 | 0.222 | 0.033 | 0.057 | 0.0655 |
| `FORK_INSPECTION` | CORE | 219 | 0.0371 | 0.116 | 0.794 | 0.203 | 0.069 | 0.102 | 0.0358 |
| `FUEL_SYSTEM_DIAGNOSTIC` | LOW_FREQUENCY | 199 | 0.0338 | 0.053 | 0.565 | 0.000 | 0.000 | 0.000 | 0.0328 |
| `ABS_DIAGNOSTIC` | LOW_FREQUENCY | 184 | 0.0312 | 0.041 | 0.576 | 0.000 | 0.000 | 0.000 | 0.0309 |
| `VALVE_CLEARANCE_INSPECTION` | CORE | 183 | 0.0310 | 0.091 | 0.792 | 0.286 | 0.011 | 0.021 | 0.0294 |
| `CVT_ROLLER_INSPECTION` | CORE | 182 | 0.0542 | 0.108 | 0.754 | 0.000 | 0.000 | 0.000 | 0.0504 |
| `ENGINE_COMPRESSION_TEST` | LOW_FREQUENCY | 180 | 0.0305 | 0.044 | 0.615 | 0.000 | 0.000 | 0.000 | 0.0298 |
| `FRONT_BRAKE_PAD_INSPECTION` | CORE | 176 | 0.0298 | 0.101 | 0.808 | 0.286 | 0.011 | 0.022 | 0.0280 |
| `WHEEL_BEARING_INSPECTION` | CORE | 154 | 0.0261 | 0.067 | 0.781 | 0.000 | 0.000 | 0.000 | 0.0251 |
| `COOLANT_LEVEL_CHECK` | CORE | 145 | 0.0831 | 0.144 | 0.725 | 0.000 | 0.000 | 0.000 | 0.0785 |
| `CVT_BELT_CHANGE` | CORE | 136 | 0.0405 | 0.136 | 0.806 | 0.222 | 0.015 | 0.028 | 0.0376 |
| `FRONT_TIRE_INSPECTION` | CORE | 123 | 0.0208 | 0.081 | 0.789 | 0.200 | 0.016 | 0.030 | 0.0202 |
| `SPARK_PLUG_INSPECTION` | CORE | 116 | 0.0197 | 0.096 | 0.835 | 0.222 | 0.017 | 0.032 | 0.0188 |
| `FINAL_GEAR_OIL_CHANGE` | CORE | 112 | 0.0334 | 0.068 | 0.728 | 0.000 | 0.000 | 0.000 | 0.0323 |
| `SPARK_PLUG_CHANGE` | CORE | 83 | 0.0141 | 0.062 | 0.835 | 0.000 | 0.000 | 0.000 | 0.0136 |
| `REAR_TIRE_INSPECTION` | CORE | 75 | 0.0127 | 0.043 | 0.791 | 0.000 | 0.000 | 0.000 | 0.0125 |
| `REAR_BRAKE_PAD_INSPECTION` | CORE | 69 | 0.0117 | 0.032 | 0.780 | 0.000 | 0.000 | 0.000 | 0.0117 |
| `COOLANT_CHANGE` | LOW_FREQUENCY | 57 | 0.0327 | 0.058 | 0.691 | 0.000 | 0.000 | 0.000 | 0.0334 |
| `STEERING_BEARING_INSPECTION` | LOW_FREQUENCY | 55 | 0.0093 | 0.023 | 0.772 | 0.000 | 0.000 | 0.000 | 0.0093 |
| `ECU_DIAGNOSTIC_SCAN` | LOW_FREQUENCY | 41 | 0.0069 | 0.011 | 0.671 | 0.000 | 0.000 | 0.000 | 0.0069 |
| `BRAKE_SYSTEM_BLEED` | LOW_FREQUENCY | 29 | 0.0049 | 0.007 | 0.614 | 0.000 | 0.000 | 0.000 | 0.0049 |
| `ENGINE_FAULT_DIAGNOSTIC` | LOW_FREQUENCY | 28 | 0.0047 | 0.023 | 0.766 | 0.000 | 0.000 | 0.000 | 0.0047 |
| `BRAKE_DISC_CHANGE` | LOW_FREQUENCY | 27 | 0.0046 | 0.012 | 0.695 | 0.000 | 0.000 | 0.000 | 0.0046 |
| `WHEEL_BALANCE` | LOW_FREQUENCY | 26 | 0.0044 | 0.020 | 0.726 | 0.000 | 0.000 | 0.000 | 0.0044 |
| `WHEEL_BEARING_CHANGE` | LOW_FREQUENCY | 26 | 0.0044 | 0.008 | 0.696 | 0.000 | 0.000 | 0.000 | 0.0044 |
| `VALVE_CLEARANCE_ADJUST` | LOW_FREQUENCY | 21 | 0.0036 | 0.008 | 0.671 | 0.000 | 0.000 | 0.000 | 0.0036 |
| `REAR_TIRE_CHANGE` | LOW_FREQUENCY | 21 | 0.0036 | 0.011 | 0.682 | 0.000 | 0.000 | 0.000 | 0.0035 |
| `FUEL_INJECTOR_CLEAN` | LOW_FREQUENCY | 21 | 0.0036 | 0.004 | 0.575 | 0.000 | 0.000 | 0.000 | 0.0036 |
| `THROTTLE_BODY_CLEAN` | LOW_FREQUENCY | 20 | 0.0034 | 0.016 | 0.761 | 0.000 | 0.000 | 0.000 | 0.0034 |
| `STEERING_BEARING_CHANGE` | LOW_FREQUENCY | 17 | 0.0029 | 0.007 | 0.686 | 0.000 | 0.000 | 0.000 | 0.0029 |
| `BATTERY_CHANGE` | LOW_FREQUENCY | 17 | 0.0029 | 0.004 | 0.571 | 0.000 | 0.000 | 0.000 | 0.0029 |
| `FORK_SEAL_CHANGE` | LOW_FREQUENCY | 16 | 0.0027 | 0.004 | 0.666 | 0.000 | 0.000 | 0.000 | 0.0027 |

12 of 44 labels have fewer than 30 TEST positives; their metrics carry wide
uncertainty. F1 of 0.000 on rare labels is the global threshold never firing, not a
missing model — their PR-AUC and ROC-AUC remain informative.

## 13. Ablation

| feature set | n | Micro F1 | mAP | Micro PR-AUC | P@3 |
|---|---|---|---|---|---|
| `F0_basic` | 37 | 0.3939 | 0.1588 | 0.5608 | 0.4866 |
| `F1_plus_policy` | 125 | 0.4254 | 0.1647 | 0.5706 | 0.4962 |
| `F2_plus_task_history` | 172 | 0.4373 | 0.1665 | 0.5731 | 0.4957 |
| `F3_plus_task_recency` | 260 | 0.4260 | 0.1637 | 0.5702 | 0.4964 |
| `F4_plus_behavioural` | 277 | 0.4215 | 0.1650 | 0.5771 | 0.5008 |
| `task_history_only_no_policy` | 172 | 0.4136 | 0.1637 | 0.5696 | 0.4931 |

**F0 alone reaches 96% of the full model's mAP from 37 features.** Deterministic
policy state (F1) is the largest single addition. Per-task history (F2) adds little
and per-task recency (F3) *costs* mAP — a genuine negative result, reported rather
than buried: those 88 columns are largely redundant with the policy ratios computed
from them. Task history cannot substitute for policy state
([`19_history_depth_ablation.md`](19_history_depth_ablation.md)).

### Oracle research ceiling — **RESEARCH ORACLE, NOT DEPLOYABLE**

Giving the model perfect knowledge of the next visit's date, type and odometer:

| metric | observable | oracle | gap |
|---|---|---|---|
| mAP | 0.1650 | 0.2372 | +44% |
| micro PR-AUC | 0.5771 | 0.6431 | +11% |
| P@3 | 0.5008 | 0.5152 | +3% |

The gap is large on ranking, **small on the top-K surface the product actually
shows**. The missing observable is next-visit timing — which is what V2.1 estimates.
**V3 does not and must not consume V2.1's output**; that would couple two
deliberately separate surfaces and propagate V2.1's calibration error into V3's
displayed percentages. This is a research observation, not a design recommendation.
Even the oracle reaches only mAP 0.2372 — the residual is the irreducible
stochastic layer from Phase 9.

## 14. Product Behaviour

11 realistic scenario sweeps, each a **filter over real landmarks** rather than a
hand-built row. **All invariants pass on every scenario**: probabilities in [0,1],
no NaN, deterministic on repeat, ranking stable, inapplicable tasks forced to 0.
Predicted task counts track actual counts (ratio ~1.15–1.4). No expected probability
is hardcoded anywhere ([`23_product_behavior.md`](23_product_behavior.md)).

### Rule vs ML disagreement

| | firings | hit rate |
|---|---|---|
| rule says due, ML disagrees | thousands per label | **0.02 – 0.10** |
| ML says yes, rule disagrees | hundreds per label | **0.28 – 0.43** |

`BATTERY_TEST`: 4,354 rule-only firings hit 7.0%; 548 ML-only firings hit 38.3%.
`ENGINE_OIL_CHANGE`: ML fires on 1,773 landmarks the rule does not and is right
**81.6%** of the time. Disagreement is not called model error — on this data the
**rule** is the one that is wrong, over-firing 5–10× on inspection labels exactly as
Phase 9 predicted. This also settles the rule-replication question from the other
side: if V3 merely replayed the rules, the ML-only column would be empty
([`24_rule_vs_ml_analysis.md`](24_rule_vs_ml_analysis.md)).

## 15. Synthetic Ceiling Diagnosis

**D — MIXED.**

Three distinct regimes, not one:

1. **One near-deterministic high-prevalence label** (`ENGINE_OIL_CHANGE`, 88%) where
   the rule and the base rate already explain almost everything and ML adds 1.11×.
2. **A middle band of ~28 threshold-gated / bundle-attached labels** where ML roughly
   doubles PR-AUC over both the rule and the base rate. **This is where the real
   value is** — `CHAIN_CLEAN` 0.702, `CHAIN_LUBRICATE` 0.577, `BATTERY_TEST` 0.397,
   `AIR_FILTER_INSPECTION` 0.381.
3. **~15 random-event labels** (breakdown faults, inspection findings) that are not
   learnable from any observable and sit at PR-AUC 0.01–0.08 regardless of model.
   Their large "lift over prevalence" multiples are an artifact of a 0.5% base rate.

Neither "strong observable signal" nor "rule-dominated" nor "insufficient signal"
describes this dataset on its own.

## 16. Product Recommendation

> **V3 CHALLENGER ACCEPTED — SYNTHETIC MULTI-LABEL VALIDATION PASS; OFFLINE ONLY;
> REAL FLEET VALIDATION PENDING**

Justification: the leakage gate passes on all three checks; the champion beats the
rule baseline by 1.89× mAP and the prevalence baseline by 1.71×; TEST micro F1 (0.5192)
and micro PR-AUC (0.5611) hold close to VALIDATION; unseen-motorcycle degradation is
mild; calibration is fitted on held-out data with per-label method selection; and all
product invariants hold.

**This acceptance is qualified**, and the qualifications are not footnotes:

- The label set is **not uniformly learnable**. 15 of 44 labels are random events
  with no observable signal and must not be shown as confident predictions.
- **Macro F1 is low (TEST 0.1107)** under the single global threshold. Rare labels
  are usable as probabilities and ranks, not as binary flags.
- mAP degrades 18% from VALIDATION to TEST under distribution shift.
- 12 labels have <30 TEST positives.
- The finding rests on a synthetic world whose core generator is not inspectable.

## 17. Production Safety

| question | answer |
|---|---|
| V2.1 modified? | **NO** — all 21 frozen hashes re-verified identical ([`30_frozen_hash_recheck.json`](30_frozen_hash_recheck.json)) |
| V2.1 retrained? | **NO** |
| Maintenance Urgency modified? | **NO** — `policy/urgency.py` hash unchanged |
| Maintenance Due modified? | **NO** |
| V2.4 created? | **NO** |
| production deployed? | **NO** — no route mounted, no frontend change, no backend import of `ridebase_ml.v3` |
| real-fleet validation claimed? | **NO** — every artifact carries `real_fleet_validation: PENDING` |
| hardcoded desired scores? | **NO** |

## 18. Tests

| Suite | Passed | Failed |
|---|---|---|
| `ridebase-ml/tests` (incl. 39 new V3 tests) | 159 | 0 |
| `ridebase-v1-dashboard/backend/tests` | 106 | 0 |
| `ridebase-control-center/tests` | 94 | 0 |
| **total** | **359** | **0** |

New V3 coverage: target contract, next-service selection, multi-hot encoding, label
taxonomy, rare-label policy, PIT safety, future-injection invariance, T-1/T/T+1
boundary, no identifiers, no oracle/latent leakage, deterministic dataset
generation, split correctness, threshold freeze, calibration policy, top-K,
predictor determinism, probability bounds, artifact load/parity.

All V2.1 production tests and all Maintenance Urgency tests **PASS**.

## 19. Git

Six logical commits on `main`:

1. `6e4924b Define V3 multi-label target and label contract`
2. `9ca3c71 Build V3 PIT-safe dataset and choose the landmark strategy`
3. `620ba91 Add V3 leakage and generator-rule audits; fix a real determinism bug`
4. `021ef61 Train and evaluate V3 challengers: baselines, tournament, ablation, oracle`
5. `9455c9c Freeze V3 research champion, touch TEST once, audit product behaviour`
6. `Package offline V3 predictor and the research output contract`

| item | value |
|---|---|
| start HEAD | `b25f3b7` |
| final commit | the sixth commit above — the one carrying this report, so its own hash cannot be quoted inside itself |
| branch | `main` |
| working tree | clean |
| force push | none |

Reviewed before committing: no secrets, no `.env`, no tokens, no caches, no
`node_modules`, no debug dumps, no temporary giant files. The 16 MB CatBoost
artifact is consistent with repository convention (V2.1's history store is a
tracked 69 MB SQLite).

Verified untouched by `git diff --name-only b25f3b7..HEAD`:
`ridebase_ml/v2_1/`, `ridebase_ml/policy/`, `models/v2_1_v1_4/`,
`derived_outputs/v2_1_v1_4/`, `ridebase-v1-dashboard/`, `ridebase-control-center/`.
No backend file imports `ridebase_ml.v3`.

## 20. Next Recommended Step

**Real-data validation.**

Not more model tuning. The ablation shows 96% of the signal is already in 37 basic
features and that adding task recency *hurts*; the oracle study shows the remaining
headroom is next-visit timing, which is not a modelling problem. The open question
is not whether a better model exists on this synthetic world — it is whether the
generator's bundle-attachment process resembles how real workshops actually build a
work order. Nothing further can be learned about that from v1.4.

A concrete first step: take the 25 A_CORE labels and check their real-world
co-occurrence and interval behaviour against a real service history. In particular,
`OIL_FILTER_CHANGE` — decoupled from oil changes here but almost always paired in
reality — is a cheap, decisive test of whether this synthetic task layer is
trustworthy at all.

---

V3 WAS DEVELOPED AS AN OFFLINE MULTI-LABEL RESEARCH CHALLENGER.
V2.1 REMAINS THE FROZEN PRODUCTION CHAMPION.
MAINTENANCE DUE AND MAINTENANCE URGENCY REMAIN DETERMINISTIC AND SEPARATE.
NO REAL-FLEET VALIDATION IS CLAIMED.
NO PRODUCTION DEPLOYMENT WAS PERFORMED.
