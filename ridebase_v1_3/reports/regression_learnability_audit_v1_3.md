# RideBase v1.3 Regression Learnability Audit

Bu rapor sentetik generator calibration deneyidir; production doğrulaması değildir. R² acceptance gate değildir.

## Target dağılımları

| target   | split      |   count |      mean |    median |       std |       p25 |       p75 |        p95 |        p99 |   version |
|:---------|:-----------|--------:|----------:|----------:|----------:|----------:|----------:|-----------:|-----------:|----------:|
| DAYS     | TEST       |    2622 |   67.7746 |   57.9361 |   40.2838 |   36.1729 |   91.9762 |   149.1023 |   180.6127 |    1.2000 |
| DAYS     | TRAIN      |   20679 |  159.5686 |  111.9528 |  151.1817 |   55.9944 |  208.9031 |   450.9208 |   744.9120 |    1.2000 |
| DAYS     | VALIDATION |    1932 |   62.8604 |   54.9337 |   35.8693 |   34.9036 |   86.0962 |   132.7864 |   158.5270 |    1.2000 |
| KM       | TEST       |    2622 | 4530.2483 | 3995.5000 | 2478.7895 | 2886.2500 | 5470.2500 |  9594.8000 | 13360.1700 |    1.2000 |
| KM       | TRAIN      |   20679 | 6762.1851 | 5267.0000 | 5032.3369 | 3417.0000 | 8483.5000 | 16560.6000 | 25613.2200 |    1.2000 |
| KM       | VALIDATION |    1932 | 4431.0963 | 3862.0000 | 2444.0276 | 2857.0000 | 5360.0000 |  9169.0000 | 13015.8400 |    1.2000 |
| DAYS     | TEST       |    1282 |  104.6734 |   88.8730 |   60.4490 |   53.7943 |  153.7796 |   215.4137 |   231.5399 |    1.3000 |
| DAYS     | TRAIN      |   25442 |  127.7559 |   94.8837 |   99.8944 |   52.5390 |  169.7274 |   349.8788 |   431.9829 |    1.3000 |
| DAYS     | VALIDATION |    1429 |   63.6305 |   55.3222 |   32.5879 |   39.0523 |   83.6219 |   129.4019 |   155.5131 |    1.3000 |
| KM       | TEST       |    1282 | 3502.9165 | 3177.5000 | 1728.5192 | 2308.7500 | 4491.7500 |  6656.7000 |  8980.2100 |    1.3000 |
| KM       | TRAIN      |   25442 | 3566.3326 | 3213.0000 | 1776.0083 | 2321.0000 | 4523.0000 |  6841.9500 |  9019.5900 |    1.3000 |
| KM       | VALIDATION |    1429 | 3446.0798 | 3176.0000 | 1378.1792 | 2463.0000 | 4238.0000 |  6138.2000 |  7430.8800 |    1.3000 |

## Signal / noise decomposition

|   version | target   | method                            |   target_variance |   signal_component_variance |   noise_component_variance |   signal_to_noise_ratio |
|----------:|:---------|:----------------------------------|------------------:|----------------------------:|---------------------------:|------------------------:|
|    1.3000 | DAYS     | generator_component_exact         |        10969.4917 |                  10496.5195 |                   571.1688 |                 18.3773 |
|    1.2000 | DAYS     | posthoc_same_model_residual_proxy |         1622.7884 |                    677.0488 |                   945.7396 |                  0.7159 |
|    1.3000 | KM       | generator_component_exact         |      3233442.1053 |                1924217.7162 |               2443208.2434 |                  0.7876 |
|    1.2000 | KM       | posthoc_same_model_residual_proxy |      6144397.5190 |                1447251.4867 |               4697146.0323 |                  0.3081 |

V1.2 decomposition generator iç bileşenleri mevcut olmadığı için same-model residual proxy'dir; v1.3 satırları builder tarafından kaydedilen exact bileşenlerdir.

## Feature-target association

