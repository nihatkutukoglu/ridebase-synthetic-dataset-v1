# RideBase Manufacturer Maintenance — Deep Research Report

_Access date: 2026-08-28. Datasets and generators (`ridebase_v1_2/`, `ridebase_v1_3/`,
`build_ridebase_v1_3.py`, the zip) were not modified. This work builds the
`ridebase-ml/external_knowledge/` layer only._

## 1. Executive summary

Every one of the **39** RideBase inventory models was researched against official
manufacturer sources. Result:

- **19 RESOLVED** — official owner's/maintenance manual located and its periodic-maintenance
  chart extracted to task level.
- **4 PARTIAL** — official manual located, but only part of the schedule is machine-readable
  (Honda PCX125 / CB125F / SH125i — graphic checkmarks; Yamaha NMAX 125 — older generation).
- **16 UNRESOLVED** — no usable official schedule could be located/parsed (per-model reasons
  and next actions in `research_gaps.csv`).

**432 task-level rows** (HIGH 336 · MEDIUM 86 · LOW 10) across **24 sources** and **23
per-model service policies**. Nothing was fabricated; nothing was copied from a same-engine
or same-displacement model.

**Official model coverage: 23 / 39 (59 %). Task-level RESOLVED coverage: 19 / 39 (49 %).**

## 2. Method

RideBase inventory → per model, search official owner's manual → service manual → maintenance
schedule → distributor site → (last resort) secondary technical. Where a chart PDF was found:
`curl` download, `pypdf` / `pdfminer.six` extraction with page references, legend decoded,
wide chart → long format. Unreadable cells → `UNKNOWN` + gap; unreachable model → `UNRESOLVED`.

## 3. Sources used (official owner's manuals unless noted)

| brand | models covered | document | market |
|---|---|---|---|
| Bajaj | Pulsar NS200, Pulsar NS125, Dominar 250 | Owner's Manual BS VI (cdn.bajajauto.com) | IN |
| Royal Enfield | Hunter 350 | Owner's Manual BS VI | GLOBAL |
| Yamaha | XSR125, NMAX 125 (GPD125-A), XMAX 250 | Owner's Manual (cdn2.yamaha-motor.eu / mirror) | EU |
| KTM | 390 Duke (398 cc) | Owner's Manual art.no 3214960en (MY2024) | GLOBAL |
| CFMOTO | 250NK; 650NK (CF650-7F) | Owner's Manual (mirror; CFMOTO EU Storyblok CDN) | GLOBAL / EU |
| TVS | Raider 125, Apache RTR 200 4V, Jupiter 125 | User Manual BS VI (tvsmotor.com) | IN |
| SYM | Jet X 125 | Owner's Manual 24-JETX (sym-global.com) | GLOBAL |
| Mondial | 50 UAG, SFC MINI 50ec, Wing 50i, Exon 50, Turismo 50i | Kullanım ve Bakım El Kitabı EURO 5 (mondialmotor.com.tr) | TR |
| KYMCO | X-Town CT 250 | X-TOWN CT125/CT250/CT300 Owner's Manual (kymco.com.cy) | EU |
| Honda | PCX125, CB125F, SH125i (partial) | Owner's Manual (honda.co.uk / hondamotopub.com) | EU |

## 4. Per-model outcome

| model_id | status | rows | note |
|---|---|---|---|
| BAJAJ_NS200 | RESOLVED | 17 | spark-plug replace / valve km not in PDF cells |
| BAJAJ_NS125 | RESOLVED | 18 | intervals from schedule "Remarks" column |
| BAJAJ_DOMINAR250 | RESOLVED | 23 | clean "Remarks" extraction |
| ROYALENFIELD_HUNTER350 | RESOLVED | 25 | fuel-filter column partly reconstructed |
| YAMAHA_XSR125 | RESOLVED | 26 | few km columns inferred from mark counts |
| YAMAHA_XMAX250 | RESOLVED | 26 | ES-language edition; marks intact |
| YAMAHA_NMAX125 | PARTIAL | 22 | 2015-2021 GPD125-A generation (year mismatch) |
| KTM_390_DUKE | RESOLVED | 21 | global schedule; TR intervals may differ |
| CFMOTO_250NK | RESOLVED | 24 | some alternating-column intervals inferred |
| CFMOTO_650NK | RESOLVED | 24 | explicit km + months + action per row |
| TVS_RAIDER125 | RESOLVED | 21 | clean table + explicit remarks |
| TVS_APACHE_RTR200_4V | RESOLVED | 22 | clean table + explicit remarks |
| TVS_JUPITER125 | RESOLVED | 18 | air-cooled CVT; clean table |
| SYM_JETX125 | RESOLVED | 16 | grid scrambled; "Remarks" replace intervals HIGH |
| MONDIAL_50_UAG | RESOLVED | 19 | shared Mondial cub table |
| MONDIAL_SFC_MINI_50EC | RESOLVED | 19 | SFC-series manual covers 50 SFC ec |
| MONDIAL_WING50I | RESOLVED | 19 | shared Mondial scooter table |
| MONDIAL_EXON50 | RESOLVED | 19 | shared Mondial scooter table |
| MONDIAL_TURISMO50I | RESOLVED | 19 | shared Mondial scooter table |
| KYMCO_XTOWN_CT250 | RESOLVED | 18 | CT250/300 chart; some cells jumbled (LOW/MEDIUM) |
| HONDA_PCX125 | PARTIAL | 5 | graphic schedule marks; time-based rows only |
| HONDA_CB125F | PARTIAL | 4 | graphic schedule marks; drive chain 500 km, brake fluid 2 yr |
| HONDA_SH125I | PARTIAL | 7 | service interval 1000→6000 km from indicator text |
| HONDA_ACTIVA125 / DIO110 / FORZA250 / ADV350 / CL250 / MONKEY / EM1E | UNRESOLVED | 0 | Honda graphic PDFs + CDN bot-block |
| CFMOTO_250SR / 250CLX / 250DUAL / 450NK / 450CLC | UNRESOLVED | 0 | paywalled / Cloudflare-blocked manuals |
| KYMCO_DOWNTOWN250I | UNRESOLVED | 0 | parsed manual covers X-Town, not Downtown |
| KUBA_CG50_PRO / KUBA_BLUEBERRY50 / RKS_NEW_LIGHT_PRO | UNRESOLVED | 0 | no model-specific official manual exists |

