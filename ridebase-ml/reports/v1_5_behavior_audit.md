# V1.5 generator behavior audit

**GATE 3: PASS — before model training.**

These are synthetic behavioral assumptions and are not validated on real RideBase fleet data.

## Due-pressure empirical rates

| group     |   rows |   event_30 |   event_60 |   event_90 |   event_120 |   eventual_return |
|:----------|-------:|-----------:|-----------:|-----------:|------------:|------------------:|
| <0.50     | 159465 |  0.0994415 |   0.24996  |   0.398927 |    0.529762 |          0.843207 |
| 0.50-0.75 |  50915 |  0.286236  |   0.517151 |   0.675975 |    0.787058 |          0.900776 |
| 0.75-1.00 |  28832 |  0.416981  |   0.663614 |   0.8121   |    0.895979 |          0.91773  |
| 1.00-1.25 |  11863 |  0.527375  |   0.770511 |   0.876748 |    0.928267 |          0.917727 |
| 1.25-1.50 |   4394 |  0.557522  |   0.771908 |   0.867651 |    0.925669 |          0.902139 |
| 1.50-2.00 |   2975 |  0.537175  |   0.766691 |   0.871604 |    0.92484  |          0.872269 |
| 2.00-2.50 |    804 |  0.577689  |   0.779754 |   0.887955 |    0.936441 |          0.837065 |
| 2.50-3.00 |    267 |  0.520833  |   0.754386 |   0.878924 |    0.917808 |          0.764045 |
| 3.00+     |    289 |  0.427451  |   0.644068 |   0.730942 |    0.784038 |          0.591696 |

## Directional summary

- Not-due P30: 0.1447; overdue P30: 0.5357; severe-overdue P30: 0.4275.
- Severe-overdue eventual return: 0.5917; the severe group is not a dead region.
- Overdue high-usage P30: 0.6759; low-usage: 0.3143.
- Known appointment P30: 0.8146; no known appointment: 0.1719.
- ON_TIME vs DELAYER direction pass rate across due bands: 1.000.
- NO_SHOW_PRONE vs NORMAL negative direction pass rate across due bands: 1.000.

## Checks

- PASS — `v1_5_structural_qa`
- PASS — `deterministic_regeneration`
- PASS — `clear_overdue_response`
- PASS — `km_pressure_response`
- PASS — `days_pressure_response`
- PASS — `no_severe_overdue_dead_zone`
- PASS — `smooth_saturation_unit_gate`
- PASS — `high_usage_positive_when_overdue`
- PASS — `adherence_direction_rate`
- PASS — `no_show_profile_direction_rate`
- PASS — `observable_repeated_no_show_counteracts`
- PASS — `high_churn_counteracts`
- PASS — `appointment_strong_positive`
- PASS — `recent_breakdown_positive_when_overdue`
- PASS — `horizon_monotonicity`
- PASS — `all_segments_represented`
- PASS — `no_latent_profile_in_modeling_table`
- PASS — `no_absolute_year_feature`

Latent profile names are used only in this generator audit and are absent from the V2.2 modeling table.
