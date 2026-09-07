# V3 Phases 11-14 — Baselines, Model Tournament, Imbalance and Metrics

All numbers are **VALIDATION**. TEST was not touched at any point in this phase.
Thresholds are tuned per label on VALIDATION (Phase 15). Every model and baseline
consumes the identical 277-column point-in-time feature matrix and the identical
applicability mask, so no result here is a feature-access artifact.

Data: [`12_tournament_validation.csv`](12_tournament_validation.csv),
[`12_tournament_per_label_validation.csv`](12_tournament_per_label_validation.csv).

## Metric contract (Phase 14)

Plain accuracy is **not** reported as a primary metric. With a 0.6%-prevalence
label, predicting all-zero scores 99.4% and is worthless. `subset_accuracy` is
shown for completeness and treated as secondary, as required.

Selection is on **mAP** (mean average precision = macro PR-AUC over labels with
positives), with micro PR-AUC, micro F1 and P@3 as ordered tie-breaks. This
ordering was fixed before the tournament ran and is recorded in
`SELECTION_CRITERIA` in `scripts/v3_research.py`.

## Phase 11 — Baselines

| model | micro F1 | macro F1 | weighted F1 | mAP | micro PR-AUC | P@1 | P@3 | R@3 | P@5 | R@5 | Hamming | subset acc | fit s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline0_prevalence | 0.2302 | 0.1501 | 0.4370 | 0.0991 | 0.4338 | 0.8355 | 0.4377 | 0.4769 | 0.3441 | 0.5535 | 0.4844 | 0.0000 | 0.0000 |
| baseline2_recurrence | 0.2977 | 0.1687 | 0.4434 | 0.0966 | 0.4307 | 0.8286 | 0.4534 | 0.4895 | 0.3609 | 0.5769 | 0.3080 | 0.0000 | 0.0000 |
| baseline1b_rule_projected | 0.2581 | 0.1518 | 0.4377 | 0.0900 | 0.1030 | 0.1653 | 0.1318 | 0.0818 | 0.0776 | 0.0823 | 0.3999 | 0.0000 | 0.0000 |
| baseline1_rule | 0.2591 | 0.1521 | 0.4373 | 0.0898 | 0.0970 | 0.1592 | 0.1245 | 0.0775 | 0.0707 | 0.0758 | 0.3960 | 0.0000 | 0.0000 |

- **Baseline 0 (prevalence)** — per-label TRAIN base rate, identical for every row.
- **Baseline 1 (rule)** — deterministic OEM policy state at the landmark, scored
  `due_ratio / (1 + due_ratio)`. Nothing is fitted.
- **Baseline 1b (rule projected)** — the same rule projected forward to `t*`, the
  number of days until the first task in the plan falls due. Median `t*` is 36.5
  days against an observed median lead of 39 days, which independently confirms
  the projection logic is right.
- **Baseline 2 (recurrence)** — personal task recurrence rate smoothed toward the
  global prevalence, boosted by overdue-ness against the task's own observed cadence.

**Both rule baselines score below prevalence-only on every ranking metric.** This
is the central Phase-9 result restated: the policy table gates which tasks are
*allowed* onto a work order but does not decide which ones appear. See
[`09_generator_rule_audit.md`](09_generator_rule_audit.md).

## Phase 12 — Model tournament

