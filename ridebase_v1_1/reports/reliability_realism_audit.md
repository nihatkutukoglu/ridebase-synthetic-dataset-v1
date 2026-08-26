# RideBase Synthetic Dataset v1.1 — Reliability Realism Audit

**Kapsam:** Yalnızca dataset iç tutarlılığı ve generator gerçekçilik denetimi. Gerçek dünya marka güvenilirliği iddiası değildir. İnternet verisi kullanılmadı; `source_tables/` altındaki ana dosyalar değiştirilmedi.

## Yöntem ve arıza tanımı

- Toplam: **10,000 motosiklet**, **41,518 servis**, **201,800 service task**, **344,714 aylık mileage satırı**.
- Ana failure hedefi: `service_type_code ∈ {REPAIR, BREAKDOWN}`; servis satırı bir kez sayıldı.
- `REPAIR`: 1,159/41,518 = 2.79%; `BREAKDOWN`: 993/41,518 = 2.39%; birleşik: 2,152/41,518 = 5.18%; `is_breakdown=1`: 993/41,518 = 2.39%.
- Temsil kontrolü: BREAKDOWN türü ile `is_breakdown=1` **41,518/41,518** satırda eşleşiyor.
- Yaş: servis yılı − production_year; gözlem-sonu yaşında son mileage timeline tarihi − production_year. Aktif motosikletlerde `observation_end_date` boş olduğu için toplam gözlem süresinin eksik sayılmasını bu şekilde önledik.
- Km maruziyeti: `mileage_timeline_monthly.km_added` her motorcycle-month için bir kez toplandı. Odometer seviyeleri exposure'a eklenmedi; bu yüzden çift sayım yok.
- `services_enriched.csv` ana servis alanlarıyla bire bir tutarlı: **YES**. Appointment→service dönüşmüş kayıt: **24,209**; eşsiz bağlı servis: **24,209**.

## 1. Veri profili

| brand | motorcycle_count | total_observation_years | avg_motorcycle_age_years | avg_ending_odometer_km |
|---|---|---|---|---|
| Honda | 3,772 | 10,461.4 | 4.92 | 60,589 |
| Mondial | 1,560 | 4,232.1 | 4.92 | 67,241 |
| TVS | 1,148 | 3,195.3 | 4.93 | 54,505 |
| Kuba | 880 | 2,395.8 | 4.88 | 75,470 |
| Yamaha | 759 | 2,071.7 | 4.93 | 76,400 |
| Bajaj | 527 | 1,460.6 | 4.71 | 41,030 |
| CFMOTO | 443 | 1,263.1 | 4.65 | 36,514 |
| RKS | 386 | 1,036.4 | 4.94 | 72,334 |
| SYM | 272 | 747.2 | 4.98 | 55,467 |
| KYMCO | 156 | 430.2 | 4.63 | 44,105 |
| KTM | 56 | 154.7 | 4.52 | 44,434 |
| Royal Enfield | 41 | 103.1 | 4.63 | 27,795 |

### Model başına motosiklet ve servis

| brand | model_name | motorcycle_count | service_count |
|---|---|---|---|
| Bajaj | Pulsar NS200 UG2 | 251 | 663 |
| Bajaj | Pulsar NS125 | 214 | 452 |
| Bajaj | Dominar D250 | 62 | 126 |
| CFMOTO | 250NK | 156 | 357 |
| CFMOTO | 250SR | 76 | 155 |
| CFMOTO | 450NK | 62 | 143 |
| CFMOTO | 250 DUAL | 59 | 136 |
| CFMOTO | 250CL-X | 42 | 72 |
| CFMOTO | 650NK | 31 | 68 |
| CFMOTO | 450 CL-C | 17 | 23 |
| Honda | PCX125 | 1,273 | 3,368 |
| Honda | Activa 125 | 1,051 | 3,333 |
| Honda | Dio 110 | 450 | 3,131 |
| Honda | CB125F | 345 | 819 |
| Honda | Forza 250 | 223 | 619 |
| Honda | SH125i | 194 | 403 |
| Honda | ADV350 | 118 | 222 |
| Honda | CL250 | 62 | 164 |
| Honda | EM1 e: | 36 | 56 |
| Honda | Monkey | 20 | 37 |
| KTM | 390 Duke | 56 | 123 |
| KYMCO | X-Town CT 250 | 83 | 198 |
| KYMCO | Downtown 250i | 73 | 136 |
| Kuba | CG50 Pro | 510 | 2,407 |
| Kuba | Blueberry 50 | 370 | 4,525 |
| Mondial | Wing 50i | 652 | 3,512 |
| Mondial | 50 UAG | 421 | 2,769 |
| Mondial | SFC MINI 50ec | 318 | 3,234 |
| Mondial | Exon 50 | 97 | 299 |
| Mondial | Turismo 50i | 72 | 277 |
| RKS | New Light Pro | 386 | 2,011 |
| Royal Enfield | Hunter 350 | 41 | 64 |
| SYM | Jet X 125 TCS ABS | 272 | 691 |
| TVS | Jupiter 125 | 857 | 2,640 |
| TVS | Raider 125 | 210 | 410 |
| TVS | Apache RTR 200 4V FI | 81 | 178 |
| Yamaha | NMAX 125 | 463 | 3,014 |
| Yamaha | XMAX 250 | 222 | 532 |
| Yamaha | XSR125 | 74 | 151 |

### Marka başına kullanım profili dağılımı

| brand | COMMUTER | COURIER | TOURING | TRACK | OFFROAD | WEEKEND | SEASONAL |
|---|---|---|---|---|---|---|---|
| Bajaj | 0.0% | 0.6% | 3.6% | 0.0% | 0.0% | 84.1% | 11.8% |
| CFMOTO | 0.0% | 0.0% | 0.0% | 34.8% | 2.3% | 13.5% | 49.4% |
| Honda | 63.7% | 10.5% | 5.1% | 0.7% | 0.7% | 16.8% | 2.4% |
| KTM | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% |
| KYMCO | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 1.3% | 98.7% |
| Kuba | 57.7% | 42.3% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Mondial | 65.6% | 23.6% | 0.0% | 0.0% | 0.0% | 0.2% | 10.6% |
| RKS | 60.9% | 39.1% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Royal Enfield | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% |
| SYM | 0.0% | 7.0% | 9.9% | 0.0% | 0.0% | 83.1% | 0.0% |
| TVS | 74.7% | 0.0% | 0.3% | 5.7% | 0.0% | 18.4% | 0.9% |
| Yamaha | 0.0% | 53.2% | 16.5% | 6.5% | 0.3% | 20.6% | 3.0% |

