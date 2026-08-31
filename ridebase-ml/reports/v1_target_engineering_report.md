# RideBase 08 - V1 Target Engineering Report

## Executive Summary

Ayni SET_A base feature matrisi ve ayni standardize model (HistGradientBoostingRegressor default) sabit tutularak
8 target tanimi karsilastirildi. Leaderboard formulasyonu **V0_RESIDUAL_ANY**; onerilen urun hedefi **NEXT_ANY_SERVICE**.
RAW_ANY -> V0_RESIDUAL_ANY DAYS TEST R2 degisimi +0.007, KM -0.010.
Periodic vs Any DAYS TEST R2 farki -0.060 (periodic coverage 0.943). Production validation **BLOCKED**.

## Why Target Engineering

V1 Basic (0.417) ve V1 Advanced (0.435) DAYS R2 yakin; feature engineering / tuning / ensemble
kucuk kazanc verdi. Soru: model mi yetersiz, target mi fazla gurultulu? Bu notebook target tanimini degistirerek yaniti arar.

## Existing Regression Ceiling

| model | DAYS R2 | DAYS MAE | KM R2 | KM MAE |
|---|---|---|---|---|
| V0 Rule | -2.793 | 67.41 | -3.320 | 4515.3 |
| V1 Basic | 0.417 | 23.04 | 0.236 | 1520.2 |
| V1 Advanced | 0.435 | 22.21 | 0.248 | 1510.2 |

## Raw Target

| target   | split      |     n |      mean |    median |       std |        variance |   skewness |   coef_of_variation |       p95 |       p99 |       max |
|:---------|:-----------|------:|----------:|----------:|----------:|----------------:|-----------:|--------------------:|----------:|----------:|----------:|
| DAYS     | TRAIN      | 20679 |  159.569  |  111.953  |  151.178  | 22854.8         |   2.23161  |            0.947418 |   450.921 |   744.912 |  1343.89  |
| DAYS     | VALIDATION |  1932 |   62.8604 |   54.9337 |   35.86   |  1285.94        |   0.747201 |            0.570471 |   132.786 |   158.527 |   183.237 |
| DAYS     | TEST       |  2622 |   67.7746 |   57.9361 |   40.2762 |  1622.17        |   0.903601 |            0.594266 |   149.102 |   180.613 |   204.847 |
| KM       | TRAIN      | 20678 | 6762.51   | 5267.5    | 5032.12   |     2.53222e+07 |   2.33602  |            0.744119 | 16560.9   | 25613.2   | 63341     |
| KM       | VALIDATION |  1931 | 4433.39   | 3863      | 2441.94   |     5.96309e+06 |   1.5936   |            0.550807 |  9169     | 13017.2   | 18912     |
| KM       | TEST       |  2622 | 4530.25   | 3995.5    | 2478.32   |     6.14205e+06 |   1.54283  |            0.54706  |  9594.8   | 13360.2   | 20038     |

## Validation Results (standardized model)