| model | micro F1 | macro F1 | weighted F1 | mAP | micro PR-AUC | P@1 | P@3 | R@3 | P@5 | R@5 | Hamming | subset acc | fit s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| catboost | 0.4178 | 0.2276 | 0.5168 | 0.1699 | 0.5823 | 0.8353 | 0.5036 | 0.5654 | 0.3945 | 0.6668 | 0.1621 | 0.0495 | 186.8000 |
| extra_trees | 0.4012 | 0.2231 | 0.5152 | 0.1670 | 0.5786 | 0.8360 | 0.5021 | 0.5512 | 0.3910 | 0.6474 | 0.1690 | 0.0181 | 146.0000 |
| random_forest | 0.3951 | 0.2231 | 0.5157 | 0.1666 | 0.5815 | 0.8362 | 0.5059 | 0.5654 | 0.3954 | 0.6663 | 0.1743 | 0.0172 | 245.4000 |
| xgboost_balanced | 0.4193 | 0.2260 | 0.5131 | 0.1651 | 0.4036 | 0.5876 | 0.4200 | 0.4972 | 0.3437 | 0.6136 | 0.1613 | 0.0633 | 156.1000 |
| xgboost | 0.4215 | 0.2234 | 0.5138 | 0.1650 | 0.5771 | 0.8337 | 0.5008 | 0.5690 | 0.3912 | 0.6684 | 0.1573 | 0.0422 | 116.9000 |
| lightgbm | 0.4425 | 0.2111 | 0.5095 | 0.1644 | 0.5707 | 0.8336 | 0.4904 | 0.5474 | 0.3857 | 0.6424 | 0.1488 | 0.0700 | 123.1000 |
| lightgbm_balanced | 0.4593 | 0.2201 | 0.5103 | 0.1635 | 0.4917 | 0.7352 | 0.4585 | 0.5332 | 0.3618 | 0.6309 | 0.1336 | 0.0702 | 117.0000 |
| logreg | 0.4105 | 0.2221 | 0.5100 | 0.1600 | 0.5694 | 0.8279 | 0.4986 | 0.5659 | 0.3907 | 0.6694 | 0.1667 | 0.0540 | 22.1000 |
| logreg_balanced | 0.3930 | 0.2202 | 0.5097 | 0.1586 | 0.1494 | 0.1230 | 0.1381 | 0.1932 | 0.1573 | 0.3712 | 0.1807 | 0.0437 | 52.9000 |

Roster restricted to libraries already installed — no new dependency was added.
Classifier Chains were built and measured separately
([`17_label_cooccurrence.md`](17_label_cooccurrence.md)). No neural network was
introduced: the simple families do not clearly fail, so the brief's bar for
justifying one is not met.

## Phase 13 — Class imbalance: the most consequential finding

Every linear and boosted family was run twice, rebalanced and not. The pairing is
the experiment:

| family | variant | micro F1 | mAP | **micro PR-AUC** | **P@3** |
|---|---|---|---|---|---|
| logreg | balanced | 0.3930 | 0.1586 | **0.1494** | **0.1381** |
| logreg | none | 0.4105 | 0.1600 | **0.5694** | **0.4986** |
| xgboost | balanced | 0.4193 | 0.1651 | **0.4036** | **0.4200** |
| xgboost | none | 0.4215 | 0.1650 | **0.5771** | **0.5008** |
| lightgbm | balanced | 0.4593 | 0.1635 | **0.4917** | **0.4585** |
| lightgbm | none | 0.4425 | 0.1644 | **0.5707** | **0.4904** |

Rebalancing leaves per-label separation roughly unchanged — mAP moves by less than
0.002 in every pair — but it **rescales each label's probability by its own
positive rate**. Because each label is rebalanced independently, a 0.6%-prevalence
task ends up emitting probabilities on the same numeric scale as an 88%-prevalence
task. Cross-label comparability is destroyed, and with it every metric that ranks
labels against each other within a row: `logreg_balanced` collapses to P@3 = 0.138,
*below* the constant-prevalence baseline's 0.438.

For a product that both ranks tasks and prints percentages, this is disqualifying.
**All champion candidates are unweighted.** Imbalance is handled instead by
per-label threshold tuning (Phase 15) and per-label calibration (Phase 16), neither
of which touches the probability scale shared across labels.

SMOTE and other synthetic oversampling were **not** used: the data is temporal and
multi-label, and interpolating between rows would both invent maintenance histories
that never happened and risk crossing the TRAIN/VALIDATION time boundary.

## Champion selection

Applying the pre-registered rule:

1. leakage gate — **PASS** ([`08_leakage_audit.md`](08_leakage_audit.md))
2. beats the rule baseline on mAP — every ML family clears 0.0900 comfortably
3. **mAP** — `catboost` **0.1699** leads (`extra_trees` 0.1670, `random_forest` 0.1666)
4. **micro PR-AUC** — `catboost` **0.5823** also leads
5. micro F1 — `lightgbm_balanced` leads at 0.4593, but it is already eliminated at
   step 3, and its ranking metrics are materially worse
6. P@3 — `catboost` 0.5036 is within 0.002 of the best (`random_forest` 0.5059)

**Champion family: `catboost`.** It wins the primary criterion and the first
tie-break outright, and is not meaningfully behind on any other metric. Note that
had the criteria been ordered differently — micro F1 first — `lightgbm_balanced`
would have won on a metric whose ranking behaviour is 13% worse. Fixing the
ordering in advance is what prevented that.