## 2. Ham marka arıza oranları

| brand | motorcycle_count | service_count | repair_count | breakdown_count | repair_breakdown_count | raw_failure_service_rate |
|---|---|---|---|---|---|---|
| CFMOTO | 443 | 954 | 57 | 54 | 111 | 11.64% |
| KYMCO | 156 | 334 | 17 | 13 | 30 | 8.98% |
| SYM | 272 | 691 | 27 | 29 | 56 | 8.10% |
| TVS | 1,148 | 3,228 | 140 | 103 | 243 | 7.53% |
| Bajaj | 527 | 1,241 | 41 | 41 | 82 | 6.61% |
| Honda | 3,772 | 12,152 | 421 | 333 | 754 | 6.20% |
| Yamaha | 759 | 3,697 | 110 | 103 | 213 | 5.76% |
| KTM | 56 | 123 | 5 | 2 | 7 | 5.69% |
| Royal Enfield | 41 | 64 | 2 | 1 | 3 | 4.69% |
| RKS | 386 | 2,011 | 52 | 42 | 94 | 4.67% |
| Mondial | 1,560 | 10,091 | 175 | 162 | 337 | 3.34% |
| Kuba | 880 | 6,932 | 112 | 110 | 222 | 3.20% |

## 3. Motosiklet başına arıza ve tekrar

| brand | motorcycle_count | motorcycles_with_failure | motorcycles_with_failure_pct | failure_events_per_100_motorcycles | repeat_failure_motorcycles | repeat_failure_motorcycle_rate |
|---|---|---|---|---|---|---|
| CFMOTO | 443 | 93 | 20.99% | 25.06 | 17 | 3.84% |
| KYMCO | 156 | 26 | 16.67% | 19.23 | 4 | 2.56% |
| SYM | 272 | 48 | 17.65% | 20.59 | 8 | 2.94% |
| TVS | 1,148 | 217 | 18.90% | 21.17 | 25 | 2.18% |
| Bajaj | 527 | 72 | 13.66% | 15.56 | 10 | 1.90% |
| Honda | 3,772 | 663 | 17.58% | 19.99 | 78 | 2.07% |
| Yamaha | 759 | 179 | 23.58% | 28.06 | 33 | 4.35% |
| KTM | 56 | 5 | 8.93% | 12.50 | 2 | 3.57% |
| Royal Enfield | 41 | 3 | 7.32% | 7.32 | 0 | 0.00% |
| RKS | 386 | 78 | 20.21% | 24.35 | 15 | 3.89% |
| Mondial | 1,560 | 280 | 17.95% | 21.60 | 49 | 3.14% |
| Kuba | 880 | 187 | 21.25% | 25.23 | 30 | 3.41% |

Yaşam boyu arıza sayısı dağılımı:

| failure_count_bucket | motorcycle_count |
|---|---|
| 0 | 8,149 |
| 1 | 1,580 |
| 2 | 244 |
| 3+ | 27 |

## 4. 10.000 km başına arıza

| brand | total_observed_km | repair_breakdown_count | failure_events_per_10000_km |
|---|---|---|---|
| CFMOTO | 8,023,218 | 111 | 0.1383 |
| KYMCO | 3,473,275 | 30 | 0.0864 |
| Bajaj | 10,010,474 | 82 | 0.0819 |
| SYM | 6,894,649 | 56 | 0.0812 |
| TVS | 32,247,753 | 243 | 0.0754 |
| Honda | 127,235,899 | 754 | 0.0593 |
| Yamaha | 37,648,992 | 213 | 0.0566 |
| KTM | 1,253,445 | 7 | 0.0558 |
| Mondial | 62,139,352 | 337 | 0.0542 |
| Royal Enfield | 569,081 | 3 | 0.0527 |
| RKS | 17,865,143 | 94 | 0.0526 |
| Kuba | 42,805,087 | 222 | 0.0519 |

**Sınırlama:** `km_added` güvenilir toplam exposure için en iyi kaynak; ancak timeline dışındaki başlangıç kilometresi exposure değildir. Sonuçlar gözlem penceresi içindeki yaklaşık insidansı gösterir.

## 5. Model bazında arıza

Sıralama filtresi: motorcycle_count ≥ 50 ve service_count ≥ 150; uygun model sayısı **28**.

### En yüksek 15

| brand | model_name | motorcycle_count | service_count | failure_count | failure_rate | observed_expected_ratio |
|---|---|---|---|---|---|---|
| CFMOTO | 250SR | 76 | 155 | 27 | 17.42% | 0.96 |
| TVS | Apache RTR 200 4V FI | 81 | 178 | 29 | 16.29% | 0.93 |
| Honda | CL250 | 62 | 164 | 24 | 14.63% | 1.08 |
| CFMOTO | 250NK | 156 | 357 | 48 | 13.45% | 1.06 |
| Yamaha | XSR125 | 74 | 151 | 20 | 13.25% | 0.93 |
| Honda | ADV350 | 118 | 222 | 25 | 11.26% | 1.35 |
| KYMCO | X-Town CT 250 | 83 | 198 | 19 | 9.60% | 1.09 |
| Yamaha | XMAX 250 | 222 | 532 | 47 | 8.83% | 1.06 |
| Honda | SH125i | 194 | 403 | 33 | 8.19% | 1.03 |
| Bajaj | Pulsar NS125 | 214 | 452 | 37 | 8.19% | 1.20 |
| SYM | Jet X 125 TCS ABS | 272 | 691 | 56 | 8.10% | 1.01 |
| TVS | Raider 125 | 210 | 410 | 33 | 8.05% | 0.93 |
| Honda | PCX125 | 1,273 | 3,368 | 255 | 7.57% | 1.09 |
| Honda | CB125F | 345 | 819 | 59 | 7.20% | 1.02 |
| TVS | Jupiter 125 | 857 | 2,640 | 181 | 6.86% | 1.03 |

### En düşük 15