| formulation           | family   | target   | model                                  |   train_rows |   val_rows |   coverage |   val_mae |   val_median_ae |   val_rmse |   val_r2 |   val_bias |   train_r2 |   val_within_a |   val_within_b |
|:----------------------|:---------|:---------|:---------------------------------------|-------------:|-----------:|-----------:|----------:|----------------:|-----------:|---------:|-----------:|-----------:|---------------:|---------------:|
| RAW_ANY               | ANY      | DAYS     | HistGradientBoostingRegressor(default) |        20679 |       1932 |     1      |   22.4714 |         16.7236 |    30.3631 |   0.2831 |     2.4354 |     0.5755 |         0.7774 |         0.9332 |
| V0_RESIDUAL_ANY       | ANY      | DAYS     | HistGradientBoostingRegressor(default) |        20679 |       1932 |     1      |   22.0923 |         15.5645 |    30.4066 |   0.281  |     0.4422 |     0.5902 |         0.7655 |         0.9337 |
| RAW_PERIODIC          | PERIODIC | DAYS     | HistGradientBoostingRegressor(default) |        20325 |       1841 |     0.9529 |   24.3258 |         19.5741 |    31.3785 |   0.2447 |     5.538  |     0.5572 |         0.7583 |         0.9299 |
| V0_RESIDUAL_PERIODIC  | PERIODIC | DAYS     | HistGradientBoostingRegressor(default) |        20325 |       1841 |     0.9529 |   23.6243 |         18.0887 |    31.4764 |   0.2399 |     2.4433 |     0.5733 |         0.7702 |         0.9283 |
| HISTORY_DEVIATION_ANY | ANY      | DAYS     | HistGradientBoostingRegressor(default) |        12027 |       1687 |     0.8732 |   22.6224 |         16.3856 |    31.6581 |   0.1957 |     2.059  |     0.5811 |         0.7659 |         0.9283 |
| LOG_ANY               | ANY      | DAYS     | HistGradientBoostingRegressor(default) |        20679 |       1932 |     1      |   31.8816 |         20.2865 |    44.8457 |  -0.5639 |   -29.1373 |     0.4572 |         0.5958 |         0.8157 |
| LOG_PERIODIC          | PERIODIC | DAYS     | HistGradientBoostingRegressor(default) |        20325 |       1841 |     0.9529 |   34.9384 |         24.9969 |    47.7921 |  -0.7522 |   -32.6591 |     0.4704 |         0.5568 |         0.7898 |
| POLICY_RATIO_ANY      | ANY      | DAYS     | HistGradientBoostingRegressor(default) |         1475 |         16 |     0.0083 |  135.897  |         61.2709 |   242.693  | -56.279  |   118.486  |     0.5574 |         0.3125 |         0.4375 |
| V0_RESIDUAL_ANY       | ANY      | KM       | HistGradientBoostingRegressor(default) |        20678 |       1931 |     0.9995 | 1511.25   |       1025.75   |  2245.59   |   0.1544 |  -273.614  |     0.3165 |         0.4878 |         0.7737 |
| RAW_ANY               | ANY      | KM       | HistGradientBoostingRegressor(default) |        20678 |       1931 |     0.9995 | 1482.75   |        944.125  |  2248.55   |   0.1521 |  -358.129  |     0.3312 |         0.5267 |         0.7727 |
| RAW_PERIODIC          | PERIODIC | KM       | HistGradientBoostingRegressor(default) |        20313 |       1836 |     0.9503 | 1569.37   |        984.309  |  2370.56   |   0.1377 |  -369.587  |     0.3188 |         0.5038 |         0.7603 |
| V0_RESIDUAL_PERIODIC  | PERIODIC | KM       | HistGradientBoostingRegressor(default) |        20313 |       1836 |     0.9503 | 1599.37   |       1018.22   |  2384.54   |   0.1275 |  -308.822  |     0.3561 |         0.4924 |         0.7527 |
| HISTORY_DEVIATION_ANY | ANY      | KM       | HistGradientBoostingRegressor(default) |        12026 |       1686 |     0.8727 | 1619.22   |       1077.89   |  2377.99   |   0.0735 |  -310.274  |     0.4306 |         0.4733 |         0.7402 |
| LOG_PERIODIC          | PERIODIC | KM       | HistGradientBoostingRegressor(default) |        20313 |       1836 |     0.9503 | 1950.11   |       1218.61   |  2913.23   |  -0.3022 | -1716.21   |     0.1776 |         0.4542 |         0.6422 |
| LOG_ANY               | ANY      | KM       | HistGradientBoostingRegressor(default) |        20678 |       1931 |     0.9995 | 1925.79   |       1259.89   |  2811.24   |  -0.3253 | -1720.46   |     0.179  |         0.4412 |         0.6479 |
| POLICY_RATIO_ANY      | ANY      | KM       | HistGradientBoostingRegressor(default) |         1628 |         18 |     0.0093 | 7480.18   |       4401.31   | 10455.1    | -27.347  |  7027.16   |     0.4944 |         0.1111 |         0.2222 |

## Coverage Trade-offs

