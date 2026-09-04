# RideBase Deterministic Maintenance Urgency Score Specification

**Version:** 1.0.0  
**Status:** PRODUCTION APPROVED  
**Author:** RideBase Core Team  
**Scope:** Deterministic Maintenance Severity Layer (Independent of ML Models)

---

## 1. Core Principle & Semantic Boundary

$$\text{Maintenance Due State} \neq \text{Customer Return Probability} \neq \text{Maintenance Urgency Score}$$

1. **Deterministic Maintenance Policy:** Answers *"Does this motorcycle need maintenance right now?"* (Binary/Status: `NOT_DUE`, `DUE_SOON`, `OVERDUE`).
2. **V2.1 Landmark Survival Model:** Answers *"What is the probability that the customer returns to service within 30/60/90/120 days?"* (Survival probabilities $P_{30}, P_{60}, P_{90}, P_{120}$).
3. **Maintenance Urgency Score (This Layer):** Answers *"How severe/urgent is the maintenance state right now on an interpretable 0–100 scale?"*

The Maintenance Urgency Score is **100% deterministic**. It does NOT use model weights, feature importance, survival curves, or predicted probabilities.

---

## 2. Input Quantities

All inputs are derived directly from the authoritative OEM / Türkiye operational maintenance policy:

| Input Symbol | Variable Name | Definition |
|---|---|---|
| $K_{\text{since}}$ | `km_since_service` | Current odometer minus last service odometer ($\text{km}$) |
| $T_{\text{since}}$ | `days_since_service` | Elapsed calendar days since last service ($\text{days}$) |
| $K_{\text{interval}}$ | `interval_km` | Primary policy distance interval ($\text{km}$) |
| $T_{\text{interval}}$ | `interval_days` | Primary policy time interval ($\text{days}$) |
| $R_{\text{km}}$ | `km_progress_ratio` | $K_{\text{since}} / K_{\text{interval}}$ |
| $R_{\text{time}}$ | `time_progress_ratio` | $T_{\text{since}} / T_{\text{interval}}$ |
| $R$ | `progress_ratio` | $\max(R_{\text{km}}, R_{\text{time}})$ |

---

## 3. Piecewise-Linear Mapping Function

The score $S \in [0, 100]$ is computed as a continuous, strictly monotonic, piecewise-linear function of the dominant progress ratio $R$:

$$
S(R) = \begin{cases}
0, & \text{if } R \le 0 \\
R \times 47.5, & \text{if } 0 < R < 0.80 \\
38 + (R - 0.80) \times 60, & \text{if } 0.80 \le R < 1.00 \\
50 + (R - 1.00) \times 50, & \text{if } 1.00 \le R < 1.50 \\
75 + (R - 1.50) \times 30, & \text{if } 1.50 \le R < 2.00 \\
90 + (R - 2.00) \times \frac{10}{3}, & \text{if } 2.00 \le R < 5.00 \\
100, & \text{if } R \ge 5.00
\end{cases}
$$

### Mathematical Properties
1. **Bounded:** $S(R) \in [0, 100]$ for all $R \in [0, \infty)$.
2. **Continuous:** At every transition boundary ($R \in \{0.80, 1.00, 1.50, 2.00, 5.00\}$), the left and right limits are strictly equal.
3. **Monotonic Non-Decreasing:** $\frac{dS}{dR} \ge 0$ everywhere.
4. **Policy-Aligned Anchor:** Exactly at $R = 1.00$ (the exact OEM due threshold), $S(1.00) = 50$, transitioning cleanly into the `GECİKMİŞ` band.
5. **Safe Saturation:** Once a motorcycle reaches $5\times$ its interval ($R \ge 5.0$), it reaches maximum urgency (100) and saturates without overflow or instability.

---

## 4. Severity Bands & Semantics