| brand | model_name | motorcycle_count | service_count | failure_count | failure_rate | observed_expected_ratio |
|---|---|---|---|---|---|---|
| Mondial | SFC MINI 50ec | 318 | 3,234 | 92 | 2.84% | 0.99 |
| Kuba | Blueberry 50 | 370 | 4,525 | 134 | 2.96% | 1.10 |
| Mondial | Wing 50i | 652 | 3,512 | 119 | 3.39% | 0.96 |
| Mondial | 50 UAG | 421 | 2,769 | 98 | 3.54% | 1.07 |
| Mondial | Turismo 50i | 72 | 277 | 10 | 3.61% | 0.72 |
| Kuba | CG50 Pro | 510 | 2,407 | 88 | 3.66% | 0.88 |
| Honda | Dio 110 | 450 | 3,131 | 123 | 3.93% | 0.89 |
| RKS | New Light Pro | 386 | 2,011 | 94 | 4.67% | 1.00 |
| Yamaha | NMAX 125 | 463 | 3,014 | 146 | 4.84% | 0.99 |
| Honda | Forza 250 | 223 | 619 | 32 | 5.17% | 0.89 |
| Bajaj | Pulsar NS200 UG2 | 251 | 663 | 37 | 5.58% | 0.84 |
| Honda | Activa 125 | 1,051 | 3,333 | 193 | 5.79% | 0.93 |
| Mondial | Exon 50 | 97 | 299 | 18 | 6.02% | 1.18 |
| TVS | Jupiter 125 | 857 | 2,640 | 181 | 6.86% | 1.03 |
| Honda | CB125F | 345 | 819 | 59 | 7.20% | 1.02 |

`observed_expected_ratio`, yaş/km/kullanım/gecikme ve marka kontrollü modelin beklediği arıza sayısına göre residual göstergedir; 1.00 nötrdür.

## 6. Yaşa göre arıza

| brand | age_bucket | service_count | failure_count | failure_rate |
|---|---|---|---|---|
| Bajaj | 0–2 | 398 | 28 | 7.04% |
| Bajaj | 3–5 | 603 | 39 | 6.47% |
| Bajaj | 6–8 | 226 | 15 | 6.64% |
| Bajaj | 9+ | 14 | 0 | 0.00% |
| CFMOTO | 0–2 | 284 | 36 | 12.68% |
| CFMOTO | 3–5 | 481 | 58 | 12.06% |
| CFMOTO | 6–8 | 178 | 16 | 8.99% |
| CFMOTO | 9+ | 11 | 1 | 9.09% |
| Honda | 0–2 | 3,536 | 248 | 7.01% |
| Honda | 3–5 | 5,606 | 325 | 5.80% |
| Honda | 6–8 | 2,616 | 160 | 6.12% |
| Honda | 9+ | 394 | 21 | 5.33% |
| KYMCO | 0–2 | 112 | 12 | 10.71% |
| KYMCO | 3–5 | 161 | 13 | 8.07% |
| KYMCO | 6–8 | 56 | 5 | 8.93% |
| KYMCO | 9+ | 5 | 0 | 0.00% |
| Kuba | 0–2 | 2,106 | 75 | 3.56% |
| Kuba | 3–5 | 3,147 | 79 | 2.51% |
| Kuba | 6–8 | 1,440 | 64 | 4.44% |
| Kuba | 9+ | 239 | 4 | 1.67% |
| Mondial | 0–2 | 2,992 | 101 | 3.38% |
| Mondial | 3–5 | 4,630 | 162 | 3.50% |
| Mondial | 6–8 | 2,160 | 62 | 2.87% |
| Mondial | 9+ | 309 | 12 | 3.88% |
| RKS | 0–2 | 609 | 22 | 3.61% |
| RKS | 3–5 | 868 | 45 | 5.18% |
| RKS | 6–8 | 442 | 23 | 5.20% |
| RKS | 9+ | 92 | 4 | 4.35% |
| SYM | 0–2 | 208 | 19 | 9.13% |
| SYM | 3–5 | 301 | 23 | 7.64% |
| SYM | 6–8 | 163 | 14 | 8.59% |
| SYM | 9+ | 19 | 0 | 0.00% |
| TVS | 0–2 | 929 | 79 | 8.50% |
| TVS | 3–5 | 1,544 | 113 | 7.32% |
| TVS | 6–8 | 651 | 42 | 6.45% |
| TVS | 9+ | 104 | 9 | 8.65% |
| Yamaha | 0–2 | 1,088 | 67 | 6.16% |
| Yamaha | 3–5 | 1,734 | 84 | 4.84% |
| Yamaha | 6–8 | 784 | 60 | 7.65% |
| Yamaha | 9+ | 91 | 2 | 2.20% |

**Honda yaş açıklaması: PARTIALLY.** Honda ham oranı 6.20%; RKS/Mondial/Kuba servis-ağırlıklı oranı 3.43% (fark 2.77 puan). Yaş/km/kullanım/gecikme kontrolü sonrası Honda 5.75%, üçlü basit ortalama 4.51% (fark 1.23 puan).

## 7. Servis odometer bandına göre arıza

| brand | km_bucket | service_count | failure_count | failure_rate |
|---|---|---|---|---|
| Bajaj | 0–10k | 163 | 13 | 7.98% |
| Bajaj | 10–25k | 417 | 27 | 6.47% |
| Bajaj | 25–50k | 348 | 28 | 8.05% |
| Bajaj | 50–75k | 157 | 7 | 4.46% |
| Bajaj | 75k+ | 156 | 7 | 4.49% |
| CFMOTO | 0–10k | 169 | 23 | 13.61% |
| CFMOTO | 10–25k | 286 | 38 | 13.29% |
| CFMOTO | 25–50k | 291 | 37 | 12.71% |
| CFMOTO | 50–75k | 130 | 9 | 6.92% |
| CFMOTO | 75k+ | 78 | 4 | 5.13% |
| Honda | 0–10k | 796 | 85 | 10.68% |
| Honda | 10–25k | 2,085 | 169 | 8.11% |
| Honda | 25–50k | 3,438 | 228 | 6.63% |
| Honda | 50–75k | 2,201 | 114 | 5.18% |
| Honda | 75k+ | 3,632 | 158 | 4.35% |
| KYMCO | 0–10k | 42 | 8 | 19.05% |
| KYMCO | 10–25k | 94 | 10 | 10.64% |
| KYMCO | 25–50k | 107 | 7 | 6.54% |
| KYMCO | 50–75k | 36 | 1 | 2.78% |
| KYMCO | 75k+ | 55 | 4 | 7.27% |
| Kuba | 0–10k | 277 | 15 | 5.42% |
| Kuba | 10–25k | 839 | 36 | 4.29% |
| Kuba | 25–50k | 1,697 | 60 | 3.54% |
| Kuba | 50–75k | 1,343 | 26 | 1.94% |
| Kuba | 75k+ | 2,776 | 85 | 3.06% |
| Mondial | 0–10k | 492 | 21 | 4.27% |
| Mondial | 10–25k | 1,408 | 61 | 4.33% |
| Mondial | 25–50k | 2,571 | 94 | 3.66% |
| Mondial | 50–75k | 1,894 | 62 | 3.27% |
| Mondial | 75k+ | 3,726 | 99 | 2.66% |
| RKS | 0–10k | 88 | 7 | 7.95% |
| RKS | 10–25k | 245 | 19 | 7.76% |
| RKS | 25–50k | 476 | 25 | 5.25% |
| RKS | 50–75k | 374 | 15 | 4.01% |
| RKS | 75k+ | 828 | 28 | 3.38% |
| SYM | 0–10k | 56 | 4 | 7.14% |
| SYM | 10–25k | 144 | 19 | 13.19% |
| SYM | 25–50k | 156 | 12 | 7.69% |
| SYM | 50–75k | 107 | 12 | 11.21% |
| SYM | 75k+ | 228 | 9 | 3.95% |
| TVS | 0–10k | 259 | 31 | 11.97% |
| TVS | 10–25k | 660 | 62 | 9.39% |
| TVS | 25–50k | 1,070 | 71 | 6.64% |
| TVS | 50–75k | 602 | 46 | 7.64% |
| TVS | 75k+ | 637 | 33 | 5.18% |
| Yamaha | 0–10k | 154 | 11 | 7.14% |
| Yamaha | 10–25k | 460 | 45 | 9.78% |
| Yamaha | 25–50k | 803 | 52 | 6.48% |
| Yamaha | 50–75k | 718 | 38 | 5.29% |
| Yamaha | 75k+ | 1,562 | 67 | 4.29% |

