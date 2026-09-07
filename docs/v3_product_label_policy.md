# V3 Product Label Policy

Machine-readable: [`config/v3_product_label_policy.json`](../config/v3_product_label_policy.json).

**This is a presentation policy, not a model change.** No label is removed from the
frozen artifacts. All 44 stay in the model and in every API response under
`all_task_probabilities` and `binary_predictions`. The policy governs only what the
product *leads with*, and how much confidence the UI is allowed to claim.

Every field below is derived from **frozen research artifacts only** —
`reports/v3/22_test_per_label.csv` (the single frozen TEST touch) and
`reports/v3/09_generator_process_by_label.csv` (the generating-process audit).
Nothing was re-measured and nothing was re-fit.

## The rules

| status | rule |
|---|---|
| `HIDDEN_BY_DEFAULT` | Phase-9 generating process is class E — a random fault or inspection-finding event. Not learnable from any landmark observable. |
| `LOW_CONFIDENCE` | fewer than 30 TEST positives, or separation too weak (PR-AUC < 0.05 or lift < 1.3x). |
| `PRIMARY` | `A_CORE` support class **and** (TEST PR-AUC ≥ 0.15 with ≥ 1.5x prevalence lift, **or** absolute TEST PR-AUC ≥ 0.4). |
| `SECONDARY` | TEST PR-AUC ≥ 0.05 and ≥ 1.3x prevalence lift, below the PRIMARY bar. |

### Why absolute PR-AUC, not just lift

Lift over prevalence alone is the wrong test for a high-prevalence label. ENGINE_OIL_CHANGE has TEST PR-AUC 0.854 on 4,626 positives - the most reliable label in the set - but only 1.09x lift, because at 78% prevalence there is almost no headroom. Judging on lift alone marked it LOW_CONFIDENCE, which is why the absolute-PR-AUC branch exists.

The first draft of this policy used lift alone and put `ENGINE_OIL_CHANGE` in
`LOW_CONFIDENCE` — the single most reliable label in the set, marked as the least
trustworthy. It was caught while building the policy, before anything was committed,
and it is recorded here rather than quietly corrected because the failure mode
generalises: any reliability rule expressed purely as a ratio will bury whatever is
already common. A regression test (`test_high_prevalence_reliable_label_is_primary`)
pins the corrected behaviour.

## Counts

| status | labels |
|---|---|
| HIDDEN_BY_DEFAULT | 15 |
| SECONDARY | 13 |
| PRIMARY | 12 |
| LOW_CONFIDENCE | 4 |
| **total** | **44** |

## Confidence tiers

Computed in `ridebase_ml.v3.product.confidence_tier`, in this order:

1. Feature coverage below 80% → `SINIRLI VERİ` (history could not be rebuilt).
2. `HIDDEN_BY_DEFAULT` label → `DÜŞÜK` **regardless of probability**.
3. `LOW_CONFIDENCE` label → capped at `ORTA`.
4. Coverage below 95% → capped at `ORTA`.
5. `PRIMARY` label at probability ≥ 60% → `YÜKSEK`.
6. Probability ≥ 25% → `ORTA`, else `DÜŞÜK`.

Rule 2 is the one that matters: **a high number on an unlearnable label must never
buy confidence.** A 99% probability on `WHEEL_BALANCE` is DÜŞÜK, and the reason
string says why.

### PRIMARY — 12 labels

Can lead the card and can reach YÜKSEK confidence.