| target_family             | split      |   any_service_observed |   periodic_observed |   periodic_censored |   coverage_vs_any |
|:--------------------------|:-----------|-----------------------:|--------------------:|--------------------:|------------------:|
| NEXT_PERIODIC_MAINTENANCE | TRAIN      |                  20679 |               20325 |                 354 |            0.9829 |
| NEXT_PERIODIC_MAINTENANCE | VALIDATION |                   1932 |                1841 |                  91 |            0.9529 |
| NEXT_PERIODIC_MAINTENANCE | TEST       |                   2622 |                2473 |                 149 |            0.9432 |

Yuksek R2 dusuk coverage ile geldiyse otomatik kazanan degildir; leaderboard >=0.80 coverage sartiyla secildi.

## Target Noise

| formulation           | target   |       std |        variance |   skewness |   coef_of_variation |
|:----------------------|:---------|----------:|----------------:|-----------:|--------------------:|
| RAW_ANY               | DAYS     |  147.454  | 21742.7         |     2.3347 |              0.9745 |
| RAW_ANY               | KM       | 4908.41   |     2.40925e+07 |     2.4013 |              0.7478 |
| LOG_ANY               | DAYS     |    0.9233 |     0.8524      |    -0.2739 |              0.1994 |
| LOG_ANY               | KM       |    0.7691 |     0.5915      |    -2.1283 |              0.09   |
| V0_RESIDUAL_ANY       | DAYS     |  144.327  | 20830.3         |     2.3404 |              0.9762 |
| V0_RESIDUAL_ANY       | KM       | 4891.65   |     2.39282e+07 |     2.3986 |              0.7564 |
| POLICY_RATIO_ANY      | DAYS     |   10.5717 |   111.761       |     4.1711 |              1.2261 |
| POLICY_RATIO_ANY      | KM       |   15.8204 |   250.284       |     4.2141 |              1.4104 |
| HISTORY_DEVIATION_ANY | DAYS     |   94.4707 |  8924.71        |     0.9866 |            -15.5248 |
| HISTORY_DEVIATION_ANY | KM       | 4900.85   |     2.40183e+07 |     1.3279 |            -15.9269 |
| RAW_PERIODIC          | DAYS     |  151.28   | 22885.6         |     2.2861 |              0.9667 |
| RAW_PERIODIC          | KM       | 5191.95   |     2.69563e+07 |     2.3673 |              0.7566 |
| LOG_PERIODIC          | DAYS     |    0.9162 |     0.8394      |    -0.2282 |              0.1963 |
| LOG_PERIODIC          | KM       |    0.7184 |     0.5161      |    -0.79   |              0.0836 |
| V0_RESIDUAL_PERIODIC  | DAYS     |  148.027  | 21912.1         |     2.2868 |              0.9674 |
| V0_RESIDUAL_PERIODIC  | KM       | 5174.67   |     2.67772e+07 |     2.366  |              0.7649 |

## Any Service vs Periodic Maintenance

| target   | target_definition         | formulation   |   val_mae |   val_r2 |   coverage |   target_std |   target_cv |   target_skew |
|:---------|:--------------------------|:--------------|----------:|---------:|-----------:|-------------:|------------:|--------------:|
| DAYS     | NEXT_ANY_SERVICE          | RAW_ANY       |   22.4714 |   0.2831 |     1      |      147.454 |      0.9745 |        2.3347 |
| DAYS     | NEXT_PERIODIC_MAINTENANCE | RAW_PERIODIC  |   24.3258 |   0.2447 |     0.9529 |      151.28  |      0.9667 |        2.2861 |
| KM       | NEXT_ANY_SERVICE          | RAW_ANY       | 1482.75   |   0.1521 |     0.9995 |     4908.41  |      0.7478 |        2.4013 |
| KM       | NEXT_PERIODIC_MAINTENANCE | RAW_PERIODIC  | 1569.37   |   0.1377 |     0.9503 |     5191.95  |      0.7566 |        2.3673 |

