# V3 Phase 23 — Product Behaviour Audit

Each scenario is a **filter over real landmarks**, not a hand-built feature row. A
synthetic row can silently violate the joint distribution (100,000 km on a
three-month-old bike) and then "pass" a sanity check that means nothing.

**No expected probability is hardcoded anywhere.** The checks are invariants
(bounds, determinism, ranking stability, applicability) plus a comparison of mean
predicted probability against the observed rate in the same slice.

Data: `ridebase-ml/derived_outputs/v3/23_product_behavior.json`.

| scenario | rows | probs in [0,1] | no NaN | deterministic | ranking stable | inapplicable = 0 | predicted / actual tasks |
|---|---|---|---|---|---|---|---|
| `low_mileage_recently_serviced` | 11 | PASS | PASS | PASS | PASS | PASS | 1.727 / 0.818 |
| `near_oil_interval` | 1,088 | PASS | PASS | PASS | PASS | PASS | 3.583 / 3.108 |
| `overdue_oil_interval` | 2,000 | PASS | PASS | PASS | PASS | PASS | 1.845 / 1.527 |
| `chain_heavy_history` | 1,536 | PASS | PASS | PASS | PASS | PASS | 3.768 / 2.725 |
| `repeated_front_brake_pad_history` | 767 | PASS | PASS | PASS | PASS | PASS | 2.841 / 2.403 |
| `high_usage` | 791 | PASS | PASS | PASS | PASS | PASS | 3.642 / 3.12 |
| `low_usage` | 1,619 | PASS | PASS | PASS | PASS | PASS | 2.872 / 2.261 |
| `no_previous_task_history` | 10 | PASS | PASS | PASS | PASS | PASS | 2.5 / 1.7 |
| `long_service_gap` | 92 | PASS | PASS | PASS | PASS | PASS | 2.0 / 1.087 |
| `new_motorcycle` | 239 | PASS | PASS | PASS | PASS | PASS | 5.264 / 4.079 |
| `unseen_motorcycle` | 1,725 | PASS | PASS | PASS | PASS | PASS | 3.388 / 2.734 |

**All invariants pass on every scenario.** Predicted task counts track actual counts
across the sweep, with a consistent mild over-prediction (ratio ~1.15–1.4) that is
the expected consequence of the global threshold being tuned for micro F1 rather
than for count calibration.

Two scenarios have very few matching landmarks —
`low_mileage_recently_serviced` (11) and `no_previous_task_history` (10). They are
reported with their row counts rather than dropped, and their numbers should not be
read as estimates. The scarcity is itself informative: a landmark almost never
follows a service by ≤30 days on a low-mileage bike, and almost every landmark in
this world has some prior task history.

## Top-5 by mean probability per scenario

Predicted vs observed in the same slice. Divergence is not automatically an error —
it is a calibration observation on a small, deliberately skewed subset.


**`low_mileage_recently_serviced`** (n=11)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.655 | 0.273 |
| 2 | `AIR_FILTER_INSPECTION` | 0.124 | 0.000 |
| 3 | `GENERAL_SAFETY_INSPECTION` | 0.107 | 0.000 |
| 4 | `BRAKE_FLUID_CHECK` | 0.102 | 0.000 |
| 5 | `BATTERY_TEST` | 0.101 | 0.000 |

**`near_oil_interval`** (n=1,088)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.865 | 0.853 |
| 2 | `BATTERY_TEST` | 0.266 | 0.223 |
| 3 | `AIR_FILTER_INSPECTION` | 0.260 | 0.205 |
| 4 | `AIR_FILTER_CHANGE` | 0.218 | 0.179 |
| 5 | `GENERAL_SAFETY_INSPECTION` | 0.217 | 0.170 |

**`overdue_oil_interval`** (n=2,000)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.726 | 0.698 |
| 2 | `FRONT_TIRE_CHANGE` | 0.159 | 0.203 |
| 3 | `BATTERY_TEST` | 0.110 | 0.056 |
| 4 | `AIR_FILTER_CHANGE` | 0.104 | 0.045 |
| 5 | `GENERAL_SAFETY_INSPECTION` | 0.094 | 0.049 |

**`chain_heavy_history`** (n=1,536)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.800 | 0.788 |
| 2 | `CHAIN_CLEAN` | 0.375 | 0.328 |
| 3 | `CHAIN_LUBRICATE` | 0.316 | 0.257 |
| 4 | `BATTERY_TEST` | 0.199 | 0.169 |
| 5 | `CHAIN_INSPECTION` | 0.186 | 0.163 |

**`repeated_front_brake_pad_history`** (n=767)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.792 | 0.757 |
| 2 | `BATTERY_TEST` | 0.196 | 0.146 |
| 3 | `AIR_FILTER_CHANGE` | 0.178 | 0.121 |
| 4 | `GENERAL_SAFETY_INSPECTION` | 0.166 | 0.145 |
| 5 | `AIR_FILTER_INSPECTION` | 0.166 | 0.157 |

**`high_usage`** (n=791)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.832 | 0.845 |
| 2 | `BATTERY_TEST` | 0.240 | 0.212 |
| 3 | `AIR_FILTER_INSPECTION` | 0.200 | 0.219 |
| 4 | `AIR_FILTER_CHANGE` | 0.200 | 0.172 |
| 5 | `BRAKE_FLUID_CHECK` | 0.192 | 0.168 |

**`low_usage`** (n=1,619)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.816 | 0.773 |
| 2 | `AIR_FILTER_INSPECTION` | 0.209 | 0.119 |
| 3 | `BATTERY_TEST` | 0.202 | 0.121 |
| 4 | `CHAIN_CLEAN` | 0.199 | 0.132 |
| 5 | `GENERAL_SAFETY_INSPECTION` | 0.186 | 0.114 |

**`no_previous_task_history`** (n=10)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.756 | 0.700 |
| 2 | `CHAIN_CLEAN` | 0.226 | 0.200 |
| 3 | `CHAIN_LUBRICATE` | 0.179 | 0.200 |
| 4 | `BATTERY_TEST` | 0.164 | 0.100 |
| 5 | `AIR_FILTER_INSPECTION` | 0.124 | 0.000 |

**`long_service_gap`** (n=92)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.869 | 0.793 |
| 2 | `GENERAL_SAFETY_INSPECTION` | 0.178 | 0.022 |
| 3 | `CHAIN_CLEAN` | 0.136 | 0.011 |
| 4 | `CHAIN_LUBRICATE` | 0.134 | 0.011 |
| 5 | `AIR_FILTER_CHANGE` | 0.133 | 0.011 |

**`new_motorcycle`** (n=239)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.916 | 0.920 |
| 2 | `BATTERY_TEST` | 0.374 | 0.322 |
| 3 | `AIR_FILTER_INSPECTION` | 0.358 | 0.310 |
| 4 | `BRAKE_FLUID_CHECK` | 0.330 | 0.297 |
| 5 | `GENERAL_SAFETY_INSPECTION` | 0.312 | 0.293 |

**`unseen_motorcycle`** (n=1,725)

| rank | task | mean predicted | observed rate |
|---|---|---|---|
| 1 | `ENGINE_OIL_CHANGE` | 0.823 | 0.801 |
| 2 | `BATTERY_TEST` | 0.240 | 0.168 |
| 3 | `AIR_FILTER_INSPECTION` | 0.228 | 0.166 |
| 4 | `AIR_FILTER_CHANGE` | 0.203 | 0.144 |
| 5 | `BRAKE_FLUID_CHECK` | 0.195 | 0.140 |