| task_code | Türkçe | English | grup | TEST + | prevalence | PR-AUC | lift | not |
|---|---|---|---|---|---|---|---|---|
| `ENGINE_OIL_CHANGE` | Motor Yağı Değişimi | Engine Oil Change | ENGINE | 4626 | 0.7846 | 0.854 | 1.09x | CORE label, TEST PR-AUC 0.854 on 4626 positives (absolute PR-AUC 0.854). |
| `CHAIN_CLEAN` | Zincir Temizliği | Drive Chain Cleaning | FINAL_DRIVE | 510 | 0.2519 | 0.603 | 2.40x | CORE label, TEST PR-AUC 0.603 on 510 positives (absolute PR-AUC 0.603). |
| `CHAIN_LUBRICATE` | Zincir Yağlama | Drive Chain Lubrication | FINAL_DRIVE | 433 | 0.2138 | 0.487 | 2.28x | CORE label, TEST PR-AUC 0.487 on 433 positives (absolute PR-AUC 0.487). |
| `CHAIN_INSPECTION` | Zincir Kontrolü | Drive Chain Inspection | FINAL_DRIVE | 249 | 0.1230 | 0.303 | 2.47x | CORE label, TEST PR-AUC 0.303 on 249 positives (2.5x prevalence). |
| `BATTERY_TEST` | Akü Testi | Battery Test | ELECTRICAL | 780 | 0.1321 | 0.298 | 2.26x | CORE label, TEST PR-AUC 0.298 on 780 positives (2.3x prevalence). |
| `AIR_FILTER_INSPECTION` | Hava Filtresi Kontrolü | Air Filter Inspection | INTAKE | 774 | 0.1313 | 0.289 | 2.20x | CORE label, TEST PR-AUC 0.289 on 774 positives (2.2x prevalence). |
| `AIR_FILTER_CHANGE` | Hava Filtresi Değişimi | Air Filter Replacement | INTAKE | 616 | 0.1045 | 0.265 | 2.53x | CORE label, TEST PR-AUC 0.265 on 616 positives (2.5x prevalence). |
| `BRAKE_FLUID_CHECK` | Fren Hidroliği Kontrolü | Brake Fluid Check | BRAKES | 658 | 0.1114 | 0.251 | 2.25x | CORE label, TEST PR-AUC 0.251 on 658 positives (2.2x prevalence). |
| `GENERAL_SAFETY_INSPECTION` | Genel Güvenlik Kontrolü | General Safety Inspection | GENERAL | 611 | 0.1035 | 0.244 | 2.36x | CORE label, TEST PR-AUC 0.244 on 611 positives (2.4x prevalence). |
| `BRAKE_FLUID_CHANGE` | Fren Hidroliği Değişimi | Brake Fluid Replacement | BRAKES | 255 | 0.0432 | 0.229 | 5.30x | CORE label, TEST PR-AUC 0.229 on 255 positives (5.3x prevalence). |
| `CVT_BELT_INSPECTION` | CVT Kayışı Kontrolü | CVT Belt Inspection | TRANSMISSION | 245 | 0.0730 | 0.174 | 2.38x | CORE label, TEST PR-AUC 0.174 on 245 positives (2.4x prevalence). |
| `CVT_CASE_INSPECTION` | CVT Kutu Kontrolü | CVT Case Inspection | TRANSMISSION | 254 | 0.0756 | 0.159 | 2.10x | CORE label, TEST PR-AUC 0.159 on 254 positives (2.1x prevalence). |
### SECONDARY — 13 labels

Shown in the ranked list; capped below YÜKSEK.

