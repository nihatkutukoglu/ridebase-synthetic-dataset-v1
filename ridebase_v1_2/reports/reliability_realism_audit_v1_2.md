# RideBase Synthetic Dataset v1.2 — Reliability Realism Audit

**Kapsam:** Generator iç gerçekçiliği; gerçek marka güvenilirliği iddiası değildir. Failure = `REPAIR` veya `BREAKDOWN`.

- Motosiklet: **10,000**
- Servis: **41,518**
- REPAIR: **1,778**
- BREAKDOWN: **422**
- Overall failure: **5.30%**
- Adjusted big-brand max/min: **1.342x**
- Release gate: **PASS**

## 1. Raw ve adjusted marka failure oranları

| brand         |   motorcycle_count |   service_count |   failure_count | raw_failure_rate   | adjusted_failure_rate   |   observed_expected_ratio |
|:--------------|-------------------:|----------------:|----------------:|:-------------------|:------------------------|--------------------------:|
| Bajaj         |                420 |            1241 |              44 | 3.55%              | 4.70%                   |                  0.886897 |
| CFMOTO        |                354 |             954 |              38 | 3.98%              | 5.33%                   |                  1.00641  |
| Honda         |               3100 |           12152 |             660 | 5.43%              | 5.38%                   |                  1.01617  |
| KTM           |                 42 |             123 |              10 | 8.13%              | 7.69%                   |                  1.4521   |
| KYMCO         |                124 |             334 |              17 | 5.09%              | 6.25%                   |                  1.18031  |
| Kuba          |                805 |            6932 |             364 | 5.25%              | 4.93%                   |                  0.930974 |
| Mondial       |               1383 |           10091 |             565 | 5.60%              | 5.27%                   |                  0.99465  |
| RKS           |                341 |            2011 |             115 | 5.72%              | 5.62%                   |                  1.06096  |
| Royal Enfield |                 33 |              64 |               2 | 3.12%              | 5.26%                   |                  0.993085 |
| SYM           |                214 |             691 |              31 | 4.49%              | 4.66%                   |                  0.879789 |
| TVS           |                970 |            3228 |             141 | 4.37%              | 5.02%                   |                  0.948212 |
| Yamaha        |                656 |            3697 |             213 | 5.76%              | 5.35%                   |                  1.00928  |

## 2. 10.000 km başına failure

| brand         |   observed_km |   failure_count |   failure_events_per_10000_km |
|:--------------|--------------:|----------------:|------------------------------:|
| Bajaj         |      10010474 |              44 |                     0.043954  |
| CFMOTO        |       8023218 |              38 |                     0.0473625 |
| Honda         |     127235899 |             660 |                     0.0518722 |
| KTM           |       1253445 |              10 |                     0.0797801 |
| KYMCO         |       3473275 |              17 |                     0.0489452 |
| Kuba          |      42805087 |             364 |                     0.0850366 |
| Mondial       |      62139352 |             565 |                     0.0909247 |
| RKS           |      17865143 |             115 |                     0.0643712 |
| Royal Enfield |        569081 |               2 |                     0.0351444 |
| SYM           |       6894649 |              31 |                     0.0449624 |
| TVS           |      32247753 |             141 |                     0.043724  |
| Yamaha        |      37648992 |             213 |                     0.0565752 |

## 3. Model observed/expected

Minimum karşılaştırma desteği: 50 motosiklet ve 150 servis.

| brand   | model_name           |   motorcycle_count |   service_count |   failure_count | failure_rate   |   observed_expected_ratio |
|:--------|:---------------------|-------------------:|----------------:|----------------:|:---------------|--------------------------:|
| Honda   | ADV350               |                 86 |             222 |              17 | 7.66%          |                  1.79276  |
| TVS     | Apache RTR 200 4V FI |                 68 |             178 |               8 | 4.49%          |                  1.25226  |
| Mondial | Turismo 50i          |                 60 |             277 |              16 | 5.78%          |                  1.23879  |
| Yamaha  | XSR125               |                 60 |             151 |               7 | 4.64%          |                  1.20318  |
| TVS     | Raider 125           |                174 |             410 |              18 | 4.39%          |                  1.16127  |
| Honda   | Forza 250            |                182 |             619 |              32 | 5.17%          |                  1.11231  |
| Yamaha  | XMAX 250             |                180 |             532 |              25 | 4.70%          |                  1.07881  |
| RKS     | New Light Pro        |                341 |            2011 |             115 | 5.72%          |                  1.06408  |
| Mondial | Wing 50i             |                585 |            3512 |             191 | 5.44%          |                  1.05967  |
| CFMOTO  | 250NK                |                126 |             357 |              14 | 3.92%          |                  1.04654  |
| Honda   | Activa 125           |                884 |            3333 |             180 | 5.40%          |                  1.00669  |
| Honda   | PCX125               |               1046 |            3368 |             167 | 4.96%          |                  1.00143  |
| Yamaha  | NMAX 125             |                416 |            3014 |             181 | 6.01%          |                  0.993528 |
| Honda   | Dio 110              |                404 |            3131 |             197 | 6.29%          |                  0.991094 |
| Mondial | 50 UAG               |                365 |            2769 |             161 | 5.81%          |                  0.985039 |
| Honda   | CL250                |                 54 |             164 |               7 | 4.27%          |                  0.983824 |
| Kuba    | Blueberry 50         |                346 |            4525 |             271 | 5.99%          |                  0.953017 |
| Mondial | SFC MINI 50ec        |                293 |            3234 |             186 | 5.75%          |                  0.936755 |
| Honda   | CB125F               |                257 |             819 |              35 | 4.27%          |                  0.932516 |
| Honda   | SH125i               |                143 |             403 |              18 | 4.47%          |                  0.909971 |
| TVS     | Jupiter 125          |                728 |            2640 |             115 | 4.36%          |                  0.903061 |
| KYMCO   | X-Town CT 250        |                 69 |             198 |               6 | 3.03%          |                  0.883441 |
| Kuba    | CG50 Pro             |                459 |            2407 |              93 | 3.86%          |                  0.869635 |
| Bajaj   | Pulsar NS125         |                154 |             452 |              18 | 3.98%          |                  0.867809 |
| SYM     | Jet X 125 TCS ABS    |                214 |             691 |              31 | 4.49%          |                  0.861663 |
| Mondial | Exon 50              |                 80 |             299 |              11 | 3.68%          |                  0.85241  |
| Bajaj   | Pulsar NS200 UG2     |                209 |             663 |              20 | 3.02%          |                  0.810534 |
| CFMOTO  | 250SR                |                 63 |             155 |               3 | 1.94%          |                  0.53503  |

