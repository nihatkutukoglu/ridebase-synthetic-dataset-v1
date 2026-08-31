# Executive Summary

RideBase V0 is a deterministic policy baseline on **Synthetic Dataset v1.2**. It is not a trained model and is not production validation. Production feasibility remains **BLOCKED** because no production extract is available.

# Baseline Definition

Model/group maintenance policies are matched to canonical tasks. The earliest calculable km/date/wear-mean due task triggers the next-service estimate. Main metrics use ACTIONABLE overdue handling (`max(horizon, 0)`); RAW negative horizons remain in prediction output.

# Data and Split

- Dataset version: 1.2.0
- Total snapshots: 41,518
- TEST snapshots: 7,691
- Authoritative split: `split_manifest.csv`
- No training/tuning was performed.

# Policy Coverage

- Motorcycle policy coverage: 100.00%
- Canonical tasks linked by active policy: 48
- Timing prediction coverage: 100.00%
- Task prediction coverage: 100.00%
- Most common unavailable reason: NONE — full timing coverage

# Next-Service Timing Results

TEST observed eligible targets only:

- Days MAE: 67.411
- Days Median AE: 57.848
- Days bias: -67.371 (early prediction direction)
- Within ±30 / ±60 / ±90 days: 17.32% / 51.98% / 74.56%
- Km MAE: 4515.312
- Km Median AE: 3981.500
- Km bias: -4514.333 (early prediction direction)
- Within ±1,000 / ±2,000 / ±5,000 km: 3.39% / 6.52% / 65.87%

# Next-Task Results

- Micro precision / recall / F1: 15.19% / 61.71% / 24.38%
- Macro F1: 14.50%
- Precision@3 / Recall@3 / HitRate@3: 12.81% / 7.02% / 30.43%
- Subset exact match: 0.00%

Macro F1 is volatile for rare task classes. V0 intentionally does not predict unpredictable REPAIR/BREAKDOWN fault tasks; future multi-label models should improve recall without sacrificing precision.

# Segment Analysis

TEST segment metrics use minimum n=50. Small segments are excluded and must not support strong conclusions. See `v0_rule_baseline_segment_metrics.csv`.

# Censoring Handling

TEST: 2,622 observed, 5,069 right-censored. Censored rows are never converted to zero days/km and are excluded from MAE/MedAE and task-label evaluation.

# Error Analysis

The largest 20 day and km errors are exported with snapshot-safe usage/history attributes. Overall days bias is -67.371; km bias is -4514.333. Overdue, sparse history and high-usage cases are explicitly identifiable in outputs.

# Leakage Audit

PASS. Prediction inputs are snapshot-time features, policies/taxonomy, and completed task history at or before `snapshot_at`. Next-service and next-task targets enter only after prediction for evaluation.

# Limitations

- Results are synthetic v1.2 offline PoC results, not production performance.
- Production feasibility notebook remains BLOCKED.
- V0 is not designed to predict stochastic failure tasks.
- Maintenance policy quality directly controls baseline quality.
- Censored samples are excluded from classical regression metrics.
- First-history fallback uses observation start + initial mileage and cannot recover unknown pre-observation maintenance.
- Future models must use the same authoritative split and compare against V0.

# Comparison Target for Future Models

V1 Statistical / V2 Survival should primarily beat TEST days/km MAE and Median AE plus coverage/calibration; task models should beat TEST micro-F1 and Recall@3 while maintaining Precision@3.

# Final Verdict

V0 is ready as a deterministic, leakage-audited synthetic benchmark. It does not close Issue #579 production validation.
