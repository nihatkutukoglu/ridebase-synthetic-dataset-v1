# V3 Phase 3-4 — Label Taxonomy Discovery and Rare-Label Policy

Machine-readable: [`reports/v3/03_label_inventory.csv`](03_label_inventory.csv),
[`config/v3_label_set.json`](../../config/v3_label_set.json).

## Method

Labels were enumerated from the **actual v1.4 data**, not from a preset list. The
starting universe is the 93 task codes the taxonomy itself marks
`can_be_next_service_target = 1`; 74 of those ever appear as a completed task line.

Every count below is measured on the V3 dataset (`random_one` landmark strategy,
39,451 rows, 7,276 motorcycles) and **over applicable rows only** — a chain task is
not "rare" because most of the fleet is scooters, it is simply inapplicable there.

### Alias normalisation

**None was applied, and none was needed.** Every `task_code` in `service_tasks.csv`
joins exactly to a `maintenance_tasks.csv` row; there are no spelling variants,
no near-duplicate codes and no evidence of any two codes meaning the same thing.
`display_title` carries natural-language variants (`title_variant_type =
NATURAL_VARIANT`) but the underlying code is canonical. No unrelated tasks were
merged to inflate support.

## Frozen rare-label policy (Phase 4)

Decided on **pre-TEST support only** (TRAIN + VALIDATION). TEST positive counts are
reported throughout as a limitation, and were never used to select labels — that
would be threshold selection against TEST.

A label is modelled only if it clears **every** gate:

| Gate | Threshold | Rationale |
|---|---|---|
| `applicable_rows` | ≥ 1,000 | the part must exist on a real slice of the fleet |
| pre-TEST positives | ≥ 200 | enough signal to fit anything |
| VALIDATION positives | ≥ 25 | enough to tune a threshold on at all |
| distinct motorcycles | ≥ 100 | not driven by a handful of bikes |
| years covered | ≥ 4 | present across the panel, not a one-year artifact |

Within the modelled set, **A_CORE** additionally requires ≥1,000 pre-TEST positives
and ≥2% prevalence among applicable rows. CORE vs LOW_FREQUENCY is a *reporting*
distinction — both are modelled, but LOW_FREQUENCY labels carry a low-support
warning in the product contract.

**Actions considered and taken:**

- *retain as independent label* — applied to all 44 labels that clear the gate.
- *merge* — **rejected**. No two labels are semantically equivalent (see alias
  normalisation), so any merge would be metric inflation dressed as taxonomy work.
- *map to OTHER* — **rejected**. An "OTHER task" bucket has no product meaning: a
  workshop cannot act on "something else, 34%".
- *exclude from V3.0 modelling but keep in data audit* — applied to 30 labels,
  each with its failing gate recorded in `config/v3_label_set.json`.

## Result

| Class | Count |
|---|---|
| A_CORE | 25 |
| B_LOW_FREQUENCY | 19 |
| C_TOO_RARE_FOR_MODELING | 30 |
| **Modelled in V3.0** | **44** |

## A_CORE (25 labels)

