# RideBase V2 Survival Baseline

_Notebook 14 · dataset v1.3.0 (frozen) · seed 42 · FAST_MODE (provisional) · input hash `dfc4ee1b266850dd`_

## Executive Summary

First leakage-safe time-to-next-service survival baselines on all **41,518** v1.3 episodes (28,153 events / 13,365 right-censored). Kaplan-Meier reference vs Cox PH (CoxPH(alpha=1.0 ridge)) vs Random Survival Forest (25 trees, fit on a 8,000-row stratified TRAIN subsample — scikit-survival RSF does not scale to full TRAIN here). Champion (VALIDATION-selected): **COX** on **SET_A_COMPACT**. TEST — IPCW C-index 0.895, IBS 0.058, Brier@90 0.060, AUC@90 0.936; calibration@90 **MODERATE**. Cox>KM True, RSF>KM True, RSF>Cox False. **Verdict: SURVIVAL SIGNAL STRONG.**

## Objective
First reliable V2 baselines with correct censoring, calibrated 30/60/90/120-day service probabilities, motorcycle-grouped evaluation. Not a tuning run (nb15).

## Survival Dataset
`v2_survival_modeling_table.parquet` — 41,518 episodes × 146 leakage-safe features. Censoring: TRAIN 21.0% · VAL 70.5% · TEST 71.3%.

## Event and Censoring Contract
`event_observed=1` → real next service before the split admin cutoff; `=0` → right-censored at the cutoff. Censored rows used natively by every model.

## Recurrent Episodes
Bootstrap unit = `motorcycle_id`. FIRST-vs-FULL TEST C-index gap 0.022 → concern **MODERATE**.
```
            subset    n  events  c_index  ipcw_c_index    ibs  brier_90  auc_90
         FULL_TEST 4470    1282   0.8616        0.8950 0.0576    0.0599   0.936
FIRST_EPISODE_TEST  857     161   0.8837        0.9107    NaN       NaN     NaN
 LAST_EPISODE_TEST 3188       0      NaN           NaN    NaN       NaN     NaN
```

## Evaluation Strategy
Validation-frozen config; TEST once. Harrell + Uno/IPCW C-index (censoring dist from TRAIN), Brier@30/60/90/120, IBS, time-dependent AUC, 10-bin KM-adjusted calibration, motorcycle-grouped bootstrap (40 reps).

## Kaplan-Meier Reference
TRAIN S(t). 1−S: @30 0.05, @60 0.25, @90 0.39, @120 0.51. Median 118 d. Same curve for every row.

## Cox PH Baseline
CoxPH(alpha=1.0 ridge); fit 4.9s; convergence PASS. Top ↑hazard: annual_km_baseline, recent_90d_km, riding_intensity_HIGH, category_SCRAMBLER, category_EV_SCOOTER. `v2_cox_coefficients.csv`.

## Random Survival Forest
25 trees, min_samples_leaf 150, max_depth 6, max_features sqrt, max_samples 0.35; **fit on a 8,000-row stratified TRAIN subsample** (event/censor ratio preserved) because sksurv RSF fit/predict does not scale to 32k rows on this machine; KM + Cox use full TRAIN, all evaluation is on full VALIDATION / TEST. fit 2.7s. Survival function (Brier / IBS / calibration) unavailable for RSF — ranking metrics only. Top permutation-importance features: historical_interval_days_median, days_since_previous_service, annual_km_baseline, recent_90d_km, riding_intensity_HIGH, engine_displacement_cc, policy_interval_km, riding_intensity_LOW.

## Validation Results
```
       model  c_index  ipcw_c_index    ibs  brier_30  brier_60  brier_90  brier_120  auc_90
KM_REFERENCE   0.5000        0.5000 0.1223    0.0337    0.1345    0.1499     0.1313  0.5000
         COX   0.9073        0.9092 0.0546    0.0240    0.0656    0.0604     0.0514  0.9535
         RSF   0.9169        0.9182    NaN       NaN       NaN       NaN        NaN  0.9520
```
Feature set: **SET_A_COMPACT**.

## Test Results
```
       model  c_index  ipcw_c_index    ibs  brier_30  brier_60  brier_90  brier_120  auc_30  auc_60  auc_90  auc_120
KM_REFERENCE   0.5000        0.5000 0.1201    0.0158    0.0937    0.1381     0.1573  0.5000  0.5000  0.5000   0.5000
         COX   0.8616        0.8950 0.0576    0.0118    0.0494    0.0599     0.0695  0.9642  0.9369  0.9360   0.9235
         RSF   0.8690        0.9035    NaN       NaN       NaN       NaN        NaN  0.9764  0.9496  0.9416   0.9212
```

## C-Index
Harrell TEST — KM 0.500 · Cox 0.862 · RSF 0.869. IPCW — Cox 0.895 · RSF 0.903. KM C-index ≈ 0.5 by construction.

## Integrated Brier Score
TEST IBS — KM 0.1201 · Cox 0.0576 · RSF nan (lower better).

## Horizon Brier Scores
```
model       COX  KM_REFERENCE
horizon                      
30       0.0118        0.0158
60       0.0494        0.0937
90       0.0599        0.1381
120      0.0695        0.1573
180      0.0687        0.1248
```

## Time-Dependent AUC
```
model       COX  KM_REFERENCE     RSF
horizon                              
30       0.9642           0.5  0.9764
60       0.9369           0.5  0.9496
90       0.9360           0.5  0.9416
120      0.9235           0.5  0.9212
180      0.8773           0.5  0.8746
```

