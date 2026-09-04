# V2.2.1 Statistical Diagnosis

**Gate: PASS — TRAIN+VALIDATION only**

## Evidence

- V1.5 has a higher and more behaviorally heterogeneous return process than V1.4; latent churn/no-show tendencies intentionally add irreducible ranking noise because latent labels are forbidden model inputs.
- The six observable history features add ranking signal, but days_to_next_known_appointment is structurally sparse and must be handled carefully.
- The current XGB-Cox risk ranking is useful but its Breslow absolute scale is badly offset; isotonic fixes Brier/calibration while compressing P30 resolution into large plateaus.
- The train-validation concordance gap quantifies model overfit; recovery should prioritize regularization and stable feature subsets rather than higher probabilities.

## Temporal validation

| start      | end        |   rows |   ipcw_c_index |      ibs |   p90_calibration_error |
|:-----------|:-----------|-------:|---------------:|---------:|------------------------:|
| 2025-07-01 | 2025-08-31 |  11671 |       0.752325 | 0.149949 |              0.00572394 |
| 2025-09-01 | 2025-10-31 |  12177 |       0.73242  | 0.160364 |              0.0148727  |
| 2025-11-01 | 2025-12-31 |  12603 |       0.718876 | 0.169799 |              0.0352327  |