| target   | feature                           |   pearson |   spearman |   mutual_information |     n |
|:---------|:----------------------------------|----------:|-----------:|---------------------:|------:|
| DAYS     | historical_interval_days_median   |    0.6232 |     0.7741 |               0.8411 | 28153 |
| DAYS     | previous_interval_days            |    0.6081 |     0.7673 |               0.8157 | 28153 |
| DAYS     | recent_km_per_day                 |   -0.7139 |    -0.8808 |               0.7635 | 28153 |
| DAYS     | annual_km_baseline                |   -0.7232 |    -0.8543 |               0.7158 | 28153 |
| DAYS     | service_sequence                  |   -0.4696 |    -0.6555 |               0.3142 | 28153 |
| DAYS     | historical_interval_km_median     |   -0.0818 |     0.1045 |               0.2033 | 28153 |
| DAYS     | policy_interval_km                |    0.4348 |     0.4727 |               0.1516 | 28153 |
| DAYS     | previous_interval_km              |   -0.0583 |     0.0800 |               0.1511 | 28153 |
| DAYS     | snapshot_odometer_km              |   -0.3838 |    -0.4718 |               0.1347 | 28153 |
| DAYS     | historical_policy_delay_mean_days |    0.2369 |     0.1962 |               0.0308 | 28153 |
| DAYS     | usage_type                        |    0.0074 |     0.0138 |               0.0171 | 28153 |
| DAYS     | policy_interval_days              |    0.0000 |     0.0000 |               0.0000 | 28153 |
| KM       | historical_interval_km_median     |    0.4082 |     0.5001 |               0.2288 | 28153 |
| KM       | policy_interval_km                |    0.4905 |     0.5033 |               0.2028 | 28153 |
| KM       | previous_interval_km              |    0.3675 |     0.4542 |               0.1849 | 28153 |
| KM       | annual_km_baseline                |    0.1378 |     0.1567 |               0.1205 | 28153 |
| KM       | recent_km_per_day                 |    0.0292 |     0.0763 |               0.1089 | 28153 |
| KM       | previous_interval_days            |    0.0383 |     0.1682 |               0.1013 | 28153 |
| KM       | historical_interval_days_median   |    0.0396 |     0.1551 |               0.0951 | 28153 |
| KM       | service_sequence                  |   -0.1383 |    -0.1150 |               0.0433 | 28153 |
| KM       | snapshot_odometer_km              |    0.0356 |     0.0588 |               0.0255 | 28153 |
| KM       | historical_policy_delay_mean_days |   -0.0642 |    -0.0833 |               0.0069 | 28153 |
| KM       | usage_type                        |    0.0021 |    -0.0090 |               0.0055 | 28153 |
| KM       | policy_interval_days              |    0.0000 |     0.0000 |               0.0000 | 28153 |

## Mileage persistence

Lag-1 autocorrelation v1.2 **0.8249**, v1.3 **0.8994**. Seri tamamen bağımsız değildir; innovation noise sıfır değildir.

## Observed / censored shift

| feature              |   observed_mean |   censored_mean |   standardized_mean_difference |
|:---------------------|----------------:|----------------:|-------------------------------:|
| motorcycle_age_years |          3.8051 |          4.7682 |                        -0.4384 |
| snapshot_odometer_km |      52743.7461 |      44262.2445 |                         0.1953 |
| recent_km_per_day    |         42.0180 |         23.3817 |                         0.6884 |
| service_sequence     |          6.0760 |          4.9180 |                         0.1922 |
| policy_interval_days |        365.2500 |        365.2500 |                       nan      |

## Cutoff drift decomposition

V1.2 validation ve test observed-only ortalamalarının düşük olmasının ana mekanizması 6–8 aylık split label cutoff'larının uzun next-event aralıklarını boundary-crossing yaparak regression eligibility dışında bırakmasıdır. Bu calendar truncation/selection etkisine event-type, history-depth ve kullanım kompozisyonu ikincil katkı verir. V1.3 aynı cutoff sözleşmesini korur; split hedefleri elle eşitlenmemiştir.
