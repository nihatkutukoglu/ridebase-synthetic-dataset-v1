# RideBase v1.4 Synthetic Generator Update

**Gate: PASS**

## Root cause

v1.3 regenerate_services preserved each motorcycle's fixed source row count and only rescaled timestamps; no stochastic event could occur after the final retained row

99.0016% of v1.3 severely-overdue landmarks were after the final generated service; their P90 was 0%, versus 93.6306% when a future retained service existed

## Due pressure vs actual return

| due_state        |   landmarks |   motorcycles |   event_30d_rate |   event_60d_rate |   event_90d_rate |   event_120d_rate |   eventual_event_rate |   median_due_ratio |
|:-----------------|------------:|--------------:|-----------------:|-----------------:|-----------------:|------------------:|----------------------:|-------------------:|
| NOT_DUE          |      201168 |          8940 |           0.1120 |           0.2350 |           0.3440 |            0.4381 |                0.8290 |             0.3490 |
| NEAR_DUE         |       41216 |          7162 |           0.3329 |           0.5196 |           0.6388 |            0.7161 |                0.8644 |             0.9485 |
| OVERDUE          |       18209 |          4242 |           0.3354 |           0.5194 |           0.6353 |            0.7093 |                0.8385 |             1.4328 |
| SEVERELY_OVERDUE |        5188 |          1304 |           0.3470 |           0.5305 |           0.6355 |            0.7001 |                0.8044 |             2.5075 |

## Behavior overlap

| behavior_group   |   attempts |   service_rate |   p10_due |   median_due |   p90_due |
|:-----------------|-----------:|---------------:|----------:|-------------:|----------:|
| IRREGULAR        |       1806 |         0.8671 |    0.3535 |       1.2095 |    2.4519 |
| REGULAR          |       1798 |         0.8782 |    0.3644 |       1.2057 |    2.3985 |
| SLIGHTLY_LATE    |       9085 |         0.8846 |    0.4006 |       1.2206 |    2.4700 |

## Hard gate

- PASS — `source_schema_unchanged`
- PASS — `v1_3_hashes_unchanged`
- PASS — `source_qa_pass`
- PASS — `severely_overdue_dead_region_resolved`
- PASS — `overdue_return_behavior_meaningful`
- PASS — `due_pressure_direction`
- PASS — `km_usage_sensitivity`
- PASS — `time_usage_sensitivity`
- PASS — `behavior_group_overlap`
- PASS — `service_outcome_not_deterministic`
- PASS — `reproducible_source_hashes`

## Final verdict

V1.4 GENERATOR READY FOR V2.1 REBUILD