## 5. Policy highlights (first service → regular interval)

- Bajaj NS200 / NS125 / Dominar 250: 500–750 km → **5,000 km / 4 months**.
- RE Hunter 350: 500 km → **5,000 km / 6 months**.
- Yamaha XSR125 / NMAX 125: 1,000 km → **6,000 km / 12 months**.
- Yamaha XMAX 250: 1,000 km → **10,000 km / 12 months**.
- KTM 390 Duke: 1,000 km → **10,000 km / 12 months** (extended items 20,000 km / 24 months).
- CFMOTO 250NK: 500–1,000 km → oil every 3,000 km, service grid every 5,000 km.
- CFMOTO 650NK: 1,000 km → oil & filter **5,000 km**, inspections **10,000 km / 12 months**.
- TVS Raider 125 / Apache RTR 200 / Jupiter 125: 500–1,000 km → **6,000 km / 6 months**.
- SYM Jet X 125: 300 km → checkpoints 1,000 / 3,000 / 6,000 / 12,000 km; oil every 3,000 km.
- Mondial 50 cc range: 500–1,000 km / 1 month → **2,000 km / 6 months**.
- KYMCO X-Town CT 250: 1,000 km → ~6,000 km / 6 months; oil **5,000 km / 6 months**.
- Honda SH125i: 1,000 km → **6,000 km** (OIL CHANGE / maintenance indicator).

## 6. Conflicts

- Bajaj NS200 AIR_FILTER: BS VI manual 20,000 km vs pre-BS6 15,000 km → BS VI preferred.
- KYMCO X-Town CT250 COOLANT: chart remark "every 10,000 km / 1 yr" (row mapping uncertain
  in the jumbled grid) vs the more usual 2-year coolant change → flagged LOW, not resolved.

## 7. Quality gate (all pass)

`duplicate_task_rows 0 · negative_km 0 · zero_repeat_interval 0 · rows_missing_source_id 0 ·
orphan_source_id 0 · rows_missing_confidence 0 · rows_missing_evidence 0`. Every task row
carries `source_id` + `source_page` + `source_table` + `evidence` + `confidence`.

## 8. ML value

**V1 next-service KM/DAYS: PARTIALLY.** 23/39 models now have a manufacturer service grid
usable as a strong prior for `km_to_next_service` / `months_to_next_service`; the fleet-weighted
coverage is good for Yamaha/Bajaj/TVS/Mondial/CFMOTO but thin for Honda.

**V3 next-task prediction: PARTIALLY → YES for covered brands.** 432 rows with
`canonical_task_code` + `action` + `component_group` + `repeat_every_km` / `repeat_every_months`
are exactly the shape V3 needs (e.g. "at 10,000 km on a 650NK: ENGINE_OIL REPLACE,
ENGINE_OIL_FILTER REPLACE, SPARK_PLUG REPLACE, AIR_FILTER INSPECT, brake/steering/chain
INSPECT"). Coverage scales as the 16 gaps are filled.

## 9. Final verdict

**Every inventory model was genuinely researched; 23 of 39 are backed by a cited official
manufacturer schedule (19 to full task level).** The remaining 16 are honest gaps with a
concrete next action each — dominated by Honda's non-extractable schedule graphics and by
China/TR-market models whose only manual copies sit behind Cloudflare or paywalls. No interval
was invented and no schedule was copied between models.
