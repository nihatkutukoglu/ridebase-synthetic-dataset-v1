# RideBase Manufacturer Maintenance Knowledge Base

## Purpose

Structured, source-referenced dataset of **manufacturer-recommended** maintenance for the
motorcycle models that appear in the authoritative RideBase model inventory
(`ridebase_v1_3/source_tables/ridebase_motorcycle_models_v1.csv`, 39 models). It answers,
per model / variant / km / month:

- when is a service due?
- which component is inspected / cleaned / replaced at which km / month?
- which tasks repeat, and how often?

It is intended as a **leakage-safe knowledge layer** for later feature engineering for the
V1 next-service KM/DAYS models and the V3 next-task model. It is **not** derived from RideBase
targets or service history.

## Research Method

1. Read the RideBase model inventory. Research scope = only these 39 models. No model outside
   the inventory was researched or added.
2. For each model, searched in source-priority order: official owner's manual → official
   service/workshop manual → official maintenance schedule → manufacturer / distributor web →
   authorised service documents → (last resort) secondary technical. Forums / blogs / parts
   shops are **not** primary sources and are not emitted as task rows.
3. Where an official maintenance chart PDF was found, it was downloaded (`curl`) and parsed
   (`pypdf` / `pdfminer.six`) with page references, and the chart legend decoded
   (`I/C/R/A/L/T`, `K/A/B/T/D`, etc.).
4. Wide "km × task" charts were converted to **long format** (one row per model × task ×
   action × interval).
5. **No interval was ever guessed.** Where a chart cell could not be read it is `UNKNOWN`
   (task field), or the model is `UNRESOLVED` / `PARTIAL` (`research_gaps.csv` /
   `model_coverage.csv`). Nothing was copied from a same-engine or same-displacement model.

## Files

| file | contents |
|---|---|
| `ridebase_model_inventory.csv` | the 39 RideBase models (from the local master table) |
| `sources.csv` | every source document used, with URL, page numbers, official flag, confidence |
| `manufacturer_maintenance_policies.csv` | per-model service-interval / first-service policy |
| `manufacturer_maintenance_tasks.csv` | **task-level** long-format maintenance rows |
| `model_mapping.csv` | RideBase model ↔ source-document model match + match_type/confidence |
| `source_conflicts.csv` | two sources disagree — logged, never averaged |
| `research_gaps.csv` | every model/task not fully resolved, with recommended next action |
| `model_coverage.csv` / `task_coverage.csv` | coverage roll-ups |
| `quality_report.csv` | data-quality checks |
| `manufacturer_maintenance_research_report.md` | full narrative report |

## Model Coverage

| | count |
|---|---|
| RideBase models in inventory | **39** |
| **RESOLVED** — official schedule extracted to task level | **19** |
| **PARTIAL** — official manual found, only some intervals machine-readable | **4** |
| **UNRESOLVED** — no usable official schedule located | **16** |
| Models with an official source of any kind | **23 (59 %)** |
| Task-level rows | **432** (HIGH 336 · MEDIUM 86 · LOW 10) |
| Sources / policies | 24 / 23 |

### By brand

| brand | models | resolved | partial | unresolved |
|---|---|---|---|---|
| Yamaha | 3 | 3 | 0 | 0 |
| Bajaj | 3 | 3 | 0 | 0 |
| TVS | 3 | 3 | 0 | 0 |
| Mondial | 5 | 5 | 0 | 0 |
| KTM | 1 | 1 | 0 | 0 |
| Royal Enfield | 1 | 1 | 0 | 0 |
| SYM | 1 | 1 | 0 | 0 |
| CFMOTO | 7 | 2 | 0 | 5 |
| KYMCO | 2 | 1 | 0 | 1 |
| Honda | 10 | 0 | 3 | 7 |
| Kuba | 2 | 0 | 0 | 2 |
| RKS | 1 | 0 | 0 | 1 |

## Known Gaps