**Aynı km bandı cevabı:** Yeterli örnekli 15 Honda–marka karşılaştırmasının 15'inde Honda oranı daha yüksek.

| km_band | comparison | honda_rate | other_rate | difference_pp |
|---|---|---|---|---|
| 0–10k | Honda vs RKS | 10.68% | 7.95% | +2.72 |
| 0–10k | Honda vs Mondial | 10.68% | 4.27% | +6.41 |
| 0–10k | Honda vs Kuba | 10.68% | 5.42% | +5.26 |
| 10–25k | Honda vs RKS | 8.11% | 7.76% | +0.35 |
| 10–25k | Honda vs Mondial | 8.11% | 4.33% | +3.77 |
| 10–25k | Honda vs Kuba | 8.11% | 4.29% | +3.81 |
| 25–50k | Honda vs RKS | 6.63% | 5.25% | +1.38 |
| 25–50k | Honda vs Mondial | 6.63% | 3.66% | +2.98 |
| 25–50k | Honda vs Kuba | 6.63% | 3.54% | +3.10 |
| 50–75k | Honda vs RKS | 5.18% | 4.01% | +1.17 |
| 50–75k | Honda vs Mondial | 5.18% | 3.27% | +1.91 |
| 50–75k | Honda vs Kuba | 5.18% | 1.94% | +3.24 |
| 75k+ | Honda vs RKS | 4.35% | 3.38% | +0.97 |
| 75k+ | Honda vs Mondial | 4.35% | 2.66% | +1.69 |
| 75k+ | Honda vs Kuba | 4.35% | 3.06% | +1.29 |

## 8. Kullanım şiddeti ve profil dengesi

### usage_type

| usage_type | service_count | failure_count | failure_rate |
|---|---|---|---|
| TRACK | 633 | 113 | 17.85% |
| OFFROAD | 144 | 21 | 14.58% |
| WEEKEND | 3,152 | 273 | 8.66% |
| SEASONAL | 1,879 | 132 | 7.03% |
| TOURING | 1,360 | 77 | 5.66% |
| COMMUTER | 16,994 | 950 | 5.59% |
| COURIER | 17,356 | 586 | 3.38% |

### riding_intensity

| riding_intensity | service_count | failure_count | failure_rate |
|---|---|---|---|
| LOW | 13,694 | 1,121 | 8.19% |
| MEDIUM | 11,583 | 498 | 4.30% |
| HIGH | 16,241 | 533 | 3.28% |

### storage_condition

| storage_condition | service_count | failure_count | failure_rate |
|---|---|---|---|
| GARAGE | 13,010 | 712 | 5.47% |
| STREET | 12,746 | 668 | 5.24% |
| COVERED_PARKING | 13,718 | 673 | 4.91% |
| INDOOR | 2,044 | 99 | 4.84% |

### climate_zone

| climate_zone | service_count | failure_count | failure_rate |
|---|---|---|---|
| CONTINENTAL_COOL | 3,206 | 176 | 5.49% |
| TEMPERATE_HUMID | 8,329 | 454 | 5.45% |
| HUMID_RAINY | 3,556 | 193 | 5.43% |
| MEDITERRANEAN_COASTAL | 4,454 | 235 | 5.28% |
| SEMI_ARID_HOT | 5,189 | 270 | 5.20% |
| CONTINENTAL_DRY | 7,562 | 387 | 5.12% |
| MEDITERRANEAN_HOT | 9,222 | 437 | 4.74% |

### annual_km_band

| annual_km_band | service_count | failure_count | failure_rate |
|---|---|---|---|
| <=6k | 2,160 | 262 | 12.13% |
| 6–12k | 11,771 | 870 | 7.39% |
| 12–20k | 10,785 | 475 | 4.40% |
| 20k+ | 16,802 | 545 | 3.24% |

### load_band

| load_band | service_count | failure_count | failure_rate |
|---|---|---|---|
| <0.95 | 1,490 | 112 | 7.52% |
| 0.95–1.05 | 15,810 | 1,111 | 7.03% |
| 1.05–1.15 | 13,184 | 600 | 4.55% |
| 1.15+ | 11,034 | 329 | 2.98% |

### COURIER / TRACK / OFFROAD marka payları

| brand | COURIER | OFFROAD | TRACK |
|---|---|---|---|
| Bajaj | 0.6% | 0.0% | 0.0% |
| CFMOTO | 0.0% | 2.3% | 34.8% |
| Honda | 10.5% | 0.7% | 0.7% |
| Kuba | 42.3% | 0.0% | 0.0% |
| Mondial | 23.6% | 0.0% | 0.0% |
| RKS | 39.1% | 0.0% | 0.0% |
| SYM | 7.0% | 0.0% | 0.0% |
| TVS | 0.0% | 0.0% | 5.7% |
| Yamaha | 53.2% | 0.3% | 6.5% |