| task_code | Türkçe | English | grup | TEST + | prevalence | PR-AUC | lift | not |
|---|---|---|---|---|---|---|---|---|
| `FRONT_TIRE_CHANGE` | Ön Lastik Değişimi | Front Tire Replacement | TIRES_WHEELS | 467 | 0.0791 | 0.198 | 2.50x | real but weaker signal: TEST PR-AUC 0.198 = 2.5x prevalence on 467 positives. |
| `COOLANT_LEVEL_CHECK` | Soğutma Sıvısı Seviye Kontrolü | Coolant Level Check | COOLING | 145 | 0.0831 | 0.144 | 1.74x | real but weaker signal: TEST PR-AUC 0.144 = 1.7x prevalence on 145 positives. |
| `CVT_BELT_CHANGE` | CVT Kayışı Değişimi | CVT Belt Replacement | TRANSMISSION | 136 | 0.0405 | 0.136 | 3.36x | real but weaker signal: TEST PR-AUC 0.136 = 3.4x prevalence on 136 positives. |
| `FORK_INSPECTION` | Ön Amortisör Kontrolü | Front Fork Inspection | SUSPENSION | 219 | 0.0371 | 0.116 | 3.13x | real but weaker signal: TEST PR-AUC 0.116 = 3.1x prevalence on 219 positives. |
| `CVT_ROLLER_INSPECTION` | Varyatör Ruloları Kontrolü | CVT Roller Inspection | TRANSMISSION | 182 | 0.0542 | 0.108 | 1.99x | real but weaker signal: TEST PR-AUC 0.108 = 2.0x prevalence on 182 positives. |
| `FRONT_BRAKE_PAD_INSPECTION` | Ön Fren Balatası Kontrolü | Front Brake Pad Inspection | BRAKES | 176 | 0.0298 | 0.101 | 3.38x | real but weaker signal: TEST PR-AUC 0.101 = 3.4x prevalence on 176 positives. |
| `SPARK_PLUG_INSPECTION` | Buji Kontrolü | Spark Plug Inspection | IGNITION | 116 | 0.0197 | 0.096 | 4.87x | real but weaker signal: TEST PR-AUC 0.096 = 4.9x prevalence on 116 positives. |
| `VALVE_CLEARANCE_INSPECTION` | Supap Boşluğu Kontrolü | Valve Clearance Inspection | ENGINE | 183 | 0.0310 | 0.091 | 2.94x | real but weaker signal: TEST PR-AUC 0.091 = 2.9x prevalence on 183 positives. |
| `FRONT_TIRE_INSPECTION` | Ön Lastik Kontrolü | Front Tire Inspection | TIRES_WHEELS | 123 | 0.0208 | 0.081 | 3.91x | real but weaker signal: TEST PR-AUC 0.081 = 3.9x prevalence on 123 positives. |
| `FINAL_GEAR_OIL_CHANGE` | Son Dişli Yağı Değişimi | Final Gear Oil Change | TRANSMISSION | 112 | 0.0334 | 0.068 | 2.03x | real but weaker signal: TEST PR-AUC 0.068 = 2.0x prevalence on 112 positives. |
| `WHEEL_BEARING_INSPECTION` | Teker Rulmanı Kontrolü | Wheel Bearing Inspection | TIRES_WHEELS | 154 | 0.0261 | 0.067 | 2.57x | real but weaker signal: TEST PR-AUC 0.067 = 2.6x prevalence on 154 positives. |
| `SPARK_PLUG_CHANGE` | Buji Değişimi | Spark Plug Replacement | IGNITION | 83 | 0.0141 | 0.062 | 4.37x | real but weaker signal: TEST PR-AUC 0.062 = 4.4x prevalence on 83 positives. |
| `COOLANT_CHANGE` | Soğutma Sıvısı Değişimi | Coolant Replacement | COOLING | 57 | 0.0327 | 0.058 | 1.79x | real but weaker signal: TEST PR-AUC 0.058 = 1.8x prevalence on 57 positives. |
### LOW_CONFIDENCE — 4 labels

Returned and rankable, but de-emphasised and never YÜKSEK.

| task_code | Türkçe | English | grup | TEST + | prevalence | PR-AUC | lift | not |
|---|---|---|---|---|---|---|---|---|
| `REAR_TIRE_INSPECTION` | Arka Lastik Kontrolü | Rear Tire Inspection | TIRES_WHEELS | 75 | 0.0127 | 0.043 | 3.42x | TEST PR-AUC 0.043 vs prevalence 0.0127 (lift 3.4x) - separation too weak to present with confidence. |
| `REAR_BRAKE_PAD_INSPECTION` | Arka Fren Balatası Kontrolü | Rear Brake Pad Inspection | BRAKES | 69 | 0.0117 | 0.032 | 2.71x | TEST PR-AUC 0.032 vs prevalence 0.0117 (lift 2.7x) - separation too weak to present with confidence. |
| `STEERING_BEARING_INSPECTION` | Gidon Rulmanı Kontrolü | Steering Head Bearing Inspection | STEERING | 55 | 0.0093 | 0.023 | 2.43x | TEST PR-AUC 0.023 vs prevalence 0.0093 (lift 2.4x) - separation too weak to present with confidence. |
| `REAR_TIRE_CHANGE` | Arka Lastik Değişimi | Rear Tire Replacement | TIRES_WHEELS | 21 | 0.0036 | 0.011 | 3.11x | only 21 TEST positives - metrics carry wide uncertainty. |
### HIDDEN_BY_DEFAULT — 15 labels

Never leads the product list. Always DÜŞÜK confidence regardless of probability.

