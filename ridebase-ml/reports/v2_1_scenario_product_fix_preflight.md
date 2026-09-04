# RideBase V2.1 Scenario Product Fix — Preflight Report

**Date:** 2026-09-04  
**Starting Commit:** `df4fd03` (`HEAD == origin/main`, working tree clean)  
**Branch:** `main`  
**Divergence:** `0 0` (in sync with remote)

---

## 1. Baseline Test Suite Verification

All suites executed synchronously and passed with zero failures:
- **`ridebase-ml`:** 113 passed (1 warning regarding XGBoost model loading compatibility) in 11.32s
- **`backend` (`ridebase-v1-dashboard/backend`):** 83 passed in 1.90s
- **`control-center` (`ridebase-control-center`):** 25 passed in 0.02s
- **Total:** 221 / 221 passed (100%)

---

## 2. Frozen V2.1 Production Artifact Integrity (Preflight SHA256)

The frozen V2.1 model, calibrator, 54-feature list, and SQLite history store hashes were recorded:
- `champion_model.joblib`: `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def`
- `calibrator.joblib`: `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945`
- `feature_list.json`: `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a`
- `v2_1_history_serving.sqlite`: `a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657`

Backend copies in `ridebase-v1-dashboard/backend/artifacts/models/v2_1_v1_4` match bit-for-bit.

---

## 3. Current Implementation Audit

| Component | Location | Implementation Details |
|---|---|---|
| **V1/V2 scenario button** | `ridebase-control-center/template.html:1627` | Button `#v2scenarioRun` labeled `"V1 + V2 SENARYO TAHMİNİNİ HESAPLA"`. Invokes `v2RunScenario()`. |
| **V2.0 API call** | `ridebase-control-center/template.html:1702` | Calls `POST /api/v2/predict/scenario`. Directly renders V2.0 output into primary result cards via `v2ResultCard()`. |
| **V2.1 scenario API call** | `ridebase-control-center/template.html:2186` | Calls `POST /api/v2_1/predict/scenario`. Currently tucked away in the secondary V2.1 tab under `SCENARIO / WHAT-IF`, leaving V2.0 as the main scenario experience. |
| **Annualized recent usage** | `ridebase-v1-dashboard/backend/app/v2_scenario.py:355` | Naive calculation `km_since * 365.0 / days_since` if `days_since >= 30` and `km_since >= 500`. On a 34-day, 30,000 km input, yields ~322,059 km/year. |
| **Displayed usage pace** | `ridebase-control-center/template.html:1683` | Shows `Son servis sonrası kullanım temposu yıllıklandırıldığında yaklaşık X km/yıl` with no distinction between baseline annual km and raw short-window pace, and no observation window confidence indicator. |
| **Deterministic maintenance policy** | `ridebase-v1-dashboard/backend/app/v2_scenario.py:320-353` & `template.html:1686-1692` | Correctly evaluates `progress_ratio = max(km_ratio, days_ratio)`, triggering `SERVİS ŞİMDİ GEREKLİ · BAKIM GECİKMİŞ` when ratio >= 1.0. Completely separate from model probability. |

---

## 4. Problem Statement & Action Plan

In the current user flow, a scenario with ~3,000 km interval and 30,000 km elapsed in 34 days results in:
1. Deterministic maintenance correctly flagging `SERVİS ŞİMDİ GEREKLİ` (progress ~1000%, overdue ~27,000 km).
2. Primary prediction cards displaying **V2.0**, which failed the live-scenario audit and gives a distorted ~11.7% P30.
3. Annualized pace showing an un-contextualized `322,059 km/yıl`, confusing model input with raw diagnostic tempo.
4. V2.1 is hidden away in a secondary tab.

The fix will promote V2.1 scenario to the primary prediction, demote V2.0 to a collapsed legacy comparison, clarify usage rate semantics, run exhaustive extreme-overdue audits, and verify zero regressions.