| task_code | group | applicable rows | positives | prevalence (applicable) | TRAIN+ | VAL+ | TEST+ | motorcycles | years |
|---|---|---|---|---|---|---|---|---|---|
| ENGINE_OIL_CHANGE | ENGINE | 39414 | 34762 | 0.8820 | 25734 | 4402 | 4626 | 6990 | 6 |
| BATTERY_TEST | ELECTRICAL | 39451 | 11933 | 0.3025 | 9891 | 1262 | 780 | 4570 | 6 |
| AIR_FILTER_INSPECTION | INTAKE | 39414 | 11863 | 0.3010 | 9838 | 1251 | 774 | 4581 | 6 |
| BRAKE_FLUID_CHECK | BRAKES | 39451 | 10451 | 0.2649 | 8702 | 1091 | 658 | 4297 | 6 |
| AIR_FILTER_CHANGE | INTAKE | 39414 | 9856 | 0.2501 | 8186 | 1054 | 616 | 4195 | 6 |
| GENERAL_SAFETY_INSPECTION | GENERAL | 39451 | 9533 | 0.2416 | 7874 | 1048 | 611 | 4194 | 6 |
| CHAIN_CLEAN | FINAL_DRIVE | 13693 | 7964 | 0.5816 | 6601 | 853 | 510 | 1938 | 6 |
| CHAIN_LUBRICATE | FINAL_DRIVE | 13693 | 6402 | 0.4675 | 5271 | 698 | 433 | 1819 | 6 |
| CHAIN_INSPECTION | FINAL_DRIVE | 13693 | 4013 | 0.2931 | 3361 | 403 | 249 | 1364 | 6 |
| BRAKE_FLUID_CHANGE | BRAKES | 39451 | 3894 | 0.0987 | 3231 | 408 | 255 | 2643 | 6 |
| FORK_INSPECTION | SUSPENSION | 39451 | 3828 | 0.0970 | 3196 | 413 | 219 | 2266 | 6 |
| CVT_BELT_INSPECTION | TRANSMISSION | 21721 | 3789 | 0.1744 | 3156 | 388 | 245 | 1843 | 6 |
| CVT_CASE_INSPECTION | TRANSMISSION | 21721 | 3721 | 0.1713 | 3048 | 419 | 254 | 1905 | 6 |
| FRONT_BRAKE_PAD_INSPECTION | BRAKES | 39451 | 2835 | 0.0719 | 2360 | 299 | 176 | 1863 | 6 |
| CVT_ROLLER_INSPECTION | TRANSMISSION | 21721 | 2720 | 0.1252 | 2250 | 288 | 182 | 1614 | 6 |
| VALVE_CLEARANCE_INSPECTION | ENGINE | 39414 | 2581 | 0.0655 | 2121 | 277 | 183 | 1800 | 6 |
| WHEEL_BEARING_INSPECTION | TIRES_WHEELS | 39451 | 2232 | 0.0566 | 1838 | 240 | 154 | 1657 | 6 |
| SPARK_PLUG_INSPECTION | IGNITION | 39414 | 2211 | 0.0561 | 1884 | 211 | 116 | 1429 | 6 |
| CVT_BELT_CHANGE | TRANSMISSION | 21721 | 2121 | 0.0976 | 1746 | 239 | 136 | 1349 | 6 |
| FRONT_TIRE_INSPECTION | TIRES_WHEELS | 39451 | 2073 | 0.0525 | 1737 | 213 | 123 | 1469 | 6 |
| COOLANT_LEVEL_CHECK | COOLING | 9786 | 1798 | 0.1837 | 1433 | 220 | 145 | 1010 | 6 |
| FINAL_GEAR_OIL_CHANGE | TRANSMISSION | 21721 | 1689 | 0.0778 | 1409 | 168 | 112 | 1109 | 6 |
| SPARK_PLUG_CHANGE | IGNITION | 39414 | 1653 | 0.0419 | 1398 | 172 | 83 | 1205 | 6 |
| REAR_TIRE_INSPECTION | TIRES_WHEELS | 39451 | 1196 | 0.0303 | 985 | 136 | 75 | 1017 | 6 |
| REAR_BRAKE_PAD_INSPECTION | BRAKES | 39451 | 1083 | 0.0275 | 881 | 133 | 69 | 893 | 6 |

## B_LOW_FREQUENCY (19 labels — modelled, low-support warning)