| task_code | Türkçe | English | grup | TEST + | prevalence | PR-AUC | lift | not |
|---|---|---|---|---|---|---|---|---|
| `FUEL_SYSTEM_DIAGNOSTIC` | Yakıt Sistemi Arıza Teşhisi | Fuel System Diagnostic | FUEL | 199 | 0.0338 | 0.053 | 1.56x | Phase-9 generating process E_BREAKDOWN_RANDOM_EVENT: a random event conditioned only on a service happening at all. TEST PR-AUC 0.053 at prevalence 0.0338 - no landmark observable predicts it. |
| `ENGINE_COMPRESSION_TEST` | Motor Kompresyon Testi | Engine Compression Test | ENGINE | 180 | 0.0305 | 0.044 | 1.45x | Phase-9 generating process E_BREAKDOWN_RANDOM_EVENT: a random event conditioned only on a service happening at all. TEST PR-AUC 0.044 at prevalence 0.0305 - no landmark observable predicts it. |
| `ABS_DIAGNOSTIC` | ABS Sistem Teşhisi | ABS System Diagnostic | BRAKES | 184 | 0.0312 | 0.041 | 1.31x | Phase-9 generating process E_BREAKDOWN_RANDOM_EVENT: a random event conditioned only on a service happening at all. TEST PR-AUC 0.041 at prevalence 0.0312 - no landmark observable predicts it. |
| `ENGINE_FAULT_DIAGNOSTIC` | Motor Arıza Teşhisi | Engine Fault Diagnostic | ENGINE | 28 | 0.0047 | 0.023 | 4.83x | Phase-9 generating process E_BREAKDOWN_RANDOM_EVENT: a random event conditioned only on a service happening at all. TEST PR-AUC 0.023 at prevalence 0.0047 - no landmark observable predicts it. |
| `WHEEL_BALANCE` | Teker Balans Ayarı | Wheel Balancing | TIRES_WHEELS | 26 | 0.0044 | 0.020 | 4.48x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.020 at prevalence 0.0044 - no landmark observable predicts it. |
| `THROTTLE_BODY_CLEAN` | Gaz Kelebeği Temizliği | Throttle Body Cleaning | INTAKE | 20 | 0.0034 | 0.016 | 4.82x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.016 at prevalence 0.0034 - no landmark observable predicts it. |
| `BRAKE_DISC_CHANGE` | Fren Diski Değişimi | Brake Disc Replacement | BRAKES | 27 | 0.0046 | 0.012 | 2.59x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.012 at prevalence 0.0046 - no landmark observable predicts it. |
| `ECU_DIAGNOSTIC_SCAN` | ECU Arıza Taraması | ECU Diagnostic Scan | ELECTRICAL | 41 | 0.0069 | 0.011 | 1.61x | Phase-9 generating process E_BREAKDOWN_RANDOM_EVENT: a random event conditioned only on a service happening at all. TEST PR-AUC 0.011 at prevalence 0.0069 - no landmark observable predicts it. |
| `WHEEL_BEARING_CHANGE` | Teker Rulmanı Değişimi | Wheel Bearing Replacement | TIRES_WHEELS | 26 | 0.0044 | 0.008 | 1.86x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.008 at prevalence 0.0044 - no landmark observable predicts it. |
| `VALVE_CLEARANCE_ADJUST` | Supap Boşluğu Ayarı | Valve Clearance Adjustment | ENGINE | 21 | 0.0036 | 0.008 | 2.22x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.008 at prevalence 0.0036 - no landmark observable predicts it. |
| `BRAKE_SYSTEM_BLEED` | Fren Sisteminin Havasını Alma | Brake System Bleeding | BRAKES | 29 | 0.0049 | 0.007 | 1.47x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.007 at prevalence 0.0049 - no landmark observable predicts it. |
| `STEERING_BEARING_CHANGE` | Gidon Rulmanı Değişimi | Steering Head Bearing Replacement | STEERING | 17 | 0.0029 | 0.007 | 2.28x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.007 at prevalence 0.0029 - no landmark observable predicts it. |
| `FORK_SEAL_CHANGE` | Amortisör Keçesi Değişimi | Fork Seal Replacement | SUSPENSION | 16 | 0.0027 | 0.004 | 1.67x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.004 at prevalence 0.0027 - no landmark observable predicts it. |
| `FUEL_INJECTOR_CLEAN` | Enjektör Temizliği | Fuel Injector Cleaning | FUEL | 21 | 0.0036 | 0.004 | 1.22x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.004 at prevalence 0.0036 - no landmark observable predicts it. |
| `BATTERY_CHANGE` | Akü Değişimi | Battery Replacement | ELECTRICAL | 17 | 0.0029 | 0.004 | 1.45x | Phase-9 generating process E_INSPECTION_FINDING_RANDOM: a random event conditioned only on a service happening at all. TEST PR-AUC 0.004 at prevalence 0.0029 - no landmark observable predicts it. |
