# RideBase v1.1 → v1.2 Reliability Comparison

| Metrik | v1.1 | v1.2 |
|---|---:|---:|
| Overall failure rate | 5.18% | 5.30% |
| Adjusted max/min ratio (büyük markalar) | 1.83x | 1.342x |
| Honda adjusted | 5.75% | 5.38% |
| RKS adjusted | 5.57% | 5.62% |
| Mondial adjusted | 3.93% | 5.27% |
| Kuba adjusted | 4.04% | 4.93% |
| Honda same-km higher | 15/15 | 9/15 |
| FINAL_DRIVE fault count | 0 | 168 |
| Failure service delay non-NULL | 2,152 | 0 |
| Failure fault-task coverage | eksik | 2200/2200 |

## Riding intensity

| riding_intensity   |   service_count |   failure_count | failure_rate   |
|:-------------------|----------------:|----------------:|:---------------|
| HIGH               |           22813 |            1430 | 6.27%          |
| LOW                |            5734 |             207 | 3.61%          |
| MEDIUM             |           12971 |             563 | 4.34%          |

## Load severity

| load_band   |   service_count |   failure_count | failure_rate   |
|:------------|----------------:|----------------:|:---------------|
| <0.95       |            8998 |             360 | 4.00%          |
| 0.95–1.05   |           18631 |             866 | 4.65%          |
| 1.05–1.15   |           10697 |             702 | 6.56%          |
| 1.15+       |            3192 |             272 | 8.52%          |

## Warranty age trend

| warranty_age_bucket   |   service_count |   warranty_count | warranty_rate   |
|:----------------------|----------------:|-----------------:|:----------------|
| 0–2                   |            8452 |              159 | 1.88%           |
| 3–5                   |           20230 |               40 | 0.20%           |
| 6–8                   |           10743 |                0 | 0.00%           |
| 9+                    |            2093 |                0 | 0.00%           |

## Overdue maintenance trend

| overdue_bucket   |   service_count |   failure_count | failure_rate   |
|:-----------------|----------------:|----------------:|:---------------|
| 0                |           16255 |             730 | 4.49%          |
| 1–7              |           10601 |             637 | 6.01%          |
| 8–30             |           13965 |             791 | 5.66%          |
| 31–60            |             697 |              42 | 6.03%          |
| 60+              |               0 |               0 | NULL           |

## Raw brand rates side-by-side

| brand         | raw_failure_service_rate   | raw_failure_rate   | adjusted_failure_rate   |
|:--------------|:---------------------------|:-------------------|:------------------------|
| Bajaj         | 6.61%                      | 3.55%              | 4.70%                   |
| CFMOTO        | 11.64%                     | 3.98%              | 5.33%                   |
| Honda         | 6.20%                      | 5.43%              | 5.38%                   |
| KTM           | 5.69%                      | 8.13%              | 7.69%                   |
| KYMCO         | 8.98%                      | 5.09%              | 6.25%                   |
| Kuba          | 3.20%                      | 5.25%              | 4.93%                   |
| Mondial       | 3.34%                      | 5.60%              | 5.27%                   |
| RKS           | 4.67%                      | 5.72%              | 5.62%                   |
| Royal Enfield | 4.69%                      | 3.12%              | 5.26%                   |
| SYM           | 8.10%                      | 4.49%              | 4.66%                   |
| TVS           | 7.53%                      | 4.37%              | 5.02%                   |
| Yamaha        | 5.76%                      | 5.76%              | 5.35%                   |
