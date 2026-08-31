# RideBase v1.2 vs v1.3 Regression Learnability

| Metric | V1.2 | V1.3 |
|---|---:|---:|
| Services | 41518 | 41518 |
| Snapshots | 41518 | 41518 |
| Observed | 33076 | 33076 |
| Censored | 8442 | 8442 |
| DAYS TEST MAE | 23.0416 | 22.7761 |
| DAYS TEST R² | 0.4172 | 0.6398 |
| KM TEST MAE | 1520.1541 | 969.4052 |
| KM TEST R² | 0.2355 | 0.4134 |
| Failure rate | 5.2989% | 5.2989% |
| Adjusted brand spread | 1.3416x | 1.3416x |
| Fault task coverage | v1.2 PASS | 2200/2200 |

R² yalnız gözlenebilir snapshot feature'larının sentetik target varyansını açıklama gücünü ölçer; production gerçekçiliği veya production performansı iddiası değildir.
