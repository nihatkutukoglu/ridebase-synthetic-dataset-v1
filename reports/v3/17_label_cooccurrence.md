# V3 Phase 17 — Label Co-occurrence

Measured on TRAIN + VALIDATION only, restricted to rows where **both** labels are
applicable to the motorcycle. Pairs with fewer than 50 co-occurrences or 500
jointly-applicable rows are not reported.

Data: [`17_label_pairs.csv`](17_label_pairs.csv), [`17_label_triplets.csv`](17_label_triplets.csv).

A target service carries a mean of **4.22** modelled tasks (median 4, IQR 3-6,
max 9). A small number of target services carry **zero** modelled tasks — every
task on them fell into the 30 excluded rare labels — and those rows are retained
as genuine all-negative examples rather than dropped, because "nothing from the
modelled set happens" is a real and predictable outcome.

## Top task pairs by co-occurrence count

| task A | task B | co-occurrences | Jaccard | P(B\|A) | P(B) | lift |
|---|---|---|---|---|---|---|
| `ENGINE_OIL_CHANGE` | `AIR_FILTER_INSPECTION` | 11057 | 0.366 | 0.367 | 0.331 | 1.109 |
| `ENGINE_OIL_CHANGE` | `BATTERY_TEST` | 10984 | 0.362 | 0.364 | 0.333 | 1.095 |
| `ENGINE_OIL_CHANGE` | `BRAKE_FLUID_CHECK` | 9765 | 0.324 | 0.324 | 0.292 | 1.109 |
| `ENGINE_OIL_CHANGE` | `AIR_FILTER_CHANGE` | 9212 | 0.305 | 0.306 | 0.276 | 1.109 |
| `ENGINE_OIL_CHANGE` | `GENERAL_SAFETY_INSPECTION` | 8862 | 0.294 | 0.294 | 0.266 | 1.108 |
| `BATTERY_TEST` | `BRAKE_FLUID_CHECK` | 8186 | 0.641 | 0.734 | 0.292 | 2.514 |
| `BATTERY_TEST` | `AIR_FILTER_INSPECTION` | 7796 | 0.540 | 0.699 | 0.331 | 2.113 |
| `ENGINE_OIL_CHANGE` | `CHAIN_CLEAN` | 7426 | 0.706 | 0.707 | 0.639 | 1.107 |
| `AIR_FILTER_INSPECTION` | `BRAKE_FLUID_CHECK` | 6187 | 0.421 | 0.558 | 0.292 | 1.910 |
| `ENGINE_OIL_CHANGE` | `CHAIN_LUBRICATE` | 5948 | 0.566 | 0.567 | 0.512 | 1.107 |
| `CHAIN_CLEAN` | `CHAIN_LUBRICATE` | 5384 | 0.670 | 0.722 | 0.512 | 1.412 |
| `BATTERY_TEST` | `AIR_FILTER_CHANGE` | 5131 | 0.336 | 0.460 | 0.276 | 1.669 |
| `AIR_FILTER_INSPECTION` | `AIR_FILTER_CHANGE` | 4922 | 0.320 | 0.444 | 0.276 | 1.610 |
| `ENGINE_OIL_CHANGE` | `CHAIN_INSPECTION` | 3747 | 0.356 | 0.357 | 0.323 | 1.106 |
| `BRAKE_FLUID_CHECK` | `AIR_FILTER_CHANGE` | 3698 | 0.241 | 0.378 | 0.276 | 1.370 |

## Top task pairs by lift (>=200 co-occurrences)

| task A | task B | co-occurrences | P(B\|A) | P(B) | lift |
|---|---|---|---|---|---|
| `WHEEL_BALANCE` | `REAR_TIRE_CHANGE` | 233 | 0.844 | 0.007 | 119.995 |
| `REAR_TIRE_INSPECTION` | `REAR_TIRE_CHANGE` | 231 | 0.206 | 0.007 | 29.290 |
| `REAR_TIRE_INSPECTION` | `WHEEL_BALANCE` | 230 | 0.205 | 0.008 | 24.937 |
| `VALVE_CLEARANCE_INSPECTION` | `WHEEL_BEARING_INSPECTION` | 903 | 0.377 | 0.062 | 6.074 |
| `VALVE_CLEARANCE_INSPECTION` | `FINAL_GEAR_OIL_CHANGE` | 637 | 0.515 | 0.086 | 5.996 |
| `FRONT_BRAKE_PAD_INSPECTION` | `FRONT_TIRE_INSPECTION` | 876 | 0.329 | 0.058 | 5.667 |
| `FORK_INSPECTION` | `FRONT_BRAKE_PAD_INSPECTION` | 1433 | 0.397 | 0.079 | 5.009 |
| `CVT_BELT_CHANGE` | `SPARK_PLUG_CHANGE` | 326 | 0.164 | 0.036 | 4.521 |
| `CVT_ROLLER_INSPECTION` | `FINAL_GEAR_OIL_CHANGE` | 946 | 0.373 | 0.086 | 4.340 |
| `FORK_INSPECTION` | `FRONT_TIRE_INSPECTION` | 838 | 0.232 | 0.058 | 3.994 |
| `WHEEL_BEARING_INSPECTION` | `FINAL_GEAR_OIL_CHANGE` | 341 | 0.321 | 0.086 | 3.735 |
| `FINAL_GEAR_OIL_CHANGE` | `SPARK_PLUG_CHANGE` | 207 | 0.131 | 0.036 | 3.614 |