## 4. Failure by age

| age_bucket   |   service_count |   failure_count | failure_rate   |
|:-------------|----------------:|----------------:|:---------------|
| 0–2          |           12326 |             407 | 3.30%          |
| 3–5          |           19162 |             984 | 5.14%          |
| 6–8          |            8748 |             674 | 7.70%          |
| 9+           |            1282 |             135 | 10.53%         |

## 5. Failure by odometer band

| km_bucket   |   service_count |   failure_count | failure_rate   |
|:------------|----------------:|----------------:|:---------------|
| 0–10k       |            2525 |              50 | 1.98%          |
| 10–25k      |            6702 |             190 | 2.83%          |
| 25–50k      |           11006 |             472 | 4.29%          |
| 50–75k      |            7591 |             406 | 5.35%          |
| 75k+        |           13694 |            1082 | 7.90%          |

## 6. Failure by usage type

| usage_type   |   service_count |   failure_count | failure_rate   |
|:-------------|----------------:|----------------:|:---------------|
| COMMUTER     |           19445 |             934 | 4.80%          |
| COURIER      |            7992 |             584 | 7.31%          |
| OFFROAD      |             755 |              51 | 6.75%          |
| SEASONAL     |            4207 |             172 | 4.09%          |
| TOURING      |            2465 |             149 | 6.04%          |
| TRACK        |             631 |              44 | 6.97%          |
| WEEKEND      |            6023 |             266 | 4.42%          |

## 7. Riding intensity

| riding_intensity   |   service_count |   failure_count | failure_rate   |
|:-------------------|----------------:|----------------:|:---------------|
| HIGH               |           22813 |            1430 | 6.27%          |
| LOW                |            5734 |             207 | 3.61%          |
| MEDIUM             |           12971 |             563 | 4.34%          |

## 8. Load severity

| load_band   |   service_count |   failure_count | failure_rate   |
|:------------|----------------:|----------------:|:---------------|
| <0.95       |            8998 |             360 | 4.00%          |
| 0.95–1.05   |           18631 |             866 | 4.65%          |
| 1.05–1.15   |           10697 |             702 | 6.56%          |
| 1.15+       |            3192 |             272 | 8.52%          |

## 9. Annual km exposure

| annual_km_band   |   service_count |   failure_count | failure_rate   |
|:-----------------|----------------:|----------------:|:---------------|
| LOW              |            6489 |             232 | 3.58%          |
| MEDIUM           |           13360 |             612 | 4.58%          |
| HIGH             |           10540 |             611 | 5.80%          |
| VERY_HIGH        |           11129 |             745 | 6.69%          |

## 10. Overdue maintenance

| overdue_bucket   |   service_count |   failure_count | failure_rate   |
|:-----------------|----------------:|----------------:|:---------------|
| 0                |           16255 |             730 | 4.49%          |
| 1–7              |           10601 |             637 | 6.01%          |
| 8–30             |           13965 |             791 | 5.66%          |
| 31–60            |             697 |              42 | 6.03%          |
| 60+              |               0 |               0 | NULL           |

## 11. Warranty by registration age

| warranty_age_bucket   |   service_count |   warranty_count | warranty_rate   |
|:----------------------|----------------:|-----------------:|:----------------|
| 0–2                   |            8452 |              159 | 1.88%           |
| 3–5                   |           20230 |               40 | 0.20%           |
| 6–8                   |           10743 |                0 | 0.00%           |
| 9+                    |            2093 |                0 | 0.00%           |

## 12. Repeat failure

- En az bir failure yaşayan motosiklet: **1,600**
- Tekrar failure yaşayan motosiklet: **358**
- 3+ failure: **128**

## 13. Fault component distribution

| primary_fault_component   |   failure_count |
|:--------------------------|----------------:|
| ENGINE                    |             373 |
| ELECTRICAL                |             318 |
| BRAKES                    |             289 |
| TRANSMISSION              |             201 |
| FUEL                      |             181 |
| COOLING                   |             178 |
| FINAL_DRIVE               |             168 |
| INTAKE                    |             147 |
| SUSPENSION                |             141 |
| TIRES_WHEELS              |             125 |
| STEERING                  |              79 |

## 14. FINAL_DRIVE

- FINAL_DRIVE failure event: **168**
- Failure service primary fault task coverage: **2,200/2,200**

## 15. Declined task rates

- Tüm task decline: **0.69%**
- ENGINE_OIL_CHANGE decline: **0.38%**

## 16. Honda vs RKS/Mondial/Kuba

- Honda adjusted: **5.38%**
- RKS adjusted: **5.62%**
- Mondial adjusted: **5.27%**
- Kuba adjusted: **4.93%**
- Aynı-km karşılaştırmalarında Honda daha yüksek: **9/15** (v1.1: 15/15)

## Gate sonucu

**PASS** — başarısız yüksek önem kontrolleri: yok
