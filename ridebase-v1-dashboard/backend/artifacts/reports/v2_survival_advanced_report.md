# RideBase V2 Advanced Survival

_Notebook 15 · dataset v1.3.0 (frozen) · seed 42 · FULL run (FINAL) · input hash `dfc4ee1b266850dd`_

## Executive Summary

Advanced leakage-safe time-to-next-service survival modelling on all **41,518** v1.3 episodes (28,153 events / 13,365 right-censored). Candidates: CoxNet, XGBoost survival:cox, XGBoost survival:aft (RSF ranking diagnostic; GradientBoostingSurvival SKIPPED_RUNTIME). Selection on VALIDATION composite (40% IBS / 25% Brier@90 / 20% (1−IPCW-C) / 15% calibration@90), per-horizon IPCW-weighted isotonic calibration fit on VALIDATION only, ensemble selected. **Champion: ENSEMBLE[XGB_COX+COXNET]** (calibration: isotonic_ipcw). TEST — IPCW C-index 0.913, IBS 0.0488, Brier@90 0.0503, AUC@90 0.951, calibration@90 MODERATE. vs Cox baseline: IBS +14.5%, Brier@90 +18.5%, IPCW-C +0.018. **Advanced survival verdict: STRONG IMPROVEMENT. Final V2 signal: STRONG. V2 MODELING COMPLETE.**

## Objective
Reliable calibrated 30/60/90/120-day service probabilities that beat the nb14 Cox baseline on probability quality, calibration and temporal generalisation. Not a 'pick the most complex model' exercise — the Cox baseline stays champion unless meaningfully beaten.

## Dataset Contract
`v2_survival_modeling_table.parquet` — 41,518 episodes × 145 leakage-safe features. Split {'TRAIN': 32203, 'VALIDATION': 4845, 'TEST': 4470}. Censoring rate: {'TEST': 0.713, 'TRAIN': 0.21, 'VALIDATION': 0.705}. Target, censoring, split, generator unchanged.

## Baseline Reference
nb14 Cox PH (`v2_cox_baseline.joblib`, SET_A_COMPACT). TEST — IPCW-C 0.895, IBS 0.0570, Brier@90 0.0617, AUC@90 0.936, calibration@90 MODERATE.

## Advanced Candidate Models
```
       model   calibration  ipcw_c_index    ibs  brier_90  cal_error_90  composite
COX_BASELINE           raw        0.9092 0.0546    0.0614        0.1036     0.0709
      COXNET           raw        0.9254 0.0461    0.0517        0.0954     0.0606
     XGB_COX           raw        0.9143 0.0377    0.0443        0.0380     0.0490
     XGB_AFT           raw        0.9163 0.0731    0.0936        0.2317     0.1041
KM_REFERENCE           raw        0.5000 0.1226    0.1509           NaN     0.2092
     XGB_COX isotonic_ipcw        0.9239 0.0358    0.0421        0.0203     0.0431
      COXNET isotonic_ipcw        0.9249 0.0382    0.0428        0.0223     0.0443
```

## CoxNet
Elastic-net Cox, l1_ratio grid [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]. Selected l1_ratio=0.1, alpha=0.076198, 75 non-zero coefficients. No convergence warnings. `v2_optuna_coxnet_trials.csv`, `v2_coxnet_coefficients.csv`.

## XGBoost Survival Cox
Signed-time target (positive=event, negative=censored); encoding QA — events 25442, censored 6761 (unchanged). Survival function via Breslow baseline hazard on TRAIN hazard ratios: S(t|x)=exp(−H₀(t)·HR(x)). Optuna 120 trials, 3-fold expanding temporal CV composite. Best params {'eta': 0.05858701717404125, 'max_depth': 6, 'min_child_weight': 18.347422429608567, 'subsample': 0.6567488078997371, 'colsample_bytree': 0.8475429989649401, 'gamma': 4.79268782658841, 'reg_alpha': 0.001688830288572431, 'reg_lambda': 0.08219888648531636}, rounds 603. `v2_optuna_xgb_cox_trials.csv`.

## XGBoost Survival AFT
Interval target: observed→[t,t], censored→[t,∞). Encoding QA — observed 25442, censored 6761 (unchanged). S(t)=1−F_dist((log t − Xβ)/σ) with the fitted distribution (normal, σ=0.5); Xβ=log(model.predict). Optuna 120 trials. Best params {'eta': 0.03572924815064539, 'max_depth': 4, 'min_child_weight': 5.531976021844972, 'subsample': 0.7840932169897824, 'colsample_bytree': 0.9654835850702895, 'gamma': 0.005456959738945276, 'reg_alpha': 4.334707480459824, 'reg_lambda': 15.876430367525316}, rounds 539. `v2_optuna_xgb_aft_trials.csv`.

