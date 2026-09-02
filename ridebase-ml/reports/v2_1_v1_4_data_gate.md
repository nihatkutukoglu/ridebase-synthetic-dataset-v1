# RideBase V2.1 Dataset Rebuild

**Gate: PASS**

Input v1.4.0; 256,841 landmarks; 8,907 motorcycles; 208,746 events; 48,095 censored; 54 features.

## Due-state behavior

| due_state        |   landmarks |   motorcycles |   event_30d_rate |   event_90d_rate |   eventual_event_rate |   due_ratio_mean |
|:-----------------|------------:|--------------:|-----------------:|-----------------:|----------------------:|-----------------:|
| NOT_DUE          |      195688 |          8907 |           0.1114 |           0.3666 |                0.8046 |           0.3628 |
| NEAR_DUE         |       39268 |          7136 |           0.3377 |           0.6984 |                0.8499 |           0.9638 |
| OVERDUE          |       17093 |          4222 |           0.3446 |           0.7113 |                0.8258 |           1.4808 |
| SEVERELY_OVERDUE |        4792 |          1290 |           0.3622 |           0.7389 |                0.7963 |           2.9396 |

## Split

| modeling_role                   |   landmarks |   motorcycles |
|:--------------------------------|------------:|--------------:|
| TEST                            |       46508 |          7157 |
| TRAIN                           |      134937 |          5880 |
| UNSEEN_MOTORCYCLE_EXCLUDED      |       30951 |          1201 |
| UNSEEN_MOTORCYCLE_TEMPORAL_TEST |        8409 |          1275 |
| VALIDATION                      |       36036 |          6358 |

## Gate checks

- PASS — `frozen_v1_3_source_unchanged`
- PASS — `v1_4_source_schema_compatible`
- PASS — `landmark_target_quality_pass`
- PASS — `severe_overdue_not_near_zero`
- PASS — `overdue_direction_coherent`
- PASS — `km_due_relevant`
- PASS — `days_due_not_structurally_reversed`
- PASS — `no_absolute_calendar_year_feature`
- PASS — `event_no_event_overlap`
- PASS — `customer_behavior_overlap`
- PASS — `usage_behavior_overlap`
- PASS — `feature_lineage_no_leakage`
- PASS — `split_not_model_feature`
- PASS — `unseen_motorcycle_isolation`
- PASS — `target_horizon_monotonicity`
- PASS — `critical_due_feature_present`

## Final verdict

V2.1 DATA GATE PASS — MODEL TRAINING ALLOWED