## Calibration
10-bin KM-adjusted, COX. @90 mean|pred−obs| 0.0686 → **MODERATE**. figs 06–09.

## Risk Groups
Thresholds from VALIDATION 90-day-risk terciles → TEST.
```
risk_group    n  events  event_rate_by_90d  km_median_days
       LOW 2278     254             0.0023           226.1
    MEDIUM 1385     527             0.1825           159.4
      HIGH  807     501             0.6957            63.1
```
HIGH vs LOW logrank p 1.08e-265; separation holds.

## Motorcycle-Grouped Evaluation
```
model   metric  estimate  ci_low  ci_high bootstrap_unit  n_replicates
  COX  c_index    0.8603  0.8511   0.8710  motorcycle_id            40
  COX      ibs    0.0502  0.0456   0.0536  motorcycle_id            40
  COX brier_90    0.0604  0.0554   0.0647  motorcycle_id            40
```

## Segment Analysis
```
    segment_type  segment    n  events  censor_rate  c_index  brier_90  auc_90       note
     history_bin      2-3 1085     245        0.774   0.8650       NaN  0.9766           
     history_bin       4+ 1802     719        0.601   0.7945       NaN  0.8794           
     history_bin      0-1 1583     318        0.799   0.8936       NaN  0.9555           
           brand   Yamaha  404     127        0.686   0.7691       NaN  0.8413           
           brand  Mondial  805     351        0.564   0.8143       NaN  0.9021           
           brand      TVS  431      58        0.865   0.7767       NaN  0.9969           
           brand    Honda 1480     321        0.783   0.8711       NaN  0.9530           
           brand   CFMOTO  164      20        0.878   0.5887       NaN     NaN           
           brand     Kuba  461     211        0.542   0.7556       NaN  0.8215           
           brand    Bajaj  246      29        0.882   0.9082       NaN  0.9960           
           brand      RKS  266     125        0.530   0.8429       NaN  0.9249           
           brand      SYM  123      33        0.732   0.8802       NaN  0.9640           
           brand    KYMCO   59       7        0.881      NaN       NaN     NaN LOW_SAMPLE
riding_intensity     HIGH 1810     928        0.487   0.7519       NaN  0.8261           
riding_intensity      LOW  993      62        0.938   0.6846       NaN  0.5515           
riding_intensity   MEDIUM 1667     292        0.825   0.7403       NaN  0.8689           
      event_type CENSORED 3188       0        1.000      NaN       NaN     NaN LOW_SAMPLE
      event_type PERIODIC 1160    1160        0.000   0.8487       NaN  0.9465           
      event_type   REPAIR   91      91        0.000   0.8420       NaN  0.9707           
```
history depth best 0-1 / worst 4+; brand best Bajaj / worst CFMOTO.

## Temporal Generalization
TRAIN/VAL/TEST survival curves shift materially later (nb13 KM medians ~118 / ~174 / ~203 d, fig 16). VAL/TEST metrics reflect model quality + this drift + ~70% censoring; 180-day numbers are diagnostic only.

## Feature Importance
RSF top-10: historical_interval_days_median, days_since_previous_service, annual_km_baseline, recent_90d_km, riding_intensity_HIGH, engine_displacement_cc, policy_interval_km, riding_intensity_LOW, previous_service_count, brand_Kuba

## Cox Hazard Ratios
```
               feature  coefficient  hazard_ratio
    annual_km_baseline       0.5367        1.7104
         recent_90d_km       0.4808        1.6174
 riding_intensity_HIGH       0.3365        1.4001
    category_SCRAMBLER       0.3123        1.3666
previous_service_count      -0.3020        0.7393
   category_EV_SCOOTER       0.2996        1.3493
         brand_Mondial       0.2764        1.3184
  riding_intensity_LOW      -0.2755        0.7592
    policy_interval_km      -0.2698        0.7635
          brand_Yamaha      -0.2402        0.7865
            brand_Kuba       0.2324        1.2617
      category_TOURING      -0.2274        0.7966
```
Synthetic predictive association — not causal.

## Limitations
- **scikit-survival `RandomSurvivalForest.predict_survival_function` does not scale on this dataset** (>8 min for 600 rows on macOS — joblib/loky deadlock). RSF is reported on ranking metrics (C-index, time-dependent AUC) only; its Brier / IBS / calibration are `n/a`. Kaplan-Meier and Cox give full probability metrics. nb15 will use faster survival libraries (GradientBoostingSurvival / XGBoost survival) for calibrated RSF-class probabilities.
- Synthetic v1.3; no real-fleet validation; FAST_MODE numbers provisional.
- VAL/TEST ~70% censored → wide CIs, weak 180/365-day support.
- Time split, not motorcycle split; recurrent episodes → grouped CIs used, residual dependence remains.
- KM reference C-index undefined (constant risk), shown as ≈0.5.
- scikit-survival pins scikit-learn 1.5.x in this env (V1 artifacts were 1.6.1 — not reloaded here).

## Baseline Verdict
**SURVIVAL SIGNAL STRONG.** Cox>KM True · RSF>KM True · RSF>Cox False. Ready for advanced survival modeling: **YES**.

## Recommendation for Notebook 15
`notebooks/15_v2_survival_advanced.ipynb` — tuned RSF, Gradient Boosting Survival, XGBoost survival (AFT / Cox), survival ensemble, calibration improvement; keep the frozen split and motorcycle-grouped evaluation.