## Random Survival Forest
Ranking diagnostic only — `predict_survival_function` returned in 0.1s (probabilities usable). Best config {'n_estimators': 150, 'min_samples_leaf': 25, 'max_depth': 14}; fit on 14,000-row stratified TRAIN subsample. VALIDATION IPCW-C 0.927, TEST IPCW-C 0.913. `v2_optuna_rsf_trials.csv`.

## Gradient Boosting Survival
Status: **SKIPPED_RUNTIME** (wall-clock budget 210s). Excluded — deferred to a faster implementation.

## Hyperparameter Optimization
Optuna TPE (seed 42) + MedianPruner. Objective = mean over 3 expanding-window temporal folds (TRAIN only, sorted by snapshot_at, no shuffle) of composite = 0.4·IBS + 0.25·Brier@90 + 0.2·(1−IPCW-C) + 0.15·calibration@90 (natural metric scales, lower = better). 120 trials/model.

## Validation Results
```
       model   calibration  ipcw_c_index    ibs  brier_30  brier_60  brier_90  brier_120  cal_error_30  cal_error_60  cal_error_90  cal_error_120  composite
COX_BASELINE           raw        0.9092 0.0546    0.0254    0.0635    0.0614     0.0524        0.0195        0.0834        0.1036         0.0914     0.0709
      COXNET           raw        0.9254 0.0461    0.0242    0.0515    0.0517     0.0461        0.0246        0.0734        0.0954         0.0973     0.0606
     XGB_COX           raw        0.9143 0.0377    0.0174    0.0397    0.0443     0.0411        0.0011        0.0146        0.0380         0.0482     0.0490
     XGB_AFT           raw        0.9163 0.0731    0.0223    0.0660    0.0936     0.0973        0.0333        0.1386        0.2317         0.3113     0.1041
KM_REFERENCE           raw        0.5000 0.1226    0.0359    0.1324    0.1509     0.1328           NaN           NaN           NaN            NaN     0.2092
     XGB_COX isotonic_ipcw        0.9239 0.0358    0.0163    0.0378    0.0421     0.0387        0.0005        0.0061        0.0203         0.0463     0.0431
      COXNET isotonic_ipcw        0.9249 0.0382    0.0194    0.0425    0.0428     0.0391        0.0007        0.0069        0.0223         0.0456     0.0443
```

## Calibration Strategy
Per-horizon IPCW-weighted isotonic regression, fit on VALIDATION only. Censored-before-horizon rows get weight 0; the rest are weighted by 1/Ĝ(min(T,h)) where Ĝ is the TRAIN censoring-time Kaplan-Meier. Cross-horizon monotonicity re-imposed by cumulative max. TEST reliability curves are never used to adjust the maps.

## Calibration Results
```
  model  horizon  raw_brier  calibrated_brier  raw_cal_error  calibrated_cal_error  ranking_changed
XGB_COX       30     0.0174            0.0163         0.0011                0.0005            False
XGB_COX       60     0.0397            0.0378         0.0146                0.0061            False
XGB_COX       90     0.0443            0.0421         0.0380                0.0203            False
XGB_COX      120     0.0411            0.0387         0.0482                0.0463            False
 COXNET       30     0.0242            0.0194         0.0246                0.0007            False
 COXNET       60     0.0515            0.0425         0.0734                0.0069            False
 COXNET       90     0.0517            0.0428         0.0954                0.0223            False
 COXNET      120     0.0461            0.0391         0.0973                0.0456            False
```
Champion TEST calibration error — @30 0.0043 (GOOD), @60 0.0347 (MODERATE), @90 0.0612 (MODERATE), @120 0.0685 (MODERATE). Project diagnostic thresholds: <0.03 GOOD · 0.03–0.07 MODERATE · >0.07 POOR.

## Ensemble Experiment
Top-2 by VALIDATION composite: ['XGB_COX', 'COXNET']. Best weight on XGB_COX = 0.6; selected (IBS gain ≥1%, calibration not worse).