Next-ANY-service target'inin %6.6'i plansiz (REPAIR/BREAKDOWN/TIRE) olaydir; bunlar interval
dagilimini genisletir. Periodic target bu olaylari hedef event saymaz (yalniz diagnostik; RAW target'tan silinmedi).

## Secondary Strong Model Check

| formulation     | target   | model                                  |   val_mae |   val_r2 |   coverage |
|:----------------|:---------|:---------------------------------------|----------:|---------:|-----------:|
| RAW_ANY         | DAYS     | HistGradientBoostingRegressor(default) |   22.4714 |   0.2831 |          1 |
| RAW_ANY         | DAYS     | LGBMRegressor                          |   21.5181 |   0.2809 |          1 |
| RAW_ANY         | DAYS     | CatBoostRegressor                      |   22.0509 |   0.2504 |          1 |
| RAW_ANY         | DAYS     | XGBRegressor                           |   23.2249 |   0.1619 |          1 |
| RAW_ANY         | DAYS     | ExtraTreesRegressor                    |   32.267  |  -0.2105 |          1 |
| V0_RESIDUAL_ANY | DAYS     | HistGradientBoostingRegressor(default) |   22.0923 |   0.281  |          1 |
| V0_RESIDUAL_ANY | DAYS     | CatBoostRegressor                      |   21.2147 |   0.2587 |          1 |
| V0_RESIDUAL_ANY | DAYS     | LGBMRegressor                          |   21.7706 |   0.2529 |          1 |
| V0_RESIDUAL_ANY | DAYS     | XGBRegressor                           |   23.4206 |   0.1473 |          1 |
| V0_RESIDUAL_ANY | DAYS     | ExtraTreesRegressor                    |   33.8005 |  -0.3634 |          1 |

## Test Results

| formulation     | family   | target   |   coverage |   val_r2 |   test_mae |   test_median_ae |   test_rmse |   test_r2 |   test_bias |   val_to_test_r2_gap |   test_within_15 |   test_within_30 |   test_within_45 |   test_within_60 |   test_within_90 |   test_within_500 |   test_within_1000 |   test_within_1500 |   test_within_2000 |   test_within_5000 |
|:----------------|:---------|:---------|-----------:|---------:|-----------:|-----------------:|------------:|----------:|------------:|---------------------:|-----------------:|-----------------:|-----------------:|-----------------:|-----------------:|------------------:|-------------------:|-------------------:|-------------------:|-------------------:|
| V0_RESIDUAL_ANY | ANY      | DAYS     |     1      |   0.281  |    22.7535 |          17.1266 |     30.5577 |    0.4244 |      0.825  |              -0.1433 |           0.4375 |           0.7654 |           0.8787 |           0.9363 |           0.9844 |          nan      |           nan      |           nan      |           nan      |           nan      |
| RAW_ANY         | ANY      | DAYS     |     1      |   0.2831 |    23.0416 |          17.7582 |     30.747  |    0.4172 |      1.8892 |              -0.1341 |           0.4161 |           0.7639 |           0.8795 |           0.9378 |           0.9817 |          nan      |           nan      |           nan      |           nan      |           nan      |
| RAW_PERIODIC    | PERIODIC | DAYS     |     0.9432 |   0.2447 |    25.293  |          20.5865 |     32.5001 |    0.3577 |      5.3775 |              -0.113  |           0.317  |           0.738  |           0.8722 |           0.9309 |           0.9774 |          nan      |           nan      |           nan      |           nan      |           nan      |
| RAW_ANY         | ANY      | KM       |     1      |   0.1521 |  1520.15   |        1069.47   |   2166.88   |    0.2355 |    -23.8394 |              -0.0834 |         nan      |         nan      |         nan      |         nan      |         nan      |            0.2395 |             0.4718 |             0.6461 |             0.7647 |             0.9641 |
| V0_RESIDUAL_ANY | ANY      | KM       |     1      |   0.1544 |  1537.19   |        1116.8    |   2181.09   |    0.2255 |      4.5206 |              -0.0711 |         nan      |         nan      |         nan      |         nan      |         nan      |            0.2304 |             0.4512 |             0.6438 |             0.7643 |             0.9626 |
| RAW_PERIODIC    | PERIODIC | KM       |     0.9428 |   0.1377 |  1674.39   |        1206.01   |   2360.73   |    0.2072 |     13.2835 |              -0.0695 |         nan      |         nan      |         nan      |         nan      |         nan      |            0.2209 |             0.4163 |             0.5975 |             0.7237 |             0.9535 |

## Leakage Audit

| target_name           | target_family   | future_info_used_to_define_target                                                          | future_info_used_as_feature   | leakage_status   |
|:----------------------|:----------------|:-------------------------------------------------------------------------------------------|:------------------------------|:-----------------|
| RAW_ANY               | ANY             | actual_next_service timing/mileage                                                         | NONE                          | PASS             |
| LOG_ANY               | ANY             | actual_next_service timing/mileage                                                         | NONE                          | PASS             |
| V0_RESIDUAL_ANY       | ANY             | actual_next_service; V0 anchor snapshot-time policy hesabi (gelecek degil)                 | NONE                          | PASS             |
| POLICY_RATIO_ANY      | ANY             | actual_next_service; policy beklenen interval snapshot-time bilgisi                        | NONE                          | PASS             |
| HISTORY_DEVIATION_ANY | ANY             | actual_next_service; gecmis ortalama interval snapshot feature'i                           | NONE                          | PASS             |
| RAW_PERIODIC          | PERIODIC        | first future PERIODIC service timing/mileage (target tanimi icin gelecege bakis normaldir) | NONE                          | PASS             |
| LOG_PERIODIC          | PERIODIC        | first future PERIODIC service timing/mileage                                               | NONE                          | PASS             |
| V0_RESIDUAL_PERIODIC  | PERIODIC        | first future PERIODIC service; V0 anchor snapshot-time policy hesabi                       | NONE                          | PASS             |

Gelecek bilgisi yalniz target tanimlamak icin kullanildi; hicbir formulasyonda feature olarak girmedi.

## Business Interpretation

- **NEXT_ANY_SERVICE**: "Motor herhangi bir nedenle ne zaman gelir?" - operasyonel doluluk / kapasite planlama.
- **NEXT_PERIODIC_MAINTENANCE**: "Planli bakim ne zaman?" - hatirlatma / CRM / parca on-siparis. Issue #579 urun hedefi
  planli bakim hatirlatmasina daha yakinsa periodic target daha dogru problem tanimidir.

## Recommended Target Definition

**NEXT_ANY_SERVICE** (leaderboard formulasyonu V0_RESIDUAL_ANY). Gerekce: is anlami, coverage 0.943,
DAYS TEST R2 0.424, KM TEST R2 0.225, periodic censoring ve yorumlanabilirlik.

## Regression Ceiling Reassessment

**PRACTICAL CEILING REMAINS**. En iyi DAYS TEST R2 0.424, en iyi KM TEST R2 0.225;
RAW_ANY'ye gore en buyuk R2 kazanci +0.007.

## Why R2 Changed (or did not)

DAYS R2 hala <0.60: interval varyansi, musteri gecikmesi ve plansiz olay rastlantisalligi target'ta kaliyor. KM R2 hala <0.45: rota/aktivite kaynakli km varyansi olculemedigi icin sinir kaliyor. Periodic target belirgin kazanc vermedi: RideBase'de servislerin cogu zaten PERIODIC. R2 yuksekse "model daha iyi" demek yerine: target varyansi, coverage dususu, periodic determinism ve
residual kolayligi birlikte degerlendirildi. TEST'e gore target secilmedi; future feature, outlier temizligi veya
censored target uydurmasi yapilmadi.

## V2 Survival Implications

**STILL RECOMMENDED**. Periodic target seciminde bile ~%5.7 periodic censoring var ve observed-only
selection bias suruyor; 41.518 snapshotin observed+censored suresini birlikte kullanan V2 survival hala anlamli.

## Final Verdict

**NO IMPROVEMENT**.