| Score Range | Severity Level (`maintenance_urgency_level`) | Policy Meaning | Recommended Action |
|---|---|---|---|
| **0 – 24** | `NORMAL` | Bakım periyodunun ilk yarısında ($R < 0.50$) | Rutin kullanım, işlem gerekmez |
| **25 – 49** | `YAKLAŞIYOR` | Bakım periyoduna yaklaşıyor ($0.50 \le R < 1.00$) | Servis randevusu planlama hazırlığı |
| **50 – 74** | `GECİKMİŞ` | OEM periyodu aşıldı ($1.00 \le R < 1.50$) | Servis şimdi gerekli |
| **75 – 89** | `ÇOK GECİKMİŞ` | OEM periyodu %50'den fazla aşıldı ($1.50 \le R < 2.00$) | Yüksek aşınma riski, acil servis |
| **90 – 100** | `KRİTİK` | OEM periyodu $2\times$ veya daha fazla aşıldı ($R \ge 2.00$) | Kritik mekanik risk, derhal servis |

---

## 5. Machine-Readable Schema

```json
{
  "maintenance_urgency_score": 100,
  "maintenance_urgency_level": "KRİTİK",
  "maintenance_urgency_reason": "27.000 km gecikmiş (kilometre periyodu 10.0× seviyesinde)",
  "determining_dimension": "KM",
  "progress_ratio": 10.0,
  "overdue_km": 27000.0,
  "overdue_days": 0.0
}
```

---

## 6. Determining Dimension (`determining_dimension`)
- If $|R_{\text{km}} - R_{\text{time}}| \le 0.01$: `"BOTH"` (balanced usage).
- Else if $R_{\text{km}} > R_{\text{time}}$: `"KM"` (mileage-driven wear).
- Else: `"TIME"` (calendar-driven aging).

---

## 7. Worked Examples

### Case A: Brand New Service ($R = 0.10$)
- Model: Honda PCX125 ($K_{\text{interval}} = 6,000\text{ km}$)
- $K_{\text{since}} = 600\text{ km}$, $T_{\text{since}} = 30\text{ days}$
- $R_{\text{km}} = 0.10$, $R_{\text{time}} = 0.082 \implies R = 0.10$
- Score: $S = 0.10 \times 47.5 = 4.75 \approx 5$
- Level: `NORMAL` (Reason: *Bakım periyodu içinde — kalan: 5.400 km*)

### Case B: Approaching Service ($R = 0.90$)
- Model: Yamaha MT-07 ($K_{\text{interval}} = 10,000\text{ km}$)
- $K_{\text{since}} = 9,000\text{ km}$, $T_{\text{since}} = 180\text{ days}$
- $R_{\text{km}} = 0.90$, $R_{\text{time}} = 0.49 \implies R = 0.90$
- Score: $S = 38 + (0.90 - 0.80) \times 60 = 44$
- Level: `YAKLAŞIYOR` (Reason: *Bakım periyoduna 1.000 km kaldı (%90 ilerleme)*)

### Case C: Exactly Due ($R = 1.00$)
- $K_{\text{since}} = 5,000\text{ km}$, $K_{\text{interval}} = 5,000\text{ km}$
- $R = 1.00$
- Score: $S = 50$
- Level: `GECİKMİŞ` (Reason: *Bakım periyodu doldu — servis şimdi gerekli*)

### Case D: Problem Screenshot Case ($R = 10.00$)
- Model: Bajaj NS200 ($K_{\text{interval}} = 3,000\text{ km}$)
- $K_{\text{since}} = 30,000\text{ km}$, $T_{\text{since}} = 34\text{ days}$
- $R_{\text{km}} = 10.0$, $R_{\text{time}} = 0.186 \implies R = 10.0$
- Score: $S = 100$
- Level: `KRİTİK` (Reason: *27.000 km gecikmiş — kilometre periyodu 10.0× seviyesinde*)
- Decoupling note: V2.1 $P_{30} = 22.7\%$ is completely uncorrupted by this urgency rating.

---

## 8. Missing Data Behavior
If $K_{\text{since}}$ or $T_{\text{since}}$ cannot be established due to missing odometer or date inputs:
- `maintenance_urgency_score`: `null`
- `maintenance_urgency_level`: `"HESAPLANAMADI"`
- `maintenance_urgency_reason`: *"Kişisel servis başlangıç noktası eksik olduğu için bakım aciliyeti hesaplanamadı."*
No fabricated score is ever returned.
