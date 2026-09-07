# V3 Phase 7 — Train / Validation / Test Split Audit

## Design

The split is **temporal** and inherited from the frozen V2.1 split
(`primary_split` on the V2.1 modeling table), so V3 and the production champion
are evaluated on the same eras and results stay comparable.

| split | landmark from | landmark to | rows | target service from | target service to |
|---|---|---|---|---|---|
| TRAIN | 2021-02-28 | 2025-05-31 | 28,191 | 2021-03-24 | 2025-06-30 |
| VALIDATION | 2025-07-31 | 2025-11-30 | 5,354 | 2025-08-01 | 2025-12-31 |
| TEST | 2026-01-31 | 2026-07-31 | 5,906 | 2026-02-01 | 2026-08-01 |

Landmark windows do not overlap: TRAIN ends 2025-05-31,
VALIDATION starts 2025-07-31, TEST starts 2026-01-31.

TEST is frozen and was first touched only after the champion, its thresholds and
its calibrators were written to disk (Phase 21 -> 22).

## Target bleed and the purge

V2.1's target is a *duration*, so a TRAIN landmark whose service happens during the
validation era is harmless there. V3's target is the **content of a specific future
service**, so the same landmark would train the model on task outcomes from the
validation era. That is genuine temporal leakage relative to a "train as at date D"
deployment story, and it is removed rather than reported away.

Bleed measured on the un-purged pool:

| split | bleeding landmarks | total | share |
|---|---|---|---|
| TRAIN | 29,873 | 156,462 | 19.1% |
| VALIDATION | 20,986 | 34,413 | 61.0% |
| TEST | 0 | 17,871 | 0.0% |

The VALIDATION rate is high because that window is only six months wide while the
lead-time distribution has a long tail. Purging is applied to the landmark **pool
before** the one-per-target sampler runs, so a target service that still has a
non-bleeding landmark keeps one instead of being lost to sampling luck. That
recovers VALIDATION from 3,325 to 5,354 rows and TEST from 3,577 to 5,906.

**A useful side effect:** after purging, no target service can be reached from two
different splits, so cross-split target sharing is structurally impossible. This is
asserted in `test_no_target_service_bleeds_across_a_split_boundary`.

## Motorcycle overlap

| relation | motorcycles |
|---|---|
| in TRAIN | 5,609 |
| in VALIDATION | 4,123 |
| in TEST | 4,646 |
| TEST ∩ TRAIN | 3,369 |
| **TEST \\ TRAIN (unseen)** | **1,277** |

Motorcycle overlap between TRAIN and TEST is expected and correct — the product
predicts for bikes it has seen before. The unseen subset is evaluated separately
(Phase 18) using the V2.1 `is_unseen_motorcycle_holdout` flag, which gives
**871** unseen-motorcycle TEST rows.

## Label prevalence and support by split

