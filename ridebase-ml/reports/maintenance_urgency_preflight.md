# RideBase Maintenance Urgency Score — Preflight Report

**Date:** 2026-09-04  
**Starting Commit:** `f7eafa2` (`HEAD == origin/main`, working tree clean)  
**Branch:** `main`  
**Divergence:** `0 0` (in sync with remote)

---

## 1. Baseline Test Suite Verification

All baseline suites passed cleanly:
- **`ridebase-ml`:** 113 / 113 passed in 11.54s
- **`backend` (`ridebase-v1-dashboard/backend`):** 83 / 83 passed in 1.89s
- **`control-center` (`ridebase-control-center`):** 26 / 26 passed in 0.02s
- **Total:** 222 / 222 passed (100%)

---

## 2. Frozen V2.1 Production Artifact Integrity (Preflight SHA256)

The frozen V2.1 model, calibrator, 54-feature list, and SQLite history store hashes were verified bit-for-bit:
- `champion_model.joblib`: `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def`
- `calibrator.joblib`: `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945`
- `feature_list.json`: `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a`
- `v2_1_history_serving.sqlite`: `a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657`

Backend artifacts in `ridebase-v1-dashboard/backend/artifacts/models/v2_1_v1_4` match identically.

---

## 3. Mission Objectives & Non-Negotiables

1. **New Layer Objective:** Answer *"How urgent/severe is the deterministic maintenance state right now?"* via a deterministic 0–100 Maintenance Urgency Score.
2. **Strict Decoupling:** The urgency score is 100% deterministic and derived entirely from policy metrics (progress ratio, overdue km, overdue days, determining dimension). It does **NOT** use P30/P60/P90/P120, V2.1 risk scores, model weights, or V2.0 outputs.
3. **Core Invariant:** `Maintenance Due != Service Return Risk`.
4. **Safety Guarantee:** V2.1 model, calibrator, and 54-feature contract remain strictly frozen; no retraining.