## 9. Bakım gecikmesi

| delay_bucket | service_count | failure_count | failure_rate |
|---|---|---|---|
| <=0 gün | 11,080 | 2,152 | 19.42% |
| 1–7 | 12,183 | 0 | 0.00% |
| 8–30 | 17,286 | 0 | 0.00% |
| 31–60 | 969 | 0 | 0.00% |
| 60+ | 0 | 0 | — |

| brand | avg_service_delay_days | avg_periodic_delay_days |
|---|---|---|
| KYMCO | 12.18 | 13.60 |
| Bajaj | 11.13 | 12.00 |
| CFMOTO | 10.37 | 12.03 |
| TVS | 9.67 | 10.63 |
| Honda | 8.62 | 9.32 |
| Mondial | 7.99 | 8.33 |
| SYM | 7.93 | 8.74 |
| Kuba | 7.76 | 8.07 |
| Yamaha | 7.38 | 7.93 |
| RKS | 7.27 | 7.70 |

**Nedensellik cevabı:** Hayır, bu alanla savunulamaz. REPAIR/BREAKDOWN kayıtlarının 2,152/2,152 tanesinde `service_delay_days=0`; dolayısıyla alan servis türünden sonra yapısal biçimde belirlenmiş ve arıza riskinin öncül gecikme exposure'ı değildir.

## 10. Garanti analizi

| brand | service_count | warranty_service_count | warranty_service_rate |
|---|---|---|---|
| RKS | 2,011 | 85 | 4.23% |
| Honda | 12,152 | 447 | 3.68% |
| CFMOTO | 954 | 34 | 3.56% |
| TVS | 3,228 | 114 | 3.53% |
| Mondial | 10,091 | 354 | 3.51% |
| Yamaha | 3,697 | 124 | 3.35% |
| Kuba | 6,932 | 231 | 3.33% |
| SYM | 691 | 23 | 3.33% |
| Bajaj | 1,241 | 38 | 3.06% |
| KYMCO | 334 | 10 | 2.99% |
| KTM | 123 | 3 | 2.44% |
| Royal Enfield | 64 | 1 | 1.56% |

### Üretim yaşı

| age_bucket | service_count | warranty_service_count | warranty_service_rate |
|---|---|---|---|
| 0–2 | 12,326 | 437 | 3.55% |
| 3–5 | 19,162 | 696 | 3.63% |
| 6–8 | 8,748 | 275 | 3.14% |
| 9+ | 1,282 | 56 | 4.37% |

### İlk kayıt tarihinden beri yaş

| reg_bucket | service_count | warranty_service_count | warranty_service_rate |
|---|---|---|---|
| 0–2 | 8,452 | 319 | 3.77% |
| 3–5 | 20,230 | 723 | 3.57% |
| 6–8 | 10,743 | 341 | 3.17% |
| 9+ | 2,093 | 81 | 3.87% |

### Servis türü

| service_type_code | service_count | warranty_service_count | breakdown_count | warranty_service_rate |
|---|---|---|---|---|
| BREAKDOWN | 993 | 24 | 993 | 2.42% |
| PERIODIC | 38,931 | 1,380 | 0 | 3.54% |
| REPAIR | 1,159 | 44 | 0 | 3.80% |
| TIRE | 435 | 16 | 0 | 3.68% |

**Garanti yeni motosikletlerde yoğun mu? NO.** İlk kayıt yaşı 0–2'de 3.77%, 9+'da 3.87%.

## 11. REPAIR / BREAKDOWN task analizi

Arıza servislerinde **7,025 task** var; taxonomy'de fault-based pay 85.37%, periodic-only pay 14.63%.

### En sık 20 task

| task_code | canonical_name_tr | task_count | share_of_failure_tasks |
|---|---|---|---|
| ECU_DIAGNOSTIC_SCAN | ECU Arıza Taraması | 832 | 11.84% |
| WHEEL_BEARING_CHANGE | Teker Rulmanı Değişimi | 414 | 5.89% |
| FORK_SEAL_CHANGE | Amortisör Keçesi Değişimi | 412 | 5.86% |
| BATTERY_CHANGE | Akü Değişimi | 399 | 5.68% |
| BRAKE_DISC_CHANGE | Fren Diski Değişimi | 391 | 5.57% |
| VALVE_CLEARANCE_ADJUST | Supap Boşluğu Ayarı | 387 | 5.51% |
| STEERING_BEARING_CHANGE | Gidon Rulmanı Değişimi | 387 | 5.51% |
| THROTTLE_BODY_CLEAN | Gaz Kelebeği Temizliği | 383 | 5.45% |
| FUEL_INJECTOR_CLEAN | Enjektör Temizliği | 373 | 5.31% |
| BRAKE_SYSTEM_BLEED | Fren Sisteminin Havasını Alma | 373 | 5.31% |
| BATTERY_TEST | Akü Testi | 225 | 3.20% |
| ENGINE_COMPRESSION_TEST | Motor Kompresyon Testi | 220 | 3.13% |
| CHARGING_SYSTEM_TEST | Şarj Sistemi Testi | 217 | 3.09% |
| STEERING_BEARING_INSPECTION | Gidon Rulmanı Kontrolü | 214 | 3.05% |
| OIL_LEAK_INSPECTION | Motor Yağ Kaçağı Kontrolü | 212 | 3.02% |
| INTAKE_LEAK_INSPECTION | Emme Sistemi Kaçak Kontrolü | 211 | 3.00% |
| BRAKE_DISC_INSPECTION | Fren Diski Kontrolü | 210 | 2.99% |
| ABS_DIAGNOSTIC | ABS Sistem Teşhisi | 207 | 2.95% |
| FUEL_SYSTEM_DIAGNOSTIC | Yakıt Sistemi Arıza Teşhisi | 204 | 2.90% |
| WHEEL_BEARING_INSPECTION | Teker Rulmanı Kontrolü | 191 | 2.72% |

### Component group

| component_group | task_count | share |
|---|---|---|
| ELECTRICAL | 1,673 | 23.81% |
| BRAKES | 1,181 | 16.81% |
| ENGINE | 819 | 11.66% |
| TIRES_WHEELS | 605 | 8.61% |
| STEERING | 601 | 8.56% |
| SUSPENSION | 599 | 8.53% |
| INTAKE | 594 | 8.46% |
| FUEL | 577 | 8.21% |
| TRANSMISSION | 292 | 4.16% |
| COOLING | 81 | 1.15% |
| EV_POWERTRAIN | 3 | 0.04% |

