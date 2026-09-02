# RideBase V2.1 Model Training

**Gate: PASS**

Champion: `xgb_cox` selected on VALIDATION; calibration: `isotonic`.

## Candidate validation metrics

| candidate           |   ipcw_c_index |      ibs | status   |
|:--------------------|---------------:|---------:|:---------|
| oem_policy_due_rule |       0.679188 | 0.218275 | FIT      |
| simple_cox          |       0.703167 | 0.180188 | FIT      |
| cox_ph              |       0.724715 | 0.159907 | FIT      |
| coxnet              |       0.724704 | 0.16     | FIT      |
| xgb_cox             |       0.743156 | 0.295231 | FIT      |

## Metamorphic checks

- PASS — `km_sensitivity_meaningful`
- PASS — `elapsed_time_no_structural_reversal`
- PASS — `due_state_no_structural_reversal`
- PASS — `calendar_invariance`
- PASS — `same_input_deterministic`
- PASS — `horizon_monotonicity`
- PASS — `odometer_consistency`
- PASS — `annual_usage_changes_risk`

## Final gate

- PASS — `p30_usable`
- PASS — `km_sensitivity_meaningful`
- PASS — `elapsed_time_no_structural_reversal`
- PASS — `calendar_invariance`
- PASS — `horizon_monotonicity`
- PASS — `calibration_acceptable`
- PASS — `unseen_motorcycle_reported`
- PASS — `no_artifact_dominance`
- PASS — `validation_only_selection`
- PASS — `synthetic_only_status_explicit`

## Final verdict

V2.1 SYNTHETIC MODEL PASS — PACKAGING ALLOWED
