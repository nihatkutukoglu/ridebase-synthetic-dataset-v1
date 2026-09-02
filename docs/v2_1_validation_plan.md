# V2.1 Validation Plan

## Ordered gates

1. Source-schema contract and frozen-file integrity.
2. Landmark/target leakage, censoring and current-odometer QA.
3. Synthetic-world sanity: distributions, due-pressure direction, customer and
   usage overlap, service frequency, failures, censoring and construction
   artifacts.
4. Only after gate 3 passes: policy baseline, simple Cox survival baseline,
   then an advanced model if validation metrics justify it.
5. Temporal and unseen-motorcycle evaluation, calibration comparison and
   metamorphic behavior audit.
6. Versioned API and experimental UI; no replacement of `/api/v2/*`.

## Split contract

The primary split is temporal: train through 2025-06-30, validation through
2025-12-31 and test from 2026-01-01. A deterministic 15% motorcycle holdout is
excluded from training; its 2026 landmarks form a combined unseen-motorcycle
and out-of-time test. Random rows are never the main evidence, and TEST is not
used for model selection.

## Required model metrics

IPCW C-index, integrated Brier score, Brier and time-dependent AUC at each
supported horizon, calibration tables/curves, risk-bucket lift and threshold
analysis. Metrics are named precisely and never called “accuracy.” Calibration
candidates are selected on validation and checked for probability resolution
and plateaus.

## Required metamorphic behavior

The matrix in `ridebase-ml/reports/v2_1_metamorphic_tests.csv` covers km and
elapsed-time sensitivity, calendar invariance, usage, due vs not-due behavior,
same-input determinism, horizon monotonicity, exact-zero collapse, observation
artifacts and input validation.

## Current status

The source and landmark gates pass; the synthetic-world gate fails on overdue
direction and a severely overdue dead region. Modeling, calibration, V2.1
prediction routes and deployment are blocked until a new same-schema,
versioned synthetic event process passes this gate. Real-fleet validation
remains pending regardless of future synthetic results.