| task_code | group | applicable rows | positives | prevalence (applicable) | TRAIN+ | VAL+ | TEST+ | motorcycles | years |
|---|---|---|---|---|---|---|---|---|---|
| FRONT_TIRE_CHANGE | TIRES_WHEELS | 39451 | 1284 | 0.0325 | 465 | 352 | 467 | 1030 | 6 |
| STEERING_BEARING_INSPECTION | STEERING | 39451 | 980 | 0.0248 | 797 | 128 | 55 | 858 | 6 |
| FUEL_SYSTEM_DIAGNOSTIC | FUEL | 39414 | 694 | 0.0176 | 364 | 131 | 199 | 637 | 6 |
| COOLANT_CHANGE | COOLING | 9786 | 655 | 0.0669 | 502 | 96 | 57 | 493 | 6 |
| ENGINE_COMPRESSION_TEST | ENGINE | 39414 | 580 | 0.0147 | 278 | 121 | 180 | 565 | 6 |
| ECU_DIAGNOSTIC_SCAN | ELECTRICAL | 39451 | 564 | 0.0143 | 453 | 70 | 41 | 538 | 6 |
| ABS_DIAGNOSTIC | BRAKES | 39451 | 542 | 0.0137 | 253 | 105 | 184 | 514 | 6 |
| WHEEL_BALANCE | TIRES_WHEELS | 39451 | 302 | 0.0077 | 242 | 34 | 26 | 289 | 6 |
| FORK_SEAL_CHANGE | SUSPENSION | 39451 | 284 | 0.0072 | 239 | 29 | 16 | 273 | 6 |
| ENGINE_FAULT_DIAGNOSTIC | ENGINE | 39414 | 278 | 0.0071 | 222 | 28 | 28 | 260 | 5 |
| BATTERY_CHANGE | ELECTRICAL | 39451 | 272 | 0.0069 | 219 | 36 | 17 | 266 | 6 |
| WHEEL_BEARING_CHANGE | TIRES_WHEELS | 39451 | 270 | 0.0068 | 205 | 39 | 26 | 267 | 6 |
| STEERING_BEARING_CHANGE | STEERING | 39451 | 267 | 0.0068 | 214 | 36 | 17 | 258 | 6 |
| BRAKE_DISC_CHANGE | BRAKES | 39451 | 266 | 0.0067 | 205 | 34 | 27 | 261 | 6 |
| VALVE_CLEARANCE_ADJUST | ENGINE | 39414 | 266 | 0.0067 | 217 | 28 | 21 | 258 | 6 |
| BRAKE_SYSTEM_BLEED | BRAKES | 39451 | 264 | 0.0067 | 203 | 32 | 29 | 258 | 6 |
| REAR_TIRE_CHANGE | TIRES_WHEELS | 39451 | 257 | 0.0065 | 204 | 32 | 21 | 249 | 6 |
| THROTTLE_BODY_CLEAN | INTAKE | 39414 | 253 | 0.0064 | 202 | 31 | 20 | 250 | 6 |
| FUEL_INJECTOR_CLEAN | FUEL | 39414 | 253 | 0.0064 | 201 | 31 | 21 | 244 | 6 |

## C_TOO_RARE_FOR_MODELING (30 labels — excluded, retained in audit)

