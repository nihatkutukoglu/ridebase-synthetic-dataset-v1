# RideBase V2 Production Packaging

_Notebook 16 · dataset v1.3.0 (frozen) · packaging only, no training · model status SYNTHETICALLY VALIDATED · real-fleet validation PENDING_

## Executive Summary

The frozen FULL/FINAL V2 survival ensemble (**ENSEMBLE[XGB_COX+COXNET]**, weights {'XGB_COX': 0.6, 'COXNET': 0.4}, per-horizon IPCW-isotonic calibration) is packaged as a deterministic, read-only production inference service — `ridebase_ml.v2.V2SurvivalPredictor` — plus a FastAPI `/api/v2/*` surface and a real (non-placeholder) RideBase Control Center V2 module. No model was retrained. The production predictor reproduces nb15's TEST predictions **bit-for-bit** (max |Δrisk| = 5.0e-09, median exact, risk-group match 100%). Single-prediction latency 11.02 ms, 1000 in 1335.03 ms. Feature-contract audit: 50 READY / 66 DERIVABLE / 1 INERT, 0 synthetic-only blockers.

## Final V2 Model
- Ensemble: 60% XGBoost `survival:cox` (Breslow baseline `H0`) + 40% CoxNet (alpha 0.0762).
- Calibration: per-horizon IPCW-weighted isotonic, fit on VALIDATION only, applied per model before blending; cross-horizon monotonicity by cumulative max.
- Feature set: SET_D_TARGET_SPECIFIC_SURVIVAL — 117 raw features, 243 encoded dims.
- Horizons: [30, 60, 90, 120] days. Risk-group thresholds (VALIDATION 90d-risk terciles): low_max 0.000, medium_max 0.522.
- TEST metrics (nb15): IPCW-C 0.9131, IBS 0.0488, Brier@90 0.0503, AUC@90 0.9507, calibration@90 0.0612.

## Artifact Validation
```
                          artifact            sha256
       v2_advanced_champion.joblib 1a4241e35e612b2b…
   v2_advanced_preprocessor.joblib 348d6fbffc36d069…
v2_advanced_calibrator_full.joblib eba90102feac522e…
     v2_advanced_calibrator.joblib 25e09657aeec23e7…
           v2_advanced_config.json 85c737ea672d0fde…
           v2_feature_catalog.json e7b58b3a5770ae60…
            v2_coxnet_model.joblib 62a43cb61bf39081…
             v2_xgb_cox_model.json 63a8a9b67d6b1b89…
```
Guard: run_mode FULL / status FINAL / dataset 1.3.0 — PASS. Checksum verification on reload: VERIFIED_OK.

## Production Predictor
`ridebase_ml/v2/` — `loader.py` (artifact load + guard + checksums + metadata), `predictor.py` (`V2SurvivalPredictor.load()` / `.predict()` / `.predict_batch()`). Pipeline: input dict → leakage/schema validation → canonical 117-col row (training order; missing handled by the persisted preprocessor — **transform only, never fit**) → XGB-Cox S(t) + CoxNet S(t) → per-model isotonic calibration → weighted blend → risk_30/60/90/120, median_service_days (raw XGB-Cox curve, nb15 contract), risk_group_90d. Read-only shared state; safe for concurrent requests.

## Feature Contract
```
           count
status          
DERIVABLE     66
READY         50
INERT          1
```
`split` is the only INERT feature — a data-partition label that leaked into nb15's frozen feature set; it is constant in TRAIN, contributes ~0, and is set to a fixed sentinel at inference (all non-TRAIN values are OHE-equivalent, so golden parity holds). **Remove it when retraining on real data.** Full table: `v2_production_feature_contract.csv`.

## Real-Data Feature Mapping
`v2_real_data_feature_mapping.csv` — every model feature → expected RideBase source + transformation. 50 are 1:1 fields; 66 need a history/derivation pipeline (rolling km / service intervals / snapshot-date features); 0 have no real source.

## Ensemble Inference
Weights are read from `config.ensemble_weights` (not hard-coded): blend = 0.6·calib(S_xgbcox) + 0.4·calib(S_coxnet). XGB-Cox S(t) = exp(−H0(t)·HR(x)) with the persisted 1000-day Breslow `H0`.