## Top task triplets

| task A | task B | task C | count | rate |
|---|---|---|---|---|
| `ENGINE_OIL_CHANGE` | `BATTERY_TEST` | `BRAKE_FLUID_CHECK` | 8162 | 0.243 |
| `ENGINE_OIL_CHANGE` | `BATTERY_TEST` | `AIR_FILTER_INSPECTION` | 7773 | 0.232 |
| `ENGINE_OIL_CHANGE` | `AIR_FILTER_INSPECTION` | `BRAKE_FLUID_CHECK` | 6169 | 0.184 |
| `BATTERY_TEST` | `AIR_FILTER_INSPECTION` | `BRAKE_FLUID_CHECK` | 5507 | 0.164 |
| `ENGINE_OIL_CHANGE` | `CHAIN_CLEAN` | `CHAIN_LUBRICATE` | 5366 | 0.460 |
| `ENGINE_OIL_CHANGE` | `BATTERY_TEST` | `AIR_FILTER_CHANGE` | 5113 | 0.152 |
| `ENGINE_OIL_CHANGE` | `AIR_FILTER_INSPECTION` | `AIR_FILTER_CHANGE` | 4906 | 0.146 |
| `BATTERY_TEST` | `AIR_FILTER_INSPECTION` | `AIR_FILTER_CHANGE` | 3896 | 0.116 |
| `ENGINE_OIL_CHANGE` | `BRAKE_FLUID_CHECK` | `AIR_FILTER_CHANGE` | 3688 | 0.110 |
| `ENGINE_OIL_CHANGE` | `CHAIN_CLEAN` | `CHAIN_INSPECTION` | 3383 | 0.290 |

## Reading these numbers

**Two structurally different kinds of dependence appear.**

*Bundle co-occurrence.* `ENGINE_OIL_CHANGE` pairs with everything at lift ~1.11,
barely above independence. It is on 88% of services, so it co-occurs with every
other task by sheer frequency, not by mechanism. `BATTERY_TEST` with
`BRAKE_FLUID_CHECK` at lift 2.51 and Jaccard 0.64 is the real inspection-bundle
signature: these tasks share the same 6,000 km / 12-month cadence and are attached
to the same work order by the same bundle draw.

*Mechanical coupling.* The high-lift tail is much sharper and much rarer.
`WHEEL_BALANCE` with `REAR_TIRE_CHANGE` has **lift 120** and a conditional
probability of **0.844** — you do not fit a rear tyre without balancing the wheel.
`REAR_TIRE_INSPECTION` with `REAR_TIRE_CHANGE` (lift 29) and with `WHEEL_BALANCE`
(lift 25) close the same triangle.

## Do classifier chains help?

The bundle-type dependence — which dominates by volume — is **already fully
explained by shared inputs**. Two tasks on the same 6,000 km cadence have nearly
identical `policy_due_ratio__*`, `km_since__*` and `days_since__*` features, and
every binary-relevance classifier sees all of them. Conditioning label B's
classifier on label A's prediction adds no information a shared feature did not
already carry.

The mechanical-coupling dependence is genuinely extra information, but it lives
almost entirely in three labels whose prevalence is 0.6-0.8%. Even a perfect chain
link there moves macro-F1 by a fraction of a point, while chains introduce
order-dependence, error propagation from a noisy parent, and a serial fit that
cannot be parallelised across labels.

Classifier Chains were nevertheless **built and measured** rather than argued away
— see `ridebase-ml/derived_outputs/v3/17_classifier_chain.json` and the tournament
table. The champion decision follows the frozen selection rule, not this prediction.
