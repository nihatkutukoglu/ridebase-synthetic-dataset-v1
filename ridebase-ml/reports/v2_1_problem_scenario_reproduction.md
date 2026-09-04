# RideBase V2.1 Problem Scenario Reproduction Report

**Date:** 2026-09-04  
**Target Scenario:** NS200-like motorcycle with extreme overdue usage in a short observation window.

---

## 1. Problem Scenario Setup

- **Motorcycle:** Bajaj Pulsar NS200 (`BAJAJ_NS200`)
- **Primary Maintenance Interval:** 3,000 km (RideBase Türkiye operational policy) / 5,000 km (Catalog)
- **Current Odometer:** 42,000 km
- **Last Service Odometer:** 12,000 km
- **Km Since Last Service:** 30,000 km
- **Overdue Km:** 27,000 km (against 3,000 km operational interval)
- **Days Since Last Service:** 34 days
- **User Entered Annual Mileage:** 10,000 km/year (explicit form input)
- **Raw Short-Window Annualized Pace:** 30,000 km / 34 days × 365 ≈ **322,059 km/year**

---

## 2. Head-to-Head Comparative Assessment

| Metric / Dimension | Deterministic Policy | V2.0 Legacy Research | V2.1 Dynamic-Landmark (Primary) |
|---|---|---|---|
| **Model Type** | Rule-based engine | XGB-Cox on service snapshots (Failed arbitrary-day audit) | XGB-Cox + Isotonic on 256k dynamic landmarks |
| **Status / Due Banner** | **SERVİS ŞİMDİ GEREKLİ** (BAKIM GECİKMİŞ) | N/A (Does not decide maintenance) | N/A (Predicts return probability only) |
| **Progress Ratio** | **1000.0%** (10.0x interval) | N/A | N/A |
| **P30 (30-Day Return)** | — | **7.98%** (Severe under-prediction anomaly) | **22.73%** (Sensible near-term return expectation) |
| **P60 (60-Day Return)** | — | 38.65% | **44.86%** |
| **P90 (90-Day Return)** | — | 49.49% | **65.61%** |
| **P120 (120-Day Return)**| — | 82.37% | **75.40%** |
| **Median Return Days** | — | ~111 days | ~263 days |
| **Risk Score** | — | — | **2.682** |
| **Annual KM Semantics**| Raw 322k km/yr used as tempo | Contradiction warning emitted | **10,000 km/year preserved** as `annual_km_baseline`; 322k treated as diagnostic short-window pace |
| **Horizon Monotonicity**| N/A | P30 < P60 < P90 < P120 | P30 <= P60 <= P90 <= P120 (Strictly Monotone) |

---

## 3. Root Cause Analysis

1. **Why V2.0 showed 7.98% / ~11.7% P30:**
   V2.0 was trained on service-event snapshot rows (where every row had just completed a service). In arbitrary-day live scenarios with extreme overdue mileage, the feature distributions fell completely outside the support of V2.0's training manifold, causing distorted hazard scores and near-zero P30 collapse. This was the exact reason V2.0 failed the live-scenario audit.
2. **Why V2.1 handles this correctly:**
   V2.1 is trained on dynamic random calendar landmarks across the lifecycle of motorcycles (including overdue states).
   - V2.1 correctly evaluates the 30-day customer return probability at **22.73%**, 60-day at **44.86%**, 90-day at **65.61%**, and 120-day at **75.40%**.
   - V2.1 keeps the deterministic maintenance decision (`SERVİS ŞİMDİ GEREKLİ`) completely separate from the probability of customer return (`Maintenance Due != Service Return Risk`).
3. **Annual Mileage Handling:**
   - Model input `annual_km_baseline` is strictly the user's explicit input (10,000 km/year).
   - The short-window pace of 322,059 km/year is identified as having a 34-day observation window (< 90 days), triggering a low-confidence diagnostic warning rather than corrupting the model's core feature vector.