İstenen grupların sayıları: ENGINE **819**, ELECTRICAL **1,673**, BRAKES **1,181**, COOLING **81**, TRANSMISSION **292**, FINAL_DRIVE **0**. Sonuç: taskların 85.37% kadarı arıza mantığına doğrudan uygun; ancak 14.63% periodic-only eşlikçi iş ve FINAL_DRIVE kanalının sıfır olması generator düzeltmesi gerektiriyor.

## 12. Declined task analizi

Payda, üretilmiş her `service_tasks` satırını teklif olarak kabul eder; pay `status=DECLINED`. Sıralama yalnız total_offered ≥ 250 tasklar içindir.

| task_code | canonical_name_tr | total_offered | declined_count | declined_rate |
|---|---|---|---|---|
| WHEEL_BEARING_CHANGE | Teker Rulmanı Değişimi | 414 | 10 | 2.42% |
| THROTTLE_BODY_CLEAN | Gaz Kelebeği Temizliği | 383 | 6 | 1.57% |
| REAR_BRAKE_PAD_INSPECTION | Arka Fren Balatası Kontrolü | 1,470 | 20 | 1.36% |
| STEERING_BEARING_CHANGE | Gidon Rulmanı Değişimi | 387 | 5 | 1.29% |
| REAR_TIRE_INSPECTION | Arka Lastik Kontrolü | 1,706 | 19 | 1.11% |
| FRONT_BRAKE_PAD_INSPECTION | Ön Fren Balatası Kontrolü | 3,814 | 37 | 0.97% |
| SPARK_PLUG_CHANGE | Buji Değişimi | 2,101 | 19 | 0.90% |
| BATTERY_TEST | Akü Testi | 16,335 | 146 | 0.89% |
| VALVE_CLEARANCE_INSPECTION | Supap Boşluğu Kontrolü | 3,493 | 31 | 0.89% |
| CVT_ROLLER_INSPECTION | Varyatör Ruloları Kontrolü | 3,758 | 33 | 0.88% |
| FORK_INSPECTION | Ön Amortisör Kontrolü | 5,195 | 45 | 0.87% |
| BRAKE_FLUID_CHECK | Fren Hidroliği Kontrolü | 14,329 | 123 | 0.86% |
| CHAIN_CLEAN | Zincir Temizliği | 10,988 | 91 | 0.83% |
| REAR_TIRE_CHANGE | Arka Lastik Değişimi | 365 | 3 | 0.82% |
| CVT_BELT_INSPECTION | CVT Kayışı Kontrolü | 5,111 | 42 | 0.82% |

**ENGINE_OIL_CHANGE:** 38,882 teklif, 148 red, 0.38%; absolute red sayısı esas olarak yüksek teklif hacmiyle açıklanıyor; oran tek başına aşırı görünmüyor.

## 13. Standardize edilmiş marka karşılaştırması

Ridge-stabilize lojistik standardizasyon: target birleşik failure; age, log(odometer), usage_type, log(annual_km), log(service_delay+1), riding_intensity, load_severity_factor ve brand. 41,518 servis, 14 iterasyon, yakınsama **YES**. Model başarısı ölçülmedi; amaç confounder kontrolü. Sınıflama: pooled oranın %90 altı `DAHA DÜŞÜK`, %110 üstü `DAHA YÜKSEK`, arası `ORTALAMA`.

| brand | service_count | raw_failure_service_rate | adjusted_failure_probability | adjusted_index_vs_pooled | classification |
|---|---|---|---|---|---|
| KYMCO | 334 | 8.98% | 7.22% | 1.39 | DAHA YÜKSEK |
| SYM | 691 | 8.10% | 6.90% | 1.33 | DAHA YÜKSEK |
| Yamaha | 3,697 | 5.76% | 6.30% | 1.21 | DAHA YÜKSEK |
| TVS | 3,228 | 7.53% | 6.13% | 1.18 | DAHA YÜKSEK |
| CFMOTO | 954 | 11.64% | 5.91% | 1.14 | DAHA YÜKSEK |
| Honda | 12,152 | 6.20% | 5.75% | 1.11 | DAHA YÜKSEK |
| RKS | 2,011 | 4.67% | 5.57% | 1.07 | ORTALAMA |
| Bajaj | 1,241 | 6.61% | 4.97% | 0.96 | ORTALAMA |
| Kuba | 6,932 | 3.20% | 4.04% | 0.78 | DAHA DÜŞÜK |
| Mondial | 10,091 | 3.34% | 3.93% | 0.76 | DAHA DÜŞÜK |

Bu sınıflar yalnız **dataset içinde üretilmiş failure propensity** gösterir.

## 14. Generator bias taraması

- **A/H — Brand ve aynı-risk profili:** Ayarlı marka oranlarının genişliği, brand/model ile ilişkili residual risk bulunduğunu gösterir; fakat tablolardan bunun doğrudan kodlanmış mı yoksa ilişkili başka latent değişkenden mi geldiği kanıtlanamaz.
- **B — Model_id:** `observed_expected_ratio` tablosu, yeterli örnekli modellerde age/km/usage/delay/brand sonrası residual farkları gösterir.
- **C/F — Kullanım dengesizliği:** COURIER/TRACK/OFFROAD pay tablosunda ölçülmüştür; ham marka kıyasında confounder'dır.
- **D — Production year:**

| brand | mean_production_year | min_production_year | max_production_year | production_year_sd |
|---|---|---|---|---|
| Mondial | 2,020.93 | 2,015 | 2,026 | 2.45 |
| RKS | 2,020.94 | 2,015 | 2,026 | 2.58 |
| SYM | 2,020.94 | 2,015 | 2,026 | 2.47 |
| Honda | 2,020.96 | 2,015 | 2,026 | 2.41 |
| Yamaha | 2,020.97 | 2,015 | 2,026 | 2.31 |
| TVS | 2,020.99 | 2,015 | 2,026 | 2.36 |
| Kuba | 2,021.03 | 2,015 | 2,026 | 2.45 |
| Bajaj | 2,021.13 | 2,016 | 2,026 | 2.20 |
| CFMOTO | 2,021.24 | 2,016 | 2,026 | 2.17 |
| KYMCO | 2,021.26 | 2,016 | 2,026 | 2.14 |