- **Honda (7 unresolved + 3 partial).** Honda's owner-manual maintenance-schedule tables encode
  the per-km Inspect/Clean/Lubricate/Replace marks as **embedded graphics** that do not survive
  PDF text extraction, and Honda's CDNs bot-block automated download. For PCX125 / CB125F /
  SH125i only the running-in km, the service interval (where a `SERVICE DUE` / `OIL CHANGE`
  indicator states it in text — SH125i: 1,000 km then every 6,000 km) and the time-based rows
  (coolant 3 yr, final-drive oil 2 yr, brake fluid 2 yr) could be read.
- **CFMOTO 250SR / 250CL-X / 250 DUAL** share the CF250-A single-cylinder engine documented in
  the **250NK** rows, but the no-copy rule forbids propagating that schedule to them; their own
  manuals were only on paywalled / Cloudflare-blocked hosts.
- **CFMOTO 450NK / 450 CL-C** — official manuals exist (cfmotousa.com) but are Cloudflare-gated.
- **KYMCO Downtown 250i** — the parsed KYMCO manual covers *X-Town CT*, not Downtown.
- **Kuba CG50 Pro / Blueberry 50, RKS New Light Pro** — no model-specific official manual exists
  (RKS ships without one). These are generic imported 50–125 cc scooters/cubs.

## Canonical Task Taxonomy

`ENGINE_OIL, ENGINE_OIL_FILTER, AIR_FILTER, SPARK_PLUG, COOLANT, BRAKE_FLUID, FRONT_BRAKE,
REAR_BRAKE, BRAKE_PADS, BRAKE_SHOES, DRIVE_CHAIN, FINAL_DRIVE, CLUTCH, THROTTLE,
VALVE_CLEARANCE, FUEL_FILTER, FUEL_SYSTEM, BATTERY, TYRES, WHEEL_BEARINGS, STEERING,
SUSPENSION, FASTENERS, LIGHTS, ELECTRICAL, GENERAL_INSPECTION`

`action` controlled vocabulary: `INSPECT, CHECK, CLEAN, REPLACE, ADJUST, LUBRICATE, TIGHTEN,
SERVICE, DRAIN_REPLACE, TOP_UP, OTHER`. `CLEAN` and `REPLACE` are never interconverted.

## Confidence Rules

- **HIGH** — official document, model/variant clearly matched, interval stated explicitly or
  unambiguously readable from the chart.
- **MEDIUM** — official document, but chart cell-to-column mapping was partly reconstructed, or
  the interval is inferred from checkmark spacing, or year/market ambiguity exists.
- **LOW** — interval could not be read cleanly / secondary corroboration only.
- `inferred_pattern = true` marks a repeat interval derived from the spacing of chart columns
  rather than an explicit "every N km" statement.

## Market / Year Handling

- Each source and task row carries a `market` (`TR / EU / IN / GLOBAL / UNKNOWN`).
- India BS VI manuals (Bajaj, TVS) are flagged `market_match = PARTIAL` against the TR listings.
- Yamaha NMAX 125 = the 2015-2021 **GPD125-A** generation (`status = PARTIAL`, year mismatch vs
  the RideBase "2026 EU spec" row); all other Yamaha schedules are the current generation.
- Generations were **not** merged blindly.

## Leakage Safety

- Built **without** reading `days_to_next_service` / `km_to_next_service` or any RideBase
  service-history row.
- Manufacturer **due km** ≠ **actual service km**. Customers arrive early/late; that gap is
  exactly what the ML model must learn. Never treat a `repeat_every_km` value as a target.
- Every task row is tied to a real `source_id`; rows without a source are not emitted.

## ML Usage

Derived features this base can support (all **due / recommended**, not actual):
`km_to_next_manufacturer_service`, `months_to_next_manufacturer_service`, `km_to_next_oil_change`,
`km_to_next_air_filter_service`, `km_to_next_spark_plug_service`, `km_to_next_valve_check`,
`tasks_due_next_{1000,2000,5000}km`, `manufacturer_service_stage`, `manufacturer_overdue_km`,
`is_oil_change_due_flag`, `is_valve_check_due_flag`, `is_belt_or_chain_due_flag`.