## Calibration Inference
The nb15 calibrator artifact carried only the champion (XGB_COX) maps. This notebook **reconstructs** the CoxNet maps from frozen VALIDATION with nb15's exact `ipcw_iso_fit` recipe (drop censored-before-h; weight 1/Ĝ(min(T,h)); `IsotonicRegression(0,1,clip)`), deterministic, no model fit — and re-saves `v2_advanced_calibrator_full.joblib` = {XGB_COX:[30, 60, 90, 120], COXNET:[30, 60, 90, 120]}. Correctness proven by the golden test.

## Probability QA
All 4470 TEST predictions: 0 ≤ p ≤ 1 (PASS), P30 ≤ P60 ≤ P90 ≤ P120 (PASS). Deterministic re-run max |Δ| = 0e+00. The predictor raises rather than return a contract-violating result.

## API Integration
Added to the existing `ridebase-v1-dashboard/backend` (no new service): `GET /api/v2/model/info`, `GET /api/v2/features`, `GET /api/v2/metrics`, `GET /api/v2/sample`, `POST /api/v2/predict`, `POST /api/v2/predict/batch`, plus `POST /api/predict/service` (V1+V2 combined) and `v2_*` fields on `/health`. Bundle is loaded once at startup. `/admin/reload` stays disabled unless `APP_ENV != production`.

## Golden Prediction Test
```
  snapshot_id  notebook_p30  notebook_p60  notebook_p90  notebook_p120  api_p30  api_p60  api_p90  api_p120    max_delta status
SNP_SVC000004           0.0      0.003392      0.044954       0.156925      0.0 0.003392 0.044954  0.156925 4.000000e-09   PASS
SNP_SVC000020           0.0      0.000000      0.000000       0.000000      0.0 0.000000 0.000000  0.000000 0.000000e+00   PASS
SNP_SVC000070           0.0      0.003392      0.045325       0.112040      0.0 0.003392 0.045325  0.112040 2.000000e-09   PASS
SNP_SVC000071           0.0      0.003392      0.014355       0.095802      0.0 0.003392 0.014355  0.095802 4.000000e-09   PASS
SNP_SVC000076           0.0      0.000000      0.000000       0.018195      0.0 0.000000 0.000000  0.018195 2.000000e-09   PASS
```
Full TEST set (4470 rows): max |Δrisk| = 5.00e-09, max |Δ median_days| = 0.00e+00, risk-group match 1.0000. `v2_production_golden_prediction_test.csv`. **Notebook inference == production inference.**

## Latency
1 row 11.02 ms · 100 rows 199.36 ms · 1000 rows 1335.03 ms (CPU). nb15 reference ≈ single 3.7 ms / 1000 ≈ 1.1 s — the production wrapper adds negligible overhead.

## Control Center Integration
The V2 module is no longer a placeholder: OVERVIEW / HORIZONS / CALIBRATION / RISK GROUPS / MODELS / FEATURES / SEGMENTS / LIMITATIONS render from the manifest `v2` block and nb15 figures; LIVE PREDICTION calls `/api/v2/predict` when the API is reachable (no fake fallback). Changelog gains a V2 PRODUCTION entry.

## Production Readiness
- Deterministic, checksum-verified, transform-only inference: **ready**.
- Golden parity with the notebook: **PASS**.
- Leakage / invalid-input / OOD guards: **PASS**.
- Latency well within interactive budget: **ready**.
- Feature pipeline for *real* data: the 117-feature derivation layer is specified (`v2_real_data_feature_mapping.csv`) but not built — that is the real-data migration phase.

## Real Fleet Validation Gap
The model has only ever seen RideBase Synthetic Dataset v1.3. Every surface says `REAL FLEET VALIDATION: PENDING`. The strong synthetic numbers are **not** a claim about real-world performance. A shadow-deployment / backtest on real service history is required before any accuracy claim.

## Limitations
- Synthetic-only validation; calibration@120 is MODERATE (borderline); ~70% censoring in VAL/TEST.
- `split` feature is inert dead weight in the frozen model (documented; remove on real-data retrain).
- median_service_days comes from the raw XGB-Cox curve (nb15 contract), not the calibrated blend.
- Real-data feature derivation pipeline is designed, not implemented.
- scikit-survival pins scikit-learn 1.5.x in this environment.

## Final Verdict
**READY FOR PILOT DEPLOYMENT** — application/API/Control-Center integration complete; model is SYNTHETICALLY VALIDATED, real-fleet validation PENDING. Next: real-data feature pipeline + shadow backtest (not a modeling task).
