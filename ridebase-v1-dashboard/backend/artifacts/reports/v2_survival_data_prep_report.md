# RideBase V2 Survival Data Preparation

_Notebook 13 · dataset **v1.3.0 (frozen)** · seed 42 · NO predictive model trained · output hash `1284a4781646d677`_

## Executive Summary

Constructed **41,518 leakage-safe time-to-next-service survival episodes** from frozen RideBase v1.3 using the dataset's authoritative strict-temporal survival contract (`survival_*` columns, per-split administrative censoring). **28,153 events / 13,365 right-censored.** V1 regression could only use the 28,153 observed rows; V2 additionally uses **13,365 right-censored episodes**. 0 negative / 0 zero durations, observed durations reproduce V1 `days_to_next_service` exactly. Leakage audit PASS on 145 features. Informative-censoring concern: **HIGH**. Kaplan-Meier median survival 126 days. **READY FOR V2 MODELING.**

## Why V2 Survival
V1 answered *"how many days/km until the next service?"* but could only learn from snapshots whose next service was actually observed. V2 answers *"what is the probability this motorcycle returns for service within 30 / 60 / 90 / 120 days?"* and can use right-censored snapshots (no service seen yet) as partial information instead of discarding them.

## Dataset Version
v1.3.0; generator 1.3.0; split unchanged {'TRAIN': 32203, 'VALIDATION': 4845, 'TEST': 4470}. Frozen — not modified.

## Survival Problem Definition
Endpoint = **time to next ANY real service** after the snapshot (NEXT ANY SERVICE, same contract as V1). Whichever of PERIODIC / REPAIR / BREAKDOWN / TIRE occurs first is the event. Cancelled / no-show / scheduled-only appointments are not events.

## Event Definition
`event_observed = 1` and `duration_days = next_service_at − snapshot_at` when the next real service is observed before the split's administrative censor date.

## Censoring Definition
`event_observed = 0` and `duration_days = survival_admin_censor_at − snapshot_at` otherwise. This means **"no next service was observed for at least `duration_days` days"** — NOT "serviced on day `duration_days`".

## Observation Boundary
Method: **existing_authoritative_survival_contract: per-split administrative censor `survival_admin_censor_at`, aligned to split_contract label cutoffs** (priority-2 in the spec: existing authoritative censoring contract). Per split: TRAIN 2025-06-30 23:59:59, VALIDATION 2025-12-31 23:59:59, TEST 2026-08-25 23:59:59 (= dataset generation date). Diagnostic global cutoff 2026-08-25 23:59:59; 1937 rows have an earlier motorcycle-observation-end in the retrospective contract.

## Temporal Label Audit
```
     split  rows  events_strict_B  events_retro_A  reclassified_censored_to_event  A_events_after_split_cutoff  boundary_crossing_future_target
     TRAIN 32203            25442           28614                            3172                         3172                             3172
VALIDATION  4845             1429            3180                            1751                         1751                             1751
      TEST  4470             1282            1282                               0                            0                                0
```
**A) retrospective / existing full-dataset contract** (`target_event_observed`, censor at global dataset end): 33,076 events. **B) strict-temporal administrative censoring (PRIMARY)**: 28,153 events. Contract A reclassifies 4,923 censored rows to events, of which **4923 have their real service AFTER the split cutoff** — a TRAIN/VALIDATION label depending on a later calendar period = temporal label leakage. The primary V2 dataset uses contract B and has **0** such rows. Leakage risk level (if A were used): **HIGH**.

## Train / Validation / Test
```
     split  rows  events  censored  event_rate  censoring_rate  duration_mean  duration_median  duration_p25  duration_p75  duration_p90  unique_motorcycles  unique_workshops
     TRAIN 32203   25442      6761      0.7901          0.2099         149.54           103.36         54.28        194.30        332.59                6761                10
VALIDATION  4845    1429      3416      0.2949          0.7051          76.33            66.59         37.12        112.01        151.47                3416                10
      TEST  4470    1282      3188      0.2868          0.7132          92.77            82.30         27.57        156.58        202.53                3188                10
```

## V1 vs V2 Row Utilization
```
     split   total  V1_regression_usable  V1_censored_excluded  V2_survival_usable  V2_observed  V2_censored
     TRAIN 32203.0               25442.0                6761.0             32203.0      25442.0       6761.0
VALIDATION  4845.0                1429.0                3416.0              4845.0       1429.0       3416.0
      TEST  4470.0                1282.0                3188.0              4470.0       1282.0       3188.0
     TOTAL 41518.0               28153.0               13365.0             41518.0      28153.0      13365.0
```
V2 uses **13,365** right-censored episodes that V1 regression had to drop.

## Duration Distribution
Overall median **95.4 d**, p90 **296.6 d**, max 1553 d. Observed median 91.3 d; censored median 107.6 d. Zero-duration rows: 0. Negative: 0.