## Final Frozen Configuration
```
{
  "model_family": "ENSEMBLE[XGB_COX+COXNET]",
  "feature_set": "SET_D_TARGET_SPECIFIC_SURVIVAL",
  "calibration_method": "isotonic_ipcw",
  "ensemble_weights": {
    "XGB_COX": 0.6,
    "COXNET": 0.4
  },
  "horizons": [
    30,
    60,
    90,
    120
  ],
  "coxnet": {
    "l1_ratio": 0.1,
    "alpha": 0.0761984562022139
  },
  "xgb_cox": {
    "eta": 0.05858701717404125,
    "max_depth": 6,
    "min_child_weight": 18.347422429608567,
    "subsample": 0.6567488078997371,
    "colsample_bytree": 0.8475429989649401,
    "gamma": 4.79268782658841,
    "reg_alpha": 0.001688830288572431,
    "reg_lambda": 0.08219888648531636,
    "n_estimators": 603
  },
  "xgb_aft": {
    "eta": 0.03572924815064539,
    "max_depth": 4,
    "min_child_weight": 5.531976021844972,
    "subsample": 0.7840932169897824,
    "colsample_bytree": 0.9654835850702895,
    "gamma": 0.005456959738945276,
    "reg_alpha": 4.334707480459824,
    "reg_lambda": 15.876430367525316,
    "n_estimators": 539,
    "dist": "normal",
    "scale": 0.5
  },
  "random_seed": 42
}
```

## Final Test
```
                   model   calibration  c_index  ipcw_c_index    ibs  brier_30  brier_60  brier_90  brier_120  auc_30  auc_60  auc_90  auc_120
            KM_REFERENCE           raw   0.5000        0.5000 0.1167    0.0148    0.0901    0.1352     0.1527  0.5000  0.5000  0.5000   0.5000
            COX_BASELINE           raw   0.8616        0.8950 0.0570    0.0110    0.0484    0.0617     0.0685  0.9642  0.9369  0.9360   0.9235
                  COXNET           raw   0.8702        0.9073 0.0513    0.0101    0.0423    0.0536     0.0601  0.9733  0.9514  0.9469   0.9313
                 XGB_COX isotonic_ipcw   0.8696        0.9085 0.0507    0.0094    0.0421    0.0515     0.0586  0.9590  0.9537  0.9489   0.9317
                 XGB_AFT           raw   0.8825        0.9126 0.0475    0.0104    0.0424    0.0476     0.0541  0.9741  0.9522  0.9551   0.9419
ENSEMBLE[XGB_COX+COXNET] isotonic_ipcw   0.8780        0.9131 0.0488    0.0093    0.0404    0.0503     0.0572  0.9735  0.9555  0.9507   0.9352
                     RSF           raw   0.8791        0.9127    NaN       NaN       NaN       NaN        NaN     NaN     NaN     NaN      NaN
```

## Baseline vs Advanced
```
      metric  cox_baseline  advanced_champion  absolute_delta  relative_delta verdict
ipcw_c_index        0.8950             0.9131          0.0181          0.0203  better
         ibs        0.0570             0.0488         -0.0083          0.1449  better
    brier_90        0.0617             0.0503         -0.0114          0.1847  better
      auc_90        0.9360             0.9507          0.0147          0.0157  better
cal_error_90        0.0683             0.0612         -0.0071          0.1043  better
```

## Horizon Metrics
```
 horizon  brier    auc  cal_error  km_reference_risk
      30 0.0093 0.9735     0.0043             0.0485
      60 0.0404 0.9555     0.0347             0.2465
      90 0.0503 0.9507     0.0612             0.3936
     120 0.0572 0.9352     0.0685             0.5059
     180 0.0627 0.8850        NaN             0.6602
```

## Risk Groups
Thresholds from VALIDATION 90-day-risk terciles → TEST.
```
risk_group    n  events  censored  event_rate_by_90d  km_median_days
       LOW 2301     259      2042             0.0007           226.4
    MEDIUM 1228     427       801             0.1211           164.8
      HIGH  941     596       345             0.7090            63.5
```
HIGH vs LOW logrank p 1.91e-303; separation holds.

## Grouped Motorcycle Evaluation
```
      metric  estimate  ci_low  ci_high bootstrap_unit  n_replicates
ipcw_c_index    0.9131  0.9052   0.9204  motorcycle_id           500
         ibs    0.0412  0.0379   0.0447  motorcycle_id           500
    brier_90    0.0501  0.0454   0.0547  motorcycle_id           500
      auc_90    0.9508  0.9439   0.9585  motorcycle_id           500
cal_error_90    0.0641  0.0499   0.0788  motorcycle_id           500
```
Resampling unit = motorcycle_id, 500 replicates.

## Temporal Generalization
```
      metric  validation   test  degradation
ipcw_c_index      0.9320 0.9131      -0.0189
         ibs      0.0352 0.0488       0.0136
    brier_90      0.0408 0.0503       0.0095
      auc_90      0.9679 0.9507      -0.0172
cal_error_90      0.0182 0.0612       0.0430
```
IPCW-C drift VAL→TEST +0.019 → **STABLE**.

