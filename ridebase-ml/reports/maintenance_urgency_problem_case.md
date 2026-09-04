# RideBase Maintenance Urgency — NS200 Problem Case Report

**Date:** 2026-09-04  
**Target Scenario:** Bajaj Pulsar NS200 with extreme overdue state (~3,000 km interval, 30,000 km since service, 34 days elapsed).

---

## 1. Scenario Inputs
- **Motorcycle:** Bajaj Pulsar NS200 (`BAJAJ_NS200`)
- **OEM / Operational Interval:** 3,000 km (RideBase TR policy) / 5,000 km (Catalog)
- **Current Odometer:** 42,000 km
- **Last Service Odometer:** 12,000 km
- **Km Since Service:** 30,000 km
- **Days Since Service:** 34 days
- **User Annual Mileage:** 10,000 km/year

---

## 2. Deterministic Maintenance Evaluation (Urgency Layer)

| Attribute | Evaluated Value | Semantics |
|---|---|---|
| **Service Status** | `OVERDUE` (`BAKIM GECİKMİŞ`) | Service threshold passed |
| **Action** | `SERVICE_NOW_REQUIRED` (`SERVİS ŞİMDİ GEREKLİ`) | **SERVİS ŞİMDİ GEREKLİ** |
| **Progress Ratio** | `1000.0%` (10.0×) | Dominant progress |
| **Overdue Km** | `27,000 km` | Distance overdue |
| **Determining Dimension** | `KM` | Driven by mileage |
| **Maintenance Urgency Score** | **`100 / 100`** | **Maximal deterministic urgency** |
| **Maintenance Urgency Level** | **`KRİTİK`** | **KRİTİK** |
| **Maintenance Urgency Reason** | *"27.000 km gecikmiş (kilometre periyodu 10.0× seviyesinde)"* | Transparent human explanation |

---

## 3. V2.1 Customer Return Prediction (ML Layer)

| Horizon | Predicted Return Probability | Semantics |
|---|---|---|
| **30 Gün ($P_{30}$)** | **22.7%** (0.227) | Probability customer returns in 30 days |
| **60 Gün ($P_{60}$)** | **44.9%** (0.449) | Probability customer returns in 60 days |
| **90 Gün ($P_{90}$)** | **65.6%** (0.656) | Probability customer returns in 90 days |
| **120 Gün ($P_{120}$)** | **75.4%** (0.754) | Probability customer returns in 120 days |
| **Median Service Days** | ~263 gün | Median return horizon |
| **Risk Score** | 2.682 | Hazard score |

---

## 4. Semantic Separation Verification

$$\text{Maintenance Urgency (100 / 100 - KRİTİK)} \neq \text{Customer Return Probability (} P_{30} = 22.7\% \text{)}$$

- **The policy state is maximal severity:** The motorcycle is 27,000 km past due ($10\times$ the interval). The Maintenance Urgency Score correctly reports **100 / 100 (KRİTİK)**.
- **The ML model predicts customer behavior:** In reality, customers with extreme delays do not automatically appear at the dealership on day 1. $P_{30} = 22.7\%$ reflects realistic customer return behavior.
- **Strict Invariant Maintained:** V2.1 probabilities are NOT forced to match the urgency score. The microcopy clearly explains this distinction.