## Observed vs Censored
Observed 28,153 (67.8%) · censored 13,365 (32.2%).

## Censoring by Split
TRAIN 21.0% · VALIDATION 70.5% · TEST 71.3%. The very high VAL/TEST censoring is **censoring-rate drift** driven by their much shorter observation windows (6 and ~8 months), a distinct phenomenon from target drift or feature drift.

## Censoring Over Time
`v2_censoring_over_time.csv` + fig 08 — censoring rises sharply toward each split's cutoff, as expected for administrative censoring.

## Censoring by Segment
`v2_censoring_by_segment.csv` (n ≥ 30). By history depth:
```
 segment_type segment_value split     n  events  censored  censoring_rate  median_duration
history_depth           0-1   ALL 15201    9905      5296          0.3484           150.20
history_depth           2-3   ALL  9157    5631      3526          0.3851           111.32
history_depth            4+   ALL 17160   12617      4543          0.2647            58.76
```

## Recurrent Service Episodes
8,442 motorcycles, 41,518 episodes (mean 4.92, median 3, p90 10, max 56 per motorcycle). By count: {'1': 1683, '2-3': 2819, '4-5': 1633, '6+': 2307}. **Observations are repeated service episodes within motorcycles** — within-motorcycle dependence must be respected in nb14+ evaluation (grouped CV / clustered SE).

## Motorcycle / Workshop Overlap
```
{
 "motorcycles": {
  "TRAIN": 6761,
  "VALIDATION": 3416,
  "TEST": 3188
 },
 "workshops": {
  "TRAIN": 10,
  "VALIDATION": 10,
  "TEST": 10
 },
 "moto_overlap": {
  "train_val": 2592,
  "train_test": 1912,
  "val_test": 1751
 },
 "workshop_overlap": {
  "train_val": 10,
  "train_test": 10,
  "val_test": 10
 }
}
```
The primary time split is not motorcycle-disjoint (train-test share 1,912 motorcycles). Documented only; split unchanged. A separate UNSEEN_MOTORCYCLE regime exists for strict group generalization.

## Event Type Distribution
```
     split event_type  count    pct  median_duration
     TRAIN   PERIODIC  23728 0.9326            97.43
     TRAIN     REPAIR   1197 0.0470            55.53
     TRAIN  BREAKDOWN    284 0.0112            58.01
     TRAIN       TIRE    233 0.0092           121.54
VALIDATION   PERIODIC   1304 0.9125            56.40
VALIDATION     REPAIR     91 0.0637            41.08
VALIDATION  BREAKDOWN     18 0.0126            31.23
VALIDATION       TIRE     16 0.0112            60.82
      TEST   PERIODIC   1160 0.9048            90.88
      TEST     REPAIR     91 0.0710            63.14
      TEST  BREAKDOWN     20 0.0156            42.55
      TEST       TIRE     11 0.0086           107.59
```
`next_event_type` is **future information → AUDIT_ONLY / TARGET_SIDE**, never a model feature.

## Observed-vs-Censored Feature Shift
`v2_observed_censored_feature_shift.csv`. Top:
```
                              feature  mean_observed  mean_censored     smd  abs_smd magnitude
                        snapshot_year      2023.3911      2024.9493 -1.5569   1.5569  material
            avg_service_interval_days       108.1492       203.2083 -0.9685   0.9685  material
               rolling3_interval_days       108.1492       203.2083 -0.9685   0.9685  material
      historical_interval_days_median       108.1492       203.2083 -0.9685   0.9685  material
               previous_interval_days       105.9709       202.7880 -0.9594   0.9594  material
          days_since_previous_service       105.9709       202.7880 -0.9594   0.9594  material
avg_km_per_day_since_previous_service        50.3261        26.4346  0.8600   0.8600  material
                   annual_km_baseline     21171.2139     13014.7502  0.8342   0.8342  material
                 long_term_km_per_day        57.9636        35.6324  0.8342   0.8342  material
                    avg_service_spend      1488.6500      2343.0000 -0.8149   0.8149  material
```

## Potential Informative Censoring
SMD bands: <0.10 small · 0.10–0.25 moderate · >0.25 material. material 46 · moderate 28 · max |SMD| 1.557 (snapshot_year). **Concern level: HIGH.** The largest shifts are calendar-position driven (`snapshot_year`, interval features): rows near a split cutoff are both later-dated and more likely censored — expected for administrative censoring and only partly true informative censoring. Diagnostic only — synthetic-dataset behaviour, not a causal claim. nb14 should prefer estimators/weighting that tolerate covariate-dependent censoring.

