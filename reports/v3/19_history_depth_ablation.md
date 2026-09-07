# V3 Phase 19 — History Depth Ablation

Same model family (unweighted XGBoost), same landmarks, same split, same
thresholds procedure. Only the feature blocks change. TRAIN/VALIDATION only.

Data: [`19_history_depth_ablation.csv`](19_history_depth_ablation.csv).

| feature set | n features | micro F1 | macro F1 | mAP | micro PR-AUC | P@3 | R@3 |
|---|---|---|---|---|---|---|---|
| F0_basic | 37 | 0.3939 | 0.2189 | 0.1588 | 0.5608 | 0.4866 | 0.5403 |
| F1_plus_policy | 125 | 0.4254 | 0.2231 | 0.1647 | 0.5706 | 0.4962 | 0.5483 |
| F2_plus_task_history | 172 | 0.4373 | 0.2249 | 0.1665 | 0.5731 | 0.4957 | 0.5515 |
| F3_plus_task_recency | 260 | 0.4260 | 0.2223 | 0.1637 | 0.5702 | 0.4964 | 0.5524 |
| F4_plus_behavioural | 277 | 0.4215 | 0.2234 | 0.1650 | 0.5771 | 0.5008 | 0.5690 |
| task_history_only_no_policy | 172 | 0.4136 | 0.2190 | 0.1637 | 0.5696 | 0.4931 | 0.5494 |

## Block definitions

| block | contents |
|---|---|
| **F0** | motorcycle attributes, odometer at landmark, time and km since last service, OEM interval state, seasonality. The frozen V2.1 base contract minus the behavioural aggregates. |
| **F1** | `policy_due_ratio__X` and `policy_overdue__X` per task — the deterministic OEM maintenance state at the landmark. |
| **F2** | `hist_count__X` per task plus cross-task aggregates — how often each task has been done before. |
| **F3** | `days_since__X` and `km_since__X` per task — task recency. |
| **F4** | observable service and appointment behaviour aggregates (prior service counts, delay history, on-time rate, spend, workshop attributes). |

## What this says about where V3's signal comes from

**F0 alone already reaches mAP 0.1588** — 96.2% of the full model's
0.1650, from just 37 features. Knowing the bike, its odometer, and
how long and how far it has been since the last service is most of the answer.

**Deterministic policy state (F1) is the single largest addition**: +0.0059 mAP and
+0.0315 micro F1 for 88 extra columns. This is consistent with Phase 9:
the policy table is a real gate on which tasks are eligible, even though it is a
poor standalone predictor of which eligible tasks actually get performed.

**Per-task history (F2) adds little, and per-task recency (F3) adds nothing.**
F2 gains +0.0018 mAP; F3 then *loses* 0.0028 mAP while adding 88 columns.
This is a genuine negative result and it is not smoothed over: the 88
`days_since__X` / `km_since__X` columns are largely redundant with the
`policy_due_ratio__X` columns, which are computed *from* them, and the duplication
costs more in variance than it returns in signal.

**Task history cannot substitute for policy state.** Dropping F1 but keeping F2+F3
(`task_history_only_no_policy`) gives mAP 0.1637, below the F1 configuration with
half as many task columns. The interval *thresholds* carry information that raw
recency does not.

**F4 behavioural history is roughly neutral on mAP** (+0.0013) but gives the best
micro PR-AUC (0.5771) and the best P@3 (0.5008) in the table, so it is
retained in the champion contract.

## Honest summary

The spread from the simplest to the richest feature set is **0.0062 mAP** — about
4%. V3's signal is dominated by basic maintenance state, not by deep
task history. A materially simpler V3 (F0+F1, 125 features instead of 277) would
retain 99.8% of the champion's mAP, and that is the configuration a
production build should start from rather than the full matrix.