| task_code | pre-TEST + | VAL + | failing gate(s) |
|---|---|---|---|
| CLUTCH_FREE_PLAY_CHECK | 163 | 22 | pos_dev=163 < 200; pos_val=22 < 25 |
| COOLING_SYSTEM_INSPECTION | 71 | 26 | pos_dev=71 < 200 |
| ELECTRICAL_FAULT_DIAGNOSTIC | 223 | 24 | pos_val=24 < 25 |
| BRAKE_FAULT_DIAGNOSTIC | 214 | 24 | pos_val=24 < 25 |
| TRANSMISSION_FAULT_DIAGNOSTIC | 151 | 21 | pos_dev=151 < 200; pos_val=21 < 25 |
| CHARGING_SYSTEM_TEST | 140 | 22 | pos_dev=140 < 200; pos_val=22 < 25 |
| BRAKE_DISC_INSPECTION | 135 | 22 | pos_dev=135 < 200; pos_val=22 < 25 |
| AIR_FILTER_CLEAN | 131 | 23 | pos_dev=131 < 200; pos_val=23 < 25; motorcycles=95 < 100 |
| INTAKE_LEAK_INSPECTION | 134 | 19 | pos_dev=134 < 200; pos_val=19 < 25 |
| OIL_LEAK_INSPECTION | 129 | 20 | pos_dev=129 < 200; pos_val=20 < 25 |
| COOLING_FAULT_DIAGNOSTIC | 131 | 15 | pos_dev=131 < 200; pos_val=15 < 25 |
| INTAKE_FAULT_DIAGNOSTIC | 112 | 14 | pos_dev=112 < 200; pos_val=14 < 25 |
| SUSPENSION_FAULT_INSPECTION | 95 | 14 | pos_dev=95 < 200; pos_val=14 < 25 |
| TIRE_WHEEL_FAULT_INSPECTION | 86 | 13 | pos_dev=86 < 200; pos_val=13 < 25; motorcycles=87 < 100 |
| CVT_BELT_FAILURE_DIAGNOSTIC | 82 | 8 | pos_dev=82 < 200; pos_val=8 < 25; motorcycles=85 < 100 |
| CLUTCH_PLATE_CHANGE | 15 | 3 | pos_dev=15 < 200; pos_val=3 < 25; motorcycles=75 < 100 |
| CLUTCH_ADJUST | 8 | 1 | pos_dev=8 < 200; pos_val=1 < 25; motorcycles=69 < 100 |
| STEERING_FAULT_INSPECTION | 59 | 6 | pos_dev=59 < 200; pos_val=6 < 25; motorcycles=61 < 100 |
| THERMOSTAT_DIAGNOSTIC | 41 | 9 | pos_dev=41 < 200; pos_val=9 < 25; motorcycles=45 < 100 |
| CLUTCH_PLATE_INSPECTION | 7 | 0 | pos_dev=7 < 200; pos_val=0 < 25; motorcycles=44 < 100 |
| CHAIN_DRIVE_DIAGNOSTIC | 39 | 4 | pos_dev=39 < 200; pos_val=4 < 25; motorcycles=39 < 100 |
| OIL_FILTER_CHANGE | 34 | 6 | pos_dev=34 < 200; pos_val=6 < 25; motorcycles=34 < 100 |
| EV_CHARGING_PORT_INSPECTION | 10 | 2 | applicable_rows=37 < 1000; pos_dev=10 < 200; pos_val=2 < 25; motorcycles=12 < 100 |
| FUEL_FILTER_CHANGE | 11 | 2 | pos_dev=11 < 200; pos_val=2 < 25; motorcycles=12 < 100 |
| EV_HIGH_VOLTAGE_SYSTEM_INSPECTION | 9 | 1 | applicable_rows=37 < 1000; pos_dev=9 < 200; pos_val=1 < 25; motorcycles=9 < 100 |
| FUEL_FILTER_INSPECTION | 8 | 1 | pos_dev=8 < 200; pos_val=1 < 25; motorcycles=8 < 100; years_covered=3 < 4 |
| EV_TRACTION_BATTERY_HEALTH_CHECK | 4 | 1 | applicable_rows=37 < 1000; pos_dev=4 < 200; pos_val=1 < 25; motorcycles=6 < 100; years_covered=3 < 4 |
| FINAL_DRIVE_FAULT_INSPECTION | 0 | 0 | pos_dev=0 < 200; pos_val=0 < 25; motorcycles=1 < 100; years_covered=1 < 4 |
| DRIVE_BELT_INSPECTION | 0 | 0 | applicable_rows=21 < 1000; pos_dev=0 < 200; pos_val=0 < 25; motorcycles=0 < 100; years_covered=0 < 4 |
| EV_DRIVE_MOTOR_DIAGNOSTIC | 0 | 0 | applicable_rows=37 < 1000; pos_dev=0 < 200; pos_val=0 < 25; motorcycles=0 < 100; years_covered=0 < 4 |

## D_AMBIGUOUS / NEEDS_REVIEW (4 labels)

These are flagged on **semantics**, not support. All four also fail the support
gate, so the flag changes no modelling decision — but the mismatch is a finding
about the synthetic world and is recorded rather than smoothed over.

- **`OIL_FILTER_CHANGE`** — Canonically an oil-change companion task, and the V3 brief's example output shows it at 0.84. In v1.4 it has 40 positives against 34,762 ENGINE_OIL_CHANGE positives, i.e. the generator does not couple them. Excluded on support; the mismatch is a data-semantics finding, not a modelling choice.

- **`DRIVE_BELT_INSPECTION`** — Eligible in the taxonomy but zero observed positives -- only 21 rows have a BELT (non-V_BELT) final drive. Unobservable, not rare.

- **`EV_DRIVE_MOTOR_DIAGNOSTIC`** — Zero observed positives across 37 applicable rows. EV coverage in v1.4 is too thin to model any EV-specific task.

- **`FINAL_DRIVE_FAULT_INSPECTION`** — A single positive in the entire dataset, in TEST only. Excluded.

## Known limitation: TEST support

The temporal split gives TEST only 2026-01 → 2026-07 (5,906 rows against 28,191
TRAIN). Several modelled B_LOW_FREQUENCY labels have fewer than 30 TEST positives,
so their frozen TEST metrics carry wide uncertainty. This is stated rather than
hidden, and the per-label TEST table reports support alongside every metric.
