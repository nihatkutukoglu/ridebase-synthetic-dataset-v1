# RideBase V2.2 TRAIN+VALIDATION Selection

**Gate: PASS**

TEST was not read by this phase. Selection and calibration are frozen before TEST first touch.

## Candidates

| candidate           | feature_contract              |   ipcw_c |      ibs | status   |
|:--------------------|:------------------------------|---------:|---------:|:---------|
| oem_policy_due_rule | deterministic_policy_baseline | 0.680503 | 0.32666  | FIT      |
| simple_cox          | 4_feature_baseline            | 0.688878 | 0.184308 | FIT      |
| cox_ph_extended60   | extended60                    | 0.724405 | 0.166331 | FIT      |
| coxnet_extended60   | extended60                    | 0.72397  | 0.166421 | FIT      |
| xgb_cox_frozen54    | frozen54                      | 0.72649  | 0.395647 | FIT      |
| xgb_cox_extended60  | extended60                    | 0.734321 | 0.386291 | FIT      |

## Selected challenger

- Model: `xgb_cox_extended60`
- Calibration: `isotonic`
- Feature contract: `extended60`

## Behavioral gate

- PASS — `scenario_count_at_least_5000`
- PASS — `due_pressure_monotone_rate`
- PASS — `overdue_lift_material`
- PASS — `severe_overdue_saturates`
- PASS — `severe_overdue_not_deterministic`
- PASS — `high_usage_overdue_lift`
- PASS — `adherence_direction`
- PASS — `no_show_counteracts_return`
- PASS — `known_appointment_intent_lift`
- PASS — `breakdown_pressure_lift`
- PASS — `service_recency_interpretable`
- PASS — `horizon_monotonicity`
- PASS — `p30_non_degenerate`
- PASS — `same_input_deterministic`
- PASS — `calendar_year_invariance`
- PASS — `ood_finite_and_bounded`
- PASS — `ood_warnings_explicit`

## Leakage and selection controls

- PASS — `train_and_validation_only`
- PASS — `test_status_sealed`
- PASS — `selection_uses_extended_observable_contract`
- PASS — `feature_count_60`
- PASS — `frozen_base54_prefix_exact`
- PASS — `observable_extension_exact`
- PASS — `forbidden_features_absent`
- PASS — `validation_ipcw_c_acceptable`
- PASS — `calibrated_validation_ibs_acceptable`
- PASS — `validation_calibration_acceptable`
- PASS — `behavior_gate_pass`
