# RideBase Maintenance Urgency Scenario Audit Report

**Date:** 2026-09-04  
**Total Scenarios Audited:** 117  
**Sweep Dimensions:**
- Intervals: 3,000 km, 5,000 km, 10,000 km
- Progress Ratios: [0.1, 0.25, 0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0]
- Determining Dimensions: KM, TIME, BOTH

---

## 1. Audit Assertions & Summary Scorecard

| Assertion | Criterion | Passed / Total | Status |
|---|---|---|---|
| **Boundedness** | $\text{Score} \in [0, 100]$ | 117 / 117 | **PASS** |
| **Monotonicity** | Score strictly non-decreasing as progress ratio rises | 117 / 117 | **PASS** |
| **Determinism** | Bit-for-bit identical repeat calculation | 117 / 117 | **PASS** |
| **Due Threshold Alignment** | $R \ge 1.0 \implies \text{Score} \ge 50$ (never NORMAL/YAKLAŞIYOR) | 117 / 117 | **PASS** |
| **Saturation** | Severe overdue ($R \ge 5.0$) saturates smoothly at 100 | 117 / 117 | **PASS** |
| **Dimension Support** | KM, TIME, BOTH accurately identified | 117 / 117 | **PASS** |

Assertion failures count: **0**

---

## 2. Representative Ratio Sweep Progression (5,000 km interval)

| Progress Ratio | KM / Time | Urgency Score | Severity Level | Determining Dimension | Policy Meaning |
|---|---|---|---|---|---|
| 0.10 (10%) | 500 km / 18 d | 5 / 100 | NORMAL | KM | Bakım periyodu içinde — kalan: 4.500 km |
| 0.25 (25%) | 1,250 km / 46 d | 12 / 100 | NORMAL | KM | Bakım periyodu içinde — kalan: 3.750 km |
| 0.50 (50%) | 2,500 km / 91 d | 24 / 100 | NORMAL | KM | Bakım periyodu içinde — kalan: 2.500 km |
| 0.75 (75%) | 3,750 km / 137 d | 36 / 100 | YAKLAŞIYOR | KM | Bakım periyoduna yaklaşıyor (%75 ilerleme) |
| 0.80 (80%) | 4,000 km / 146 d | 38 / 100 | YAKLAŞIYOR | KM | Bakım periyoduna 1.000 km kaldı (%80 ilerleme) |
| 0.90 (90%) | 4,500 km / 164 d | 44 / 100 | YAKLAŞIYOR | KM | Bakım periyoduna 500 km kaldı (%90 ilerleme) |
| **1.00 (100%)** | 5,000 km / 183 d | **50 / 100** | **GECİKMİŞ** | KM | Bakım periyodu doldu (SERVİS ŞİMDİ GEREKLİ) |
| 1.10 (110%) | 5,500 km / 201 d | 55 / 100 | GECİKMİŞ | KM | 500 km gecikmiş (1.1× seviyesinde) |
| 1.25 (125%) | 6,250 km / 228 d | 63 / 100 | GECİKMİŞ | KM | 1.250 km gecikmiş (1.2× seviyesinde) |
| 1.50 (150%) | 7,500 km / 274 d | 75 / 100 | ÇOK GECİKMİŞ | KM | 2.500 km gecikmiş (1.5× seviyesinde) |
| 2.00 (200%) | 10,000 km / 365 d | 90 / 100 | KRİTİK | KM | 5.000 km gecikmiş (2.0× seviyesinde) |
| 3.00 (300%) | 15,000 km / 548 d | 93 / 100 | KRİTİK | KM | 10.000 km gecikmiş (3.0× seviyesinde) |
| 5.00 (500%) | 25,000 km / 913 d | 100 / 100 | KRİTİK | KM | 20.000 km gecikmiş (5.0× seviyesinde) |
| 10.00 (1000%) | 50,000 km / 1826 d | 100 / 100 | KRİTİK | KM | 45.000 km gecikmiş (10.0× seviyesinde) |

---

## 3. Verdict

**ALL AUDIT ASSERTIONS PASSED (100%).**  
The deterministic Maintenance Urgency Score satisfies all mathematical, boundary, monotonicity, and explainability requirements.
