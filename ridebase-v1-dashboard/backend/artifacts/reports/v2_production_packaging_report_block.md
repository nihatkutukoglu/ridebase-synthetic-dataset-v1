# RideBase V2 Production Packaging

1. Dataset version: v1.3.0 (frozen)
2. V2 run mode: FULL (config status FINAL)
3. V2 status: MODEL SYNTHETICALLY VALIDATED · real-fleet validation PENDING
4. Final model: ENSEMBLE[XGB_COX+COXNET]
5. Ensemble weights: {'XGB_COX': 0.6, 'COXNET': 0.4} (from config, not hard-coded)
6. Calibration: per-horizon IPCW-weighted isotonic (VALIDATION-fit; reconstructed + verified)
7. Horizons: [30, 60, 90, 120] days
8. Feature count: 117 raw (243 encoded)
9. Champion artifact loaded: YES (v2_advanced_champion.joblib)
10. Calibrator loaded: YES (v2_advanced_calibrator_full.joblib — XGB_COX + COXNET x [30, 60, 90, 120])
11. Preprocessor loaded: YES (transform-only; fit never called)
12. Config loaded: YES (run_mode=FULL, status=FINAL)
13. Checksums: 8 SHA256 recorded in v2_production_bundle_manifest.json; reload verification VERIFIED_OK
14. Production-derivable features (READY, 1:1): 50
15. Derivable with pipeline (DERIVABLE): 66
16. Missing real-data source: 0
17. Synthetic-only blockers: 0 (INERT/drop-safe: 1 — 'split' only)
18. Predictor created: YES — ridebase_ml.v2.V2SurvivalPredictor
19. Prediction output schema: risk_30d, risk_60d, risk_90d, risk_120d, median_service_days, risk_group_90d (+ raw_ensemble_risk, warnings)
20. Probability bounds: PASS (0 ≤ p ≤ 1 on all 4470 TEST rows)
21. Probability monotonicity: PASS (P30 ≤ P60 ≤ P90 ≤ P120)
22. Deterministic inference: PASS (re-run max |Δ| = 0e+00)
23. Golden prediction rows: 4470 (full TEST set; 5 shown in v2_production_golden_prediction_test.csv)
24. Maximum notebook-vs-production delta: risk 5.00e-09 · median_days 0.00e+00 · risk-group match 1.0000
25. Golden parity verdict: PASS
26. API endpoints added: /api/v2/model/info, /api/v2/features, /api/v2/metrics, /api/v2/sample, /api/v2/predict, /api/v2/predict/batch, /api/predict/service
27. /api/v2/predict working: YES (backend tests + smoke)
28. /api/v2/predict/batch working: YES (100 + 1000 rows)
29. /api/v2/model/info working: YES (artifact-driven metadata)
30. /health V2 status: v2_model_loaded / v2_calibrator_loaded / v2_config_loaded / v2_status fields added
31. Leakage request guard: PASS (6/6 rejected with 422/ValueError)
32. Feature-order guard: PASS (order fixed by frozen preprocessor; caller cannot set it)
33. Invalid-input validation: PASS (negative mileage / inf / non-numeric rejected)
34. OOD warning: PASS (p01–p99 breach surfaced in `warnings`, prediction still returned)
35. Single prediction latency: 11.02 ms
36. 100 prediction latency: 199.36 ms
37. 1000 prediction latency: 1335.03 ms
38. Backend tests: existing V1 suite unchanged
39. V2-specific tests: tests/test_v2_api.py (load, info, prediction, bounds, monotonicity, leakage, feature-order, determinism, batch, invalid-input, OOD, golden-parity)
40. Smoke test: scripts/smoke_v2_inference.py (health → info → sample → predict → bounds → monotonicity → determinism → batch → golden)
41. CI updated: V2 job added; missing FINAL artifact => FAIL in the production lane
42. Docker dependencies verified: xgboost / scikit-survival / scikit-learn / joblib in requirements; requirements-prod.txt added (inference-only)
43. Control Center V2 integrated: YES (module PRODUCTION_PACKAGED, not placeholder)
44. V2 Overview: 41,518 episodes / 13,365 censored used / IPCW-C 0.9131 / IBS 0.0488 / Brier@90 0.0503 / AUC@90 0.9507 — run FULL/FINAL
45. Horizon metrics: Brier + AUC + calibration per 30/60/90/120 from nb15 tables
46. Calibration view: nb15 calibration figures + verdicts {'30': 'GOOD', '60': 'MODERATE', '90': 'MODERATE', '120': 'MODERATE'}
47. Risk groups: LOW/MEDIUM/HIGH from v2_advanced_risk_groups.csv (real, no fake thresholds)
48. Live prediction: calls /api/v2/predict when reachable; no fake fallback
49. V1+V2 comparison: side-by-side view (V1 point days/km vs V2 probability-over-time) via /api/predict/service
50. Changelog: 'V2 survival model packaged for inference (nb16)' — PASS
51. Synthetic validation warning: shown on report, predictor response, manifest, API, Control Center
52. Real fleet validation: PENDING (unchanged everywhere)
53. Production feature mapping generated: v2_real_data_feature_mapping.csv (117 rows)
54. Production bundle manifest: models/v2_production_bundle_manifest.json (8 checksums)
55. Packaging report: reports/v2_production_packaging_report.md
56. README updated: YES (entry 16)
57. Notebook errors: 0 (this run completed)
58. QA: ALL PASS
59. Final packaging verdict: READY FOR PILOT DEPLOYMENT
60. Next step: real-data feature-derivation pipeline + shadow/backtest validation on real RideBase service history (separate phase; NOT a modeling task)