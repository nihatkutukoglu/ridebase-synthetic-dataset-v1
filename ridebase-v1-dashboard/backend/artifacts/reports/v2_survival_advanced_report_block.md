# RideBase V2 Advanced Survival

1. Dataset version: v1.3.0 (frozen)
2. Survival rows: 41,518
3. Events: 28,153
4. Censored: 13,365
5. Features used: 117 (SET_D_TARGET_SPECIFIC_SURVIVAL); encoded dims 243
6. Primary horizons: [30, 60, 90, 120] days (180 diagnostic)
7. Baseline Cox validation IPCW C-index: 0.909
8. Baseline Cox validation IBS: 0.0546
9. Baseline Cox validation Brier @90: 0.0614
10. Baseline Cox validation calibration @90: 0.1036 (POOR)
11. CoxNet validation IPCW C-index: 0.925
12. CoxNet validation IBS: 0.0461
13. CoxNet Brier @90: 0.0517
14. CoxNet calibration @90: 0.0954 (POOR)
15. XGB-Cox validation IPCW C-index: 0.914
16. XGB-Cox validation IBS: 0.0377
17. XGB-Cox Brier @90: 0.0443
18. XGB-Cox calibration @90: 0.0380 (MODERATE)
19. XGB-AFT validation IPCW C-index: 0.916
20. XGB-AFT validation IBS: 0.0731
21. XGB-AFT Brier @90: 0.0936
22. XGB-AFT calibration @90: 0.2317 (POOR)
23. RSF advanced validation IPCW C-index: 0.927
24. RSF advanced probability metrics available?: YES
25. Gradient Boosting Survival status: SKIPPED_RUNTIME
26. Best raw survival model: XGB_COX
27. Best calibrated survival model: XGB_COX (isotonic_ipcw)
28. Calibration method: per-horizon IPCW-weighted isotonic (fit on VALIDATION only)
29. Ensemble tested?: YES
30. Ensemble selected?: YES (w=0.6)
31. FINAL selected model: ENSEMBLE[XGB_COX+COXNET]
32. Final feature set: SET_D_TARGET_SPECIFIC_SURVIVAL
33. Final hyperparameters: coxnet={'l1_ratio': 0.1, 'alpha': 0.0761984562022139} | xgb_cox={'eta': 0.05858701717404125, 'max_depth': 6, 'min_child_weight': 18.347422429608567, 'subsample': 0.6567488078997371, 'colsample_bytree': 0.8475429989649401, 'gamma': 4.79268782658841, 'reg_alpha': 0.001688830288572431, 'reg_lambda': 0.08219888648531636, 'n_estimators': 603} | xgb_aft={'eta': 0.03572924815064539, 'max_depth': 4, 'min_child_weight': 5.531976021844972, 'subsample': 0.7840932169897824, 'colsample_bytree': 0.9654835850702895, 'gamma': 0.005456959738945276, 'reg_alpha': 4.334707480459824, 'reg_lambda': 15.876430367525316, 'n_estimators': 539, 'dist': 'normal', 'scale': 0.5}
34. TEST IPCW C-index: 0.913
35. TEST Harrell C-index: 0.878
36. TEST IBS: 0.0488
37. TEST Brier @30: 0.0093
38. TEST Brier @60: 0.0404
39. TEST Brier @90: 0.0503
40. TEST Brier @120: 0.0572
41. TEST AUC @30: 0.973
42. TEST AUC @60: 0.955
43. TEST AUC @90: 0.951
44. TEST AUC @120: 0.935
45. TEST calibration error @30: 0.0043
46. TEST calibration error @60: 0.0347
47. TEST calibration error @90: 0.0612
48. TEST calibration error @120: 0.0685
49. Calibration @30 verdict: GOOD
50. Calibration @60 verdict: MODERATE
51. Calibration @90 verdict: MODERATE
52. Calibration @120 verdict: MODERATE
53. Baseline Cox TEST IBS: 0.0570
54. Advanced TEST IBS: 0.0488
55. IBS relative improvement %: +14.5%
56. Baseline Cox TEST Brier @90: 0.0617
57. Advanced TEST Brier @90: 0.0503
58. Brier @90 relative improvement %: +18.5%
59. Baseline Cox TEST IPCW C-index: 0.895
60. Advanced TEST IPCW C-index: 0.913
61. C-index gain: +0.018
62. High-risk TEST group serviced by 90d: 70.9% (n=941)
63. Medium-risk: 12.1% (n=1228)
64. Low-risk: 0.1% (n=2301)
65. Risk-group separation: clear (HIGH-vs-LOW logrank p=1.9e-303)
66. Grouped bootstrap IPCW-C CI: 0.9131 [0.9052, 0.9204]
67. Grouped bootstrap IBS CI: 0.0412 [0.0379, 0.0447]
68. Grouped bootstrap Brier@90 CI: 0.0501 [0.0454, 0.0547]
69. Grouped bootstrap calibration@90 CI: 0.0641 [0.0499, 0.0788]
70. FULL vs FIRST_EPISODE result: FULL C-index 0.878 vs FIRST 0.883 (n=857); LAST episode n/a (n=3188)
71. Recurrent episode concern: LOW
72. Best history-depth segment: 2-3
73. Worst history-depth segment: 4+
74. Best brand: Bajaj
75. Worst brand: Kuba
76. Top 10 final features: ['current_primary_trigger_task_ENGINE_OIL_CHANGE', 'riding_intensity_HIGH', 'annual_km_baseline', 'days_since_previous_service', 'is_fleet_customer', 'engine_displacement_cc', 'customer_type_INDIVIDUAL', 'cooling_type_AIR', 'policy_interval_km', 'services_last_365d']
77. Validation → TEST degradation: IPCW-C -0.019, IBS +0.0136, cal@90 +0.0430
78. Temporal generalization verdict: STABLE
79. Single prediction latency: 3.66 ms
80. 100 prediction latency: 115.73 ms
81. 1000 prediction latency: 1144.99 ms
82. Production inference feasible?: YES
83. Leakage audit: PASS (145 candidate features; next_*/censor*/future_* excluded)
84. Calibration leakage audit: PASS (isotonic maps fit on VALIDATION only; TEST never used to tune)
85. Split integrity: PASS {'TRAIN': 32203, 'VALIDATION': 4845, 'TEST': 4470}
86. Reproducibility: XGB refit seed 42 max|Δ|=0.00e+00 (PASS)
87. QA: ALL PASS
88. Notebook errors: 0 (this run completed)
89. Final model artifact: models/v2_advanced_champion.joblib + models/v2_advanced_config.json
90. Calibrator artifact: models/v2_advanced_calibrator.joblib
91. Prediction output: outputs/v2_advanced_test_predictions.parquet (4470, 21)
92. Report: reports/v2_survival_advanced_report.md
93. Figures: 19 in reports/figures/v2_survival_advanced/
94. Tables: 22
95. Advanced survival verdict: STRONG IMPROVEMENT
96. Final V2 signal: STRONG
97. V2 modeling status: V2 MODELING COMPLETE
98. Control Center updated: YES (stage ADVANCED_MODELING_COMPLETE, changelog nb15)
99. Published Artifact URL: https://claude.ai/code/artifact/3366dcd0-0e51-4f81-ba96-9d24253402bc (republish after build.py)
100. Recommended next step: notebooks/16_v2_production_packaging.ipynb — V2 production packaging + API integration