- **E — service_delay:** Marka ortalamaları yukarıda; arıza servislerindeki yapısal sıfır nedeniyle causal açıklama olarak kullanılamaz.
- **G — Breakdown / powertrain / category:**

| powertrain_type | service_count | breakdown_count | breakdown_rate |
|---|---|---|---|
| EV | 56 | 2 | 3.57% |
| ICE | 41,462 | 991 | 2.39% |

| category | service_count | breakdown_count | breakdown_rate |
|---|---|---|---|
| CRUISER | 23 | 2 | 8.70% |
| SUPERSPORT | 155 | 13 | 8.39% |
| MINI_BIKE | 37 | 3 | 8.11% |
| SCRAMBLER | 164 | 10 | 6.10% |
| TOURING | 126 | 6 | 4.76% |
| BIG_SCOOTER | 1,707 | 68 | 3.98% |
| NAKED | 3,364 | 132 | 3.92% |
| ROADSTER | 136 | 5 | 3.68% |
| EV_SCOOTER | 56 | 2 | 3.57% |
| ADVENTURE | 136 | 4 | 2.94% |
| SCOOTER | 25,193 | 576 | 2.29% |
| CUB | 10,421 | 172 | 1.65% |

EV örneği çok küçük (3 failure service). Bu servislerde 13 task ve ICE-only component grubunda 0 task var; mevcut küçük örnekte açık powertrain uyumsuzluğu görülmedi. Düşük servis sayılı category oranları güvenilir sıralama olarak yorumlanmamalı.

## 15. Şüpheli sonuçlar

| Problem | Etkilenen Marka/Model | Bulgular | Olası Sebep | Önem |
|---|---|---|---|---|
| Kontrol sonrası marka etkisi çok geniş | KYMCO / Mondial | Standartlaştırılmış oran oranı 1.83x | Yaş/km/kullanım dışı marka/model risk katsayısı veya üretim kuralı | HIGH |
| Arıza servislerinde gecikme alanı yapısal sıfır | Tüm markalar | 2,152/2,152 arıza kaydında delay=0 | Unscheduled servislerde gecikmenin otomatik sıfırlanması | HIGH |
| Honda ayarlı oranı karşılaştırma grubunun üstünde kalıyor | Honda vs RKS/Mondial/Kuba | Ayarlı 5.75% vs 4.51%; aynı-km karşılaştırmalarının 15/15 tanesinde daha yüksek | Yaş/km/kullanım dışı brand/model baseline farkı | HIGH |
| Garanti oranı yaşla monoton düşmüyor | Tüm markalar | Kayıt yaşı 0–2: 3.77%; 9+: 3.87% | Garanti olasılığının yaş/tescil/kilometreye yeterince bağlanmaması | HIGH |
| Riskli kullanım profili marka bazında dengesiz | COURIER | Markalar arası pay aralığı 53.2% | Profil atama ağırlıkları marka/model karmasıyla ilişkili | MEDIUM |
| Final-drive arıza kanalı görünmüyor | Zincir/kayış aktarmalı modeller | 7,025 arıza taskı içinde FINAL_DRIVE=0 | FINAL_DRIVE task taxonomy'sinde fault-based görev eksikliği veya senaryo seçimine dahil edilmemesi | MEDIUM |
| Yeterli örnekli modellerde açıklanamayan residual fark | ADV350 / Turismo 50i | Observed/expected 1.35x vs 0.72x | Model_id düzeyinde risk parametresi | MEDIUM |
| Motor yağı değişimi absolute red sayısında görünür | ENGINE_OIL_CHANGE | 148/38,882 = 0.38% | Yüksek teklif hacmi; oran tek başına aşırı olmayabilir | LOW |

# RideBase Reliability Audit Özeti

## 1. Ham marka arıza oranları

| brand | motorcycle_count | service_count | repair_count | breakdown_count | repair_breakdown_count | raw_failure_service_rate |
|---|---|---|---|---|---|---|
| CFMOTO | 443 | 954 | 57 | 54 | 111 | 11.64% |
| KYMCO | 156 | 334 | 17 | 13 | 30 | 8.98% |
| SYM | 272 | 691 | 27 | 29 | 56 | 8.10% |
| TVS | 1,148 | 3,228 | 140 | 103 | 243 | 7.53% |
| Bajaj | 527 | 1,241 | 41 | 41 | 82 | 6.61% |
| Honda | 3,772 | 12,152 | 421 | 333 | 754 | 6.20% |
| Yamaha | 759 | 3,697 | 110 | 103 | 213 | 5.76% |
| RKS | 386 | 2,011 | 52 | 42 | 94 | 4.67% |
| Mondial | 1,560 | 10,091 | 175 | 162 | 337 | 3.34% |
| Kuba | 880 | 6,932 | 112 | 110 | 222 | 3.20% |

## 2. 10.000 km başına arıza

| brand | total_observed_km | repair_breakdown_count | failure_events_per_10000_km |
|---|---|---|---|
| CFMOTO | 8,023,218 | 111 | 0.1383 |
| KYMCO | 3,473,275 | 30 | 0.0864 |
| Bajaj | 10,010,474 | 82 | 0.0819 |
| SYM | 6,894,649 | 56 | 0.0812 |
| TVS | 32,247,753 | 243 | 0.0754 |
| Honda | 127,235,899 | 754 | 0.0593 |
| Yamaha | 37,648,992 | 213 | 0.0566 |
| Mondial | 62,139,352 | 337 | 0.0542 |
| RKS | 17,865,143 | 94 | 0.0526 |
| Kuba | 42,805,087 | 222 | 0.0519 |

## 3. Yaş/km kontrolü sonrası dikkat çeken markalar

| brand | adjusted_failure_probability | adjusted_index_vs_pooled | classification |
|---|---|---|---|
| KYMCO | 7.22% | 1.39 | DAHA YÜKSEK |
| SYM | 6.90% | 1.33 | DAHA YÜKSEK |
| Yamaha | 6.30% | 1.21 | DAHA YÜKSEK |
| TVS | 6.13% | 1.18 | DAHA YÜKSEK |
| CFMOTO | 5.91% | 1.14 | DAHA YÜKSEK |
| Honda | 5.75% | 1.11 | DAHA YÜKSEK |
| RKS | 5.57% | 1.07 | ORTALAMA |
| Bajaj | 4.97% | 0.96 | ORTALAMA |
| Kuba | 4.04% | 0.78 | DAHA DÜŞÜK |
| Mondial | 3.93% | 0.76 | DAHA DÜŞÜK |

## 4. En yüksek model arıza oranları