## Survival Horizon Support
```
 horizon_days      split  rows_at_risk  events_before_horizon  censored_before_horizon support_status
           30      TRAIN         29902                   1532                      769           GOOD
           30 VALIDATION          3964                    178                      703       MODERATE
           30       TEST          3310                     63                     1097       MODERATE
           60      TRAIN         23026                   7673                     1504           GOOD
           60 VALIDATION          2642                    804                     1399           GOOD
           60       TEST          2669                    394                     1407           GOOD
           90      TRAIN         17944                  12101                     2158           GOOD
           90 VALIDATION          1730                   1143                     1972           GOOD
           90       TEST          2090                    653                     1727           GOOD
          120      TRAIN         14095                  15369                     2739           GOOD
          120 VALIDATION          1051                   1322                     2472           GOOD
          120       TEST          1618                    830                     2022           GOOD
          180      TRAIN          8870                  19606                     3727           GOOD
          180 VALIDATION            61                   1429                     3355       MODERATE
          180       TEST           764                   1069                     2637           GOOD
          365      TRAIN          2400                  24440                     5363           GOOD
          365 VALIDATION             0                   1429                     3416            LOW
          365       TEST             0                   1282                     3188            LOW
```

## Kaplan-Meier Sanity Check
S(t) — probability the next service has NOT happened by day t. S(30)=0.95, S(60)=0.77, S(90)=0.63, S(120)=0.52. Median survival: 126.1 days. By split: {'TRAIN': '118.1', 'VALIDATION': '174.2', 'TEST': '203.0'}. Descriptive only — not a predictive model.

## Leakage Audit
`v2_survival_leakage_audit.csv` — 145 model features, all `leakage_status = PASS`; 142 production-derivable. Column roles in `v2_survival_column_manifest.csv`. Forbidden target/future columns: 0 in features.

## Data Quality
```
                            check                                              value                                           expected status                                                  notes
                  dataset_version                                              1.3.0                                              1.3.0   PASS                                                       
                  split_unchanged {'TRAIN': 32203, 'VALIDATION': 4845, 'TEST': 4470} {'TRAIN': 32203, 'VALIDATION': 4845, 'TEST': 4470}   PASS                                                       
               duplicate_snapshot                                                  0                                                  0   PASS                                                       
         censoring_boundary_valid                                               True                                               True   PASS                        one admin censor date per split
           survival_eligible_rows                                              41518                                              41518   PASS                     every snapshot is a usable episode
                negative_duration                                                  0                                                  0   PASS                                                       
                    zero_duration                                                  0                                                  0   PASS                           audited, not silently bumped
        missing_duration_modeling                                                  0                                                  0   PASS                                                       
           missing_event_observed                                                  0                                                  0   PASS                                                       
            snapshot_after_censor                                                  0                                                  0   PASS                                                       
            event_before_snapshot                                                  0                                                  0   PASS                                                       
            observed_target_match                                max|diff|=0.000000d                                0 (or sub-rounding)   PASS          0 semantic mismatches vs days_to_next_service
             event_subset_of_full                                                  0                                                  0   PASS every strict-temporal event is a real observed service
         event_equals_v1_observed                                               True                                               True   PASS            V2 observed set == V1 regression usable set
temporal_label_overlap_in_primary                                                  0                                                  0   PASS          primary(B) has no event past its admin censor
           future_feature_leakage                                                  0                                                  0   PASS                                  145 features all PASS
    modeling_table_no_future_cols                                                  0                                                  0   PASS                                                       
               split_changed_rows                                                  0                                                  0   PASS                                                       
            reproducibility_event                                                  0                                                  0   PASS                  event_observed re-derives identically
             orphan_motorcycle_id                                                  0                                                  0   PASS                                                       
                    invalid_split                                                  0                                                  0   PASS                                                       
                      output_hash                                   1284a4781646d677                                      deterministic   PASS                   sha256[:16] of modeling table target
```

## Limitations
- Synthetic v1.3 — no real-fleet validation. Censoring / interval structure follow generator rules.
- Recurrent episodes per motorcycle → correlated observations; naive CV will be optimistic.
- Time split ≠ motorcycle split; train-test motorcycle overlap is large.
- VAL/TEST censoring ~70% (short windows) → long-horizon (180/365 d) estimates are weak there.
- `MOTORCYCLE_OBSERVATION_END` cases: strict contract censors at the split cutoff, which can slightly overstate censored duration for motorcycles that left the fleet earlier.

## V2 Modeling Readiness
**READY FOR V2 MODELING** — target valid, censoring valid, split intact (0 changed), leakage PASS, 28,153 events, 30/60/90/120-day horizon support acceptable.

## Recommendation for Notebook 14
`notebooks/14_v2_survival_baseline.ipynb` — Kaplan-Meier reference, Cox PH baseline, Random Survival Forest baseline. Metrics to compute there (NOT here): C-index, Integrated Brier Score, Brier @30/60/90/120, time-dependent AUC, calibration @30/60/90/120. Use grouped (by motorcycle_id) resampling.