## Segment Analysis
```
    segment_type segment_value    n  events  censor_rate  ipcw_c  brier_90  auc_90  calibration_error_90       note
     history_bin           2-3 1085     245        0.774  0.9501    0.0235  0.9853                0.1086           
     history_bin            4+ 1802     719        0.601  0.8498    0.0847  0.9009                0.0750           
     history_bin           0-1 1583     318        0.799  0.9342    0.0296  0.9640                0.0134           
           brand        Yamaha  404     127        0.686  0.8384    0.0747  0.8743                0.0761           
           brand       Mondial  805     351        0.564  0.8661    0.0837  0.9232                0.0869           
           brand           TVS  431      58        0.865  0.9829    0.0039  0.9979                0.0395           
           brand         Honda 1480     321        0.783  0.9349    0.0284  0.9674                0.0399           
           brand        CFMOTO  164      20        0.878     NaN    0.0000     NaN                0.0001           
           brand          Kuba  461     211        0.542  0.8059    0.1284  0.8544                0.1191           
           brand         Bajaj  246      29        0.882  0.9880    0.0046  0.9980                0.0096           
           brand           RKS  266     125        0.530  0.8609    0.0666  0.9397                0.0412           
           brand           SYM  123      33        0.732  0.9243    0.0444  0.9637                0.0547           
           brand         KYMCO   59       7        0.881     NaN       NaN     NaN                   NaN LOW_SAMPLE
riding_intensity          HIGH 1810     928        0.487  0.8064    0.1195  0.8604                0.0801           
riding_intensity           LOW  993      62        0.938  0.7652    0.0021  0.6813                0.0026           
riding_intensity        MEDIUM 1667     292        0.825  0.8779    0.0039  0.9598                0.0454           
      event_type      CENSORED 3188       0        1.000     NaN       NaN     NaN                   NaN LOW_SAMPLE
      event_type      PERIODIC 1160    1160        0.000  0.8949    0.0854  0.9629                0.0597           
      event_type        REPAIR   91      91        0.000  0.8805    0.1074  0.9900                0.2454           
```
history depth best 2-3 / worst 4+; brand best Bajaj / worst Kuba.

## Feature Importance
XGB_COX top-10: current_primary_trigger_task_ENGINE_OIL_CHANGE, riding_intensity_HIGH, annual_km_baseline, days_since_previous_service, is_fleet_customer, engine_displacement_cc, customer_type_INDIVIDUAL, cooling_type_AIR, policy_interval_km, services_last_365d. `v2_advanced_feature_importance.csv`. Synthetic predictive association — not causal.

## Runtime / Inference
Champion latency — 1 pred 3.66 ms, 100 preds 115.73 ms, 1000 preds 1144.99 ms (CPU). Production inference feasible: **True**.

## V1 vs V2 Diagnostic
V1 final predictions unavailable in outputs/ — V1/V2 days comparison skipped. V2 value is probability + censored-episode usage, not point days.

## FAST vs FULL
```
      metric   fast   full  rel_change direction
ipcw_c_index 0.9126 0.9131      0.0005      flat
         ibs 0.0495 0.0488      0.0148  improved
    brier_90 0.0502 0.0503     -0.0021      flat
      auc_90 0.9512 0.9507     -0.0005      flat
cal_error_90 0.0668 0.0612      0.0839  improved
```
FULL run: 3 temporal folds · 120/120 complete XGB-Cox/AFT Optuna trials · 500 grouped bootstrap reps.

## Limitations
- Synthetic v1.3; no real-fleet validation. Model status: SYNTHETICALLY VALIDATED.
- FULL run.
- VAL/TEST ~70% censored → wide CIs; 180/365-day support weak (diagnostic only).
- Time split, not motorcycle split; recurrent episodes → grouped CIs used, residual dependence remains.
- scikit-survival RSF `predict_survival_function` does not scale here → RSF is ranking-only.
- XGB survival:cox probabilities depend on a Breslow baseline estimated on TRAIN (PH assumption).
- scikit-survival pins scikit-learn 1.5.x in this env.

## Final V2 Verdict
**STRONG IMPROVEMENT** vs baseline · **Final V2 signal: STRONG** · calibration@90 MODERATE · temporal STABLE · **V2 MODELING COMPLETE**.

## Recommendation
notebooks/16_v2_production_packaging.ipynb — V2 production packaging + API integration. Score-chasing is explicitly out of scope — do not auto-open nb16 to chase metrics.