| brand | model_name | motorcycle_count | service_count | failure_count | failure_rate |
|---|---|---|---|---|---|
| CFMOTO | 250SR | 76 | 155 | 27 | 17.42% |
| TVS | Apache RTR 200 4V FI | 81 | 178 | 29 | 16.29% |
| Honda | CL250 | 62 | 164 | 24 | 14.63% |
| CFMOTO | 250NK | 156 | 357 | 48 | 13.45% |
| Yamaha | XSR125 | 74 | 151 | 20 | 13.25% |
| Honda | ADV350 | 118 | 222 | 25 | 11.26% |
| KYMCO | X-Town CT 250 | 83 | 198 | 19 | 9.60% |
| Yamaha | XMAX 250 | 222 | 532 | 47 | 8.83% |
| Honda | SH125i | 194 | 403 | 33 | 8.19% |
| Bajaj | Pulsar NS125 | 214 | 452 | 37 | 8.19% |

## 5. Garanti davranışı

NO: Garanti yaşla yeterince düşmüyor; 0–2 3.77%, 9+ 3.87%.

## 6. Declined bakım görevleri

| task_code | canonical_name_tr | total_offered | declined_count | declined_rate |
|---|---|---|---|---|
| WHEEL_BEARING_CHANGE | Teker Rulmanı Değişimi | 414 | 10 | 2.42% |
| THROTTLE_BODY_CLEAN | Gaz Kelebeği Temizliği | 383 | 6 | 1.57% |
| REAR_BRAKE_PAD_INSPECTION | Arka Fren Balatası Kontrolü | 1,470 | 20 | 1.36% |
| STEERING_BEARING_CHANGE | Gidon Rulmanı Değişimi | 387 | 5 | 1.29% |
| REAR_TIRE_INSPECTION | Arka Lastik Kontrolü | 1,706 | 19 | 1.11% |
| FRONT_BRAKE_PAD_INSPECTION | Ön Fren Balatası Kontrolü | 3,814 | 37 | 0.97% |
| SPARK_PLUG_CHANGE | Buji Değişimi | 2,101 | 19 | 0.90% |
| BATTERY_TEST | Akü Testi | 16,335 | 146 | 0.89% |
| VALVE_CLEARANCE_INSPECTION | Supap Boşluğu Kontrolü | 3,493 | 31 | 0.89% |
| CVT_ROLLER_INSPECTION | Varyatör Ruloları Kontrolü | 3,758 | 33 | 0.88% |

## 7. Generator'da değiştirilmesi önerilen şeyler

1. **Marka/model risk katsayılarını kalibre et.** Sorun/neden: Ayarlı oranlar arasında büyük fark kalıyorsa marka etkisi confounder'lardan bağımsız üretiliyor olabilir. Etkilenen alan: `services.service_type_code, motorcycles.brand/model_id`. Öneri: Temel tehlikeyi marka yerine parça/powertrain/category ve doğrulanabilir model özelliklerinden türet; marka residualını sınırla.
2. **Bakım gecikmesi ile unscheduled servis gecikmesini ayır.** Sorun/neden: Tüm REPAIR/BREAKDOWN kayıtlarında delay=0 olması gecikme–arıza ilişkisini ters/yanıltıcı gösteriyor. Etkilenen alan: `services.service_delay_days, service_type_code`. Öneri: service_delay_days'i yalnız planlı bakım için tut; ayrıca overdue_maintenance_days_at_failure üret.
3. **Kullanım profili atamasını marka içinde dengele.** Sorun/neden: COURIER/TRACK/OFFROAD pay farkları ham marka oranlarını etkileyebilir. Etkilenen alan: `usage_profiles.usage_type/riding_intensity/load_severity_factor`. Öneri: Marka başına hedef profil dağılımı veya post-stratified kota uygula; model/category gerekçesini ayrı sakla.
4. **Arıza senaryosu task seçimini fault taxonomy ile kısıtla.** Sorun/neden: Fault-based olmayan periyodik tasklar arıza servisinin nedenini bulanıklaştırabilir. Etkilenen alan: `service_tasks.task_code, maintenance_tasks.is_fault_based/is_periodic`. Öneri: En az bir primary fault task zorunlu kıl; ek periyodik işleri secondary/opportunistic olarak etiketle.
5. **Model residual oranlarını shrinkage ile sınırla.** Sorun/neden: Örnekli modellerde observed/expected farkı model_id'ye doğrudan risk verilmiş olabileceğini düşündürür. Etkilenen alan: `motorcycles.model_id, services.service_type_code`. Öneri: Model etkilerini hiyerarşik/partial-pooling mantığıyla daralt ve minimum örnek eşiğiyle doğrula.
6. **Redleri count yerine teklif-bazlı oranla kalibre et.** Sorun/neden: Yağ değişimindeki absolute red sayısı yüksek teklif hacminden kaynaklanabilir. Etkilenen alan: `service_tasks.status/task_code`. Öneri: Task-specific declined_rate hedefleri ve minimum offered kontrolü kullan.
7. **Garanti olasılığını kayıt/üretim yaşına monoton bağla.** Sorun/neden: Garanti güvenilirlikten ayrı bir süreçtir ve yaşla açıkça azalmalıdır. Etkilenen alan: `services.is_warranty, motorcycles.first_registration_date/production_year`. Öneri: Garanti süresi + kilometre limiti + uygun service_type kuralı kullan.
8. **Kronik arızayı açık latent durumla üret ve sınırla.** Sorun/neden: 2+ arızalar rastgele tekrar mı yoksa kronik durum mu olduğu anlaşılmadan kümelenebilir. Etkilenen alan: `motorcycle_id, services.service_type_code`. Öneri: chronic_risk_tier alanı ekle; tekrar hazardına tavan ve component-level recurrence kuralı koy.
9. **Arıza maruziyetini km-zaman çiftine bağla.** Sorun/neden: Servis oranı kullanım farkından etkilenir. Etkilenen alan: `mileage_timeline_monthly.km_added, observation dates`. Öneri: Failure hazardını km + yaş üzerinden üret; rapor QA'sında her sürüm için /10k km ve /moto-year eşikleri koy.
10. **Sürüm QA kapıları ekle.** Sorun/neden: Generator bias ancak çok boyutlu kontrollerle yakalanıyor. Etkilenen alan: `Tüm temel tablolar`. Öneri: Her üretimde raw/adjusted marka, model min-N, usage balance, warranty monotonicity, repeat ve declined-rate testlerini çalıştır.
