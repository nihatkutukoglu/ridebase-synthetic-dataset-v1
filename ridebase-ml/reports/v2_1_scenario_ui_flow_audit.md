# RideBase V2.1 Scenario UI/API Flow Audit Report

**Date:** 2026-09-04  
**Audit Target:** RideBase ML Control Center (`ridebase-control-center`) & Inference API (`ridebase-v1-dashboard/backend`)

---

## 1. Actual Current Flow (Step-by-Step)

### A. User Input
The user navigates to the **V2 Survival** tab and accesses the Scenario form (`v2ModeScenario`).
Inputs collected:
- Motosiklet: `brand`, `model_id`, `production_year`
- Kullanım: `current_odometer_km` (v2odo), `annual_km_baseline` (v2annual), `usage_type`, `riding_intensity`
- Servis geçmişi: `last_service_date`, `last_service_odometer_km`

### B. Action Trigger
User clicks `#v2scenarioRun` (`"V1 + V2 SENARYO TAHMİNİNİ HESAPLA"`), invoking `v2RunScenario()`.

### C. Backend Route & Evaluation (`POST /api/v2/predict/scenario`)
1. **Deterministic Maintenance Policy (`_maintenance_assessment`)**:
   - Computes `km_since = current_odometer_km - last_service_odometer_km`.
   - Computes `days_since = snapshot_date - last_service_date`.
   - Compares against catalog or operational policy (e.g. Bajaj NS200: 3,000 km / 6 months).
   - Evaluates progress ratio: if >= 1.0, marks `status="OVERDUE"`, `action_label="SERVİS ŞİMDİ GEREKLİ"`.
   - Naively annualizes short-window usage: if `days_since >= 30` and `km_since >= 500`, sets `recent_annualized_km = km_since * 365.0 / days_since`. (e.g., 30,000 km in 34 days = 322,059 km/year).
2. **V1 Regression (`v1_predict`)**:
   - If maintenance is overdue, V1 point estimation is suppressed (`decision.show_v1_point_estimate = false`).
3. **V2.0 Survival Prediction (`predictor.predict_batch`)**:
   - Executes frozen V2.0 model (`xgb_cox` on 117 features).
   - Generates `risk_30d`, `risk_60d`, `risk_90d`, `risk_120d`, `median_service_days`.
4. **API Response**:
   - Returns `{maintenance, v1, v2, coverage, provenance, decision, warnings}`.

### D. UI Rendering
1. `v2MaintenanceCard(d.maintenance)` renders the top banner (`SERVİS ŞİMDİ GEREKLİ · BAKIM GECİKMİŞ`) along with raw annualized pace: `"Son servis sonrası kullanım temposu yıllıklandırıldığında yaklaşık 322,059 km/yıl"`.
2. `v2ResultCard(d.v1, d.v2, ...)` renders **V2.0 outputs as the primary prediction cards** (e.g. `P30: 11.7%`).
3. `v2CoverageCard` renders the 117-feature breakdown.

---

## 2. Status of V2.1 Scenario in Current Architecture

- **Main Scenario Form (`v2ModeScenario`)**: **ABSENT**. V2.1 is NOT called at all. The primary cards show V2.0.
- **V2.1 Module Tab (`v2_1Predict`)**:
  - Contains a secondary subtab `SCENARIO / WHAT-IF` (`v2_1ModeScenario`) calling `POST /api/v2_1/predict/scenario`.
  - Default active tab in V2.1 is `HISTORY PIPELINE`, making V2.1 scenario hidden from normal user navigation.
  - The V2.1 scenario tab lacks the rich deterministic maintenance card and usage rate context present in the primary scenario experience.

---

## 3. Flow Architecture Flaw & Remediation Target

| Aspect | Current Flawed State | Target Architecture |
|---|---|---|
| **Primary Prediction** | V2.0 Research model (failed live audit, shows ~11.7% P30 on extreme overdue) | **V2.1 Dynamic-Landmark model** (`POST /api/v2_1/predict/scenario`) |
| **V2.0 Placement** | Primary card at top of scenario results | **Demoted to collapsed legacy research comparison** with clear audit failure warning |
| **Deterministic Maintenance Banner** | Visible, but adjacent to flawed V2.0 cards | **Preserved authoritative banner** clearly separated: `Maintenance Due != Customer Return Risk` |
| **Usage Rate Semantics** | Raw 322k km/yr displayed without qualifier or confidence window | **Distinguish explicit annual input vs. short-window tempo**, adding low-confidence badge if observation window < 90 days |