| label | TRAIN prev | VAL prev | TEST prev | TRAIN + | VAL + | TEST + |
|---|---|---|---|---|---|---|
| `ENGINE_OIL_CHANGE` | 0.9136 | 0.8230 | 0.7846 | 25734 | 4402 | 4626 |
| `BATTERY_TEST` | 0.3509 | 0.2357 | 0.1321 | 9891 | 1262 | 780 |
| `AIR_FILTER_INSPECTION` | 0.3492 | 0.2339 | 0.1313 | 9838 | 1251 | 774 |
| `BRAKE_FLUID_CHECK` | 0.3087 | 0.2038 | 0.1114 | 8702 | 1091 | 658 |
| `AIR_FILTER_CHANGE` | 0.2906 | 0.1970 | 0.1045 | 8186 | 1054 | 616 |
| `GENERAL_SAFETY_INSPECTION` | 0.2793 | 0.1957 | 0.1035 | 7874 | 1048 | 611 |
| `CHAIN_CLEAN` | 0.6729 | 0.4591 | 0.2519 | 6601 | 853 | 510 |
| `FRONT_TIRE_CHANGE` | 0.0165 | 0.0657 | 0.0791 | 465 | 352 | 467 |
| `CHAIN_LUBRICATE` | 0.5373 | 0.3757 | 0.2138 | 5271 | 698 | 433 |
| `BRAKE_FLUID_CHANGE` | 0.1146 | 0.0762 | 0.0432 | 3231 | 408 | 255 |
| `CVT_CASE_INSPECTION` | 0.1981 | 0.1406 | 0.0756 | 3048 | 419 | 254 |
| `CHAIN_INSPECTION` | 0.3426 | 0.2169 | 0.1230 | 3361 | 403 | 249 |
| `CVT_BELT_INSPECTION` | 0.2052 | 0.1302 | 0.0730 | 3156 | 388 | 245 |
| `FORK_INSPECTION` | 0.1134 | 0.0771 | 0.0371 | 3196 | 413 | 219 |
| `FUEL_SYSTEM_DIAGNOSTIC` | 0.0129 | 0.0245 | 0.0338 | 364 | 131 | 199 |
| `ABS_DIAGNOSTIC` | 0.0090 | 0.0196 | 0.0312 | 253 | 105 | 184 |
| `VALVE_CLEARANCE_INSPECTION` | 0.0753 | 0.0518 | 0.0310 | 2121 | 277 | 183 |
| `CVT_ROLLER_INSPECTION` | 0.1463 | 0.0966 | 0.0542 | 2250 | 288 | 182 |
| `ENGINE_COMPRESSION_TEST` | 0.0099 | 0.0226 | 0.0305 | 278 | 121 | 180 |
| `FRONT_BRAKE_PAD_INSPECTION` | 0.0837 | 0.0558 | 0.0298 | 2360 | 299 | 176 |
| `WHEEL_BEARING_INSPECTION` | 0.0652 | 0.0448 | 0.0261 | 1838 | 240 | 154 |
| `COOLANT_LEVEL_CHECK` | 0.2197 | 0.1448 | 0.0831 | 1433 | 220 | 145 |
| `CVT_BELT_CHANGE` | 0.1135 | 0.0802 | 0.0405 | 1746 | 239 | 136 |
| `FRONT_TIRE_INSPECTION` | 0.0616 | 0.0398 | 0.0208 | 1737 | 213 | 123 |
| `SPARK_PLUG_INSPECTION` | 0.0669 | 0.0394 | 0.0197 | 1884 | 211 | 116 |
| `FINAL_GEAR_OIL_CHANGE` | 0.0916 | 0.0564 | 0.0334 | 1409 | 168 | 112 |
| `SPARK_PLUG_CHANGE` | 0.0496 | 0.0322 | 0.0141 | 1398 | 172 | 83 |
| `REAR_TIRE_INSPECTION` | 0.0349 | 0.0254 | 0.0127 | 985 | 136 | 75 |
| `REAR_BRAKE_PAD_INSPECTION` | 0.0313 | 0.0248 | 0.0117 | 881 | 133 | 69 |
| `COOLANT_CHANGE` | 0.0770 | 0.0632 | 0.0327 | 502 | 96 | 57 |
| `STEERING_BEARING_INSPECTION` | 0.0283 | 0.0239 | 0.0093 | 797 | 128 | 55 |
| `ECU_DIAGNOSTIC_SCAN` | 0.0161 | 0.0131 | 0.0069 | 453 | 70 | 41 |
| `BRAKE_SYSTEM_BLEED` | 0.0072 | 0.0060 | 0.0049 | 203 | 32 | 29 |
| `ENGINE_FAULT_DIAGNOSTIC` | 0.0079 | 0.0052 | 0.0047 | 222 | 28 | 28 |
| `BRAKE_DISC_CHANGE` | 0.0073 | 0.0064 | 0.0046 | 205 | 34 | 27 |
| `WHEEL_BALANCE` | 0.0086 | 0.0064 | 0.0044 | 242 | 34 | 26 |
| `WHEEL_BEARING_CHANGE` | 0.0073 | 0.0073 | 0.0044 | 205 | 39 | 26 |
| `VALVE_CLEARANCE_ADJUST` | 0.0077 | 0.0052 | 0.0036 | 217 | 28 | 21 |
| `REAR_TIRE_CHANGE` | 0.0072 | 0.0060 | 0.0036 | 204 | 32 | 21 |
| `FUEL_INJECTOR_CLEAN` | 0.0071 | 0.0058 | 0.0036 | 201 | 31 | 21 |
| `THROTTLE_BODY_CLEAN` | 0.0072 | 0.0058 | 0.0034 | 202 | 31 | 20 |
| `STEERING_BEARING_CHANGE` | 0.0076 | 0.0067 | 0.0029 | 214 | 36 | 17 |
| `BATTERY_CHANGE` | 0.0078 | 0.0067 | 0.0029 | 219 | 36 | 17 |
| `FORK_SEAL_CHANGE` | 0.0085 | 0.0054 | 0.0027 | 239 | 29 | 16 |

## Stated limitation: thin TEST support

TEST covers only 2026-01 → 2026-07. **12 of 44 modelled labels have
fewer than 30 TEST positives**, so their frozen TEST metrics carry wide
uncertainty and must not be read as precise estimates:

`WHEEL_BALANCE` (26), `FORK_SEAL_CHANGE` (16), `ENGINE_FAULT_DIAGNOSTIC` (28), `BATTERY_CHANGE` (17), `WHEEL_BEARING_CHANGE` (26), `STEERING_BEARING_CHANGE` (17), `BRAKE_DISC_CHANGE` (27), `VALVE_CLEARANCE_ADJUST` (21), `BRAKE_SYSTEM_BLEED` (29), `REAR_TIRE_CHANGE` (21), `THROTTLE_BODY_CLEAN` (20), `FUEL_INJECTOR_CLEAN` (21)

This is reported rather than hidden, and support is printed alongside every metric
in the per-label TEST table. The labels were nonetheless retained: they cleared the
frozen pre-TEST support gate, and dropping them after seeing TEST support would be
selection against TEST.

Two prevalence shifts are worth flagging, both consequences of the generator's v1.4
tail extension rather than of the split:

- `FRONT_TIRE_CHANGE` rises sharply into VALIDATION/TEST (TRAIN 0.0165 → TEST 0.0791).
- The fault-driven diagnostics (`FUEL_SYSTEM_DIAGNOSTIC`, `ENGINE_COMPRESSION_TEST`,
  `ABS_DIAGNOSTIC`) also rise into the later window.

Both mean TEST is a genuinely harder, distribution-shifted evaluation than
VALIDATION, which is the right direction for a temporal holdout to err in.
