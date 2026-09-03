# RideBase V2.1 history pipeline contract

Status: **Prompt 1 contract frozen. Full V1.4 history derivation and API wiring are not implemented in this gate.**

Model status remains **V2.1 EXPERIMENTAL LIVE — SYNTHETICALLY VALIDATED, REAL FLEET VALIDATION PENDING**. V3 remains on hold.

## Frozen context

- Starting repository HEAD: `34bc779` (`main`).
- Frozen champion: `xgb_cox` with per-horizon isotonic calibration.
- Frozen feature count: 54 (13 categorical, 41 numeric).
- `feature_list.json` SHA-256: `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a`.
- `champion_model.joblib` SHA-256: `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def`.
- `preprocessor.joblib` SHA-256: `6b24e0ebc027f52bebb52841ec551cadb14b63bf2f540687a69ee0445ec9f990`.
- `calibrator.joblib` SHA-256: `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945`.
- Modeling-table SHA-256 (data freeze manifest): `427e9e1fd321977f95c65c581df719c779747d0b8026aacefe0a4abb5fecdcc4`.
- Artifact hashes remain authoritative in `ridebase-ml/models/v2_1_v1_4/artifact_manifest.json`.
- V1.4 is compatible with the frozen 13-table v1.3 source-schema contract. No source table or source column is changed by this work.

The existing `POST /api/v2_1/predict/scenario` route is an honest manual what-if path. It resolves model-master, user-entered, policy and simple landmark features; other frozen inputs stay missing and are imputed by the frozen preprocessor. It is not history reconstruction, and it does not overlay a sample row.

## Canonical request and meaning

```json
{
  "motorcycle_id": "MC000001",
  "landmark_date": "2026-06-30"
}
```

Using only information known for that motorcycle on or before `landmark_date`, derive the frozen V2.1 feature contract and estimate service-return probability within 30/60/90/120 days. This is not maintenance-needed probability.

The landmark is a calendar date. Records anywhere on that date are included; records whose semantic event date is strictly later are excluded.

## Architecture

`RideBaseSourceAdapter` is a read-only abstraction. A concrete file/DB/API adapter implements only `read_table`; the public methods apply point-in-time filtering:

- `get_motorcycle`
- `get_customer_for_motorcycle`
- `get_services_before`
- `get_mileage_before`
- `get_service_tasks_before`
- `get_service_parts_before`
- `get_appointments_before`
- `get_usage_profile`
- `get_workshop_history`
- `get_model_master`
- `get_maintenance_policy`

`build_features(motorcycle_id, landmark_date, source_adapter)` returns `features`, `provenance`, `source_evidence`, `warnings`, `feature_coverage`, and `landmark`. `features` and `provenance` have exactly the frozen 54 keys. In Prompt 1 only calendar terms and a source-supported current odometer are resolved; unresolved values stay null. The full synthetic derivation is gated to Prompt 2.

Coverage is a source-resolution measure, never confidence.

## Point-in-time timestamp audit

| Source | Boundary at landmark T | Notes / ambiguity |
|---|---|---|
| motorcycles | `observation_start_date <= T` | Table is not versioned. Historical values of mutable `is_active`, ownership/workshop/customer links cannot be reconstructed after an update. Frozen immutable identity/date fields are usable. |
| customers | `first_seen_date <= T` | Table is not versioned. Current `is_active`/`churn_date` and changed attributes must not be treated as historical truth without future versioning. |
| services / services_enriched | `received_at.date <= T`; only configured eligible statuses in feature derivation | `received_at` is the frozen offline service time. Later completion/delivery fields may be after T and must not influence T. |
| mileage_timeline_monthly | `period_end_date <= T` | `closing_odometer_km` is current odometer for matching monthly landmarks. `initial_mileage_km` is never current odometer. |
| service_tasks | completed tasks use `completed_at.date <= T` | Started-but-not-completed tasks are excluded from completed-task features. |
| service_parts | inherit eligible parent service and task boundaries | No row timestamp exists. A part added later to an already-eligible parent cannot be detected; append/update audit timestamps are required in a real source. |
| appointments | `created_at.date <= T` | `scheduled_at` may be future but the booking is known. Status/service link are mutable and unsafe historically without status versioning. Frozen 54-feature pipeline currently uses workshop master `appointment_rate`, not appointment-event aggregates. |
| usage_profiles | `profile_start_date <= T <= profile_end_date` (open end allowed) | Profile intervals provide point-in-time selection. Overlap is resolved to latest start; overlapping real rows should be rejected/audited by a concrete adapter. |
| workshops | linked unversioned master row | Capacity/rate/lead-time/volume values can change. Exact historical reconstruction is unavailable under the current source contract. |
| model master | linked unversioned master row | Treated as reference master; historical corrections are not versioned. |
| maintenance_policies | applicable model/group rows from unversioned master | Policy effective-from/to dates do not exist. Exact historical policy reconstruction is unavailable after policy changes. |

## Frozen feature mapping

Missing behavior is null plus optional frozen-preprocessor imputation unless stated otherwise. The machine-readable exhaustive mapping is `FEATURE_MAPPING` in `history_features.py`; tests require exact equality with the frozen list.

| Feature | Source(s) | Derivation | Timestamp boundary | Leakage risk | Missing behavior | Provenance | Reproducibility class |
|---|---|---|---|---|---|---|---|
| brand | motorcycles | direct | observation start <= T | low | null | SOURCE_MOTORCYCLE | directly available |
| category | motorcycles | direct | observation start <= T | low | null | SOURCE_MOTORCYCLE | directly available |
| powertrain_type | motorcycles | direct | observation start <= T | low | null | SOURCE_MOTORCYCLE | directly available |
| policy_group | model master | model lookup | unversioned | medium | null | MODEL_MASTER | directly available |
| customer_type | customers | linked lookup | first seen <= T | medium | null | SOURCE_CUSTOMER | customer/history-derived |
| usage_type | usage profile | active profile | profile interval contains T | low | null | HISTORY_DERIVED | customer/history-derived |
| riding_intensity | usage profile | active profile | profile interval contains T | low | null | HISTORY_DERIVED | customer/history-derived |
| climate_zone | usage profile | active profile | profile interval contains T | low | null | HISTORY_DERIVED | customer/history-derived |
| storage_condition | usage profile | active profile | profile interval contains T | low | null | HISTORY_DERIVED | customer/history-derived |
| workshop_region | workshops | linked master | unversioned | medium | null | HISTORY_DERIVED | directly available |
| workshop_price_level | workshops | linked master | unversioned | medium | null | HISTORY_DERIVED | directly available |
| last_service_type_code | services | last eligible value | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| last_arrival_mode | services | last eligible value | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| production_age_days | motorcycles + T | T - registration, clip 0 | registration <= T | low | null | LANDMARK_DERIVED | landmark-derived |
| ownership_age_days | motorcycles + T | T - ownership start, clip 0 | ownership start <= T | low | null | LANDMARK_DERIVED | landmark-derived |
| is_fleet_customer | customers | linked flag | first seen <= T | medium | null | SOURCE_CUSTOMER | customer/history-derived |
| current_odometer_km_at_landmark | mileage | latest valid closing odometer | period end <= T | low | null; never initial mileage | SOURCE_MILEAGE_HISTORY | mileage-history-derived |
| annual_km_baseline | usage profile | active profile value | profile interval contains T | low | null | HISTORY_DERIVED | customer/history-derived |
| recent_90d_km | mileage | frozen three-month sum | period end <= T | low | null | SOURCE_MILEAGE_HISTORY | mileage-history-derived |
| recent_vs_baseline_usage_ratio | mileage + profile | 90d annualized / baseline | inputs <= T | low | null | HISTORY_DERIVED | mileage-history-derived |
| days_since_last_service | services + T | elapsed calendar days | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| km_since_last_service | mileage + services | current minus service odo, clip 0 | inputs <= T | low | null | HISTORY_DERIVED | service-history-derived |
| avg_km_per_day_since_last_service | mileage + services | km/days; same-day zero | inputs <= T | low | null | HISTORY_DERIVED | service-history-derived |
| oem_interval_days | policy + model | frozen primary-policy rule | unversioned | medium | null | POLICY_DERIVED | policy-derived |
| oem_interval_km | policy + model | frozen primary-policy rule | unversioned | medium | null | POLICY_DERIVED | policy-derived |
| days_due_ratio | service + policy | elapsed / interval | history <= T; policy unversioned | medium | null | POLICY_DERIVED | policy-derived |
| km_due_ratio | mileage + service + policy | elapsed / interval | history <= T; policy unversioned | medium | null | POLICY_DERIVED | policy-derived |
| max_due_ratio | derived ratios | maximum non-null ratio | inputs <= T | low | null | POLICY_DERIVED | policy-derived |
| days_overdue | service + policy | max(elapsed - interval, 0) | history <= T; policy unversioned | medium | null | POLICY_DERIVED | policy-derived |
| km_overdue | mileage + service + policy | max(elapsed - interval, 0) | history <= T; policy unversioned | medium | null | POLICY_DERIVED | policy-derived |
| maintenance_due_now | task + policy | any applicable due task | completed/history <= T | medium | null | POLICY_DERIVED | task/part-derived |
| due_task_count | task + policy | count due tasks | completed <= T | medium | null | POLICY_DERIVED | task/part-derived |
| critical_due_task_count | task + policy | count critical due tasks | completed <= T | medium | null | POLICY_DERIVED | task/part-derived |
| days_until_next_scheduled_due | task + policy | minimum remaining days | completed <= T | medium | null | POLICY_DERIVED | task/part-derived |
| km_until_next_scheduled_due | task + policy + mileage | minimum remaining km | history <= T | medium | null | POLICY_DERIVED | task/part-derived |
| recent_service_count_90d | services | inclusive frozen 90d window | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| recent_service_count_365d | services | inclusive frozen 365d window | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| prior_service_count | services | eligible prefix count | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| prior_periodic_service_count | services | PERIODIC prefix count | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| prior_breakdown_count | services | BREAKDOWN prefix count | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| prior_repair_count | services | REPAIR prefix count | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| historical_service_delay_mean_days | services | frozen missing-as-zero mean | received <= T | medium | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| historical_on_time_rate | services | share delay <= 0 | received <= T | medium | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| cumulative_service_spend | services | frozen missing-as-zero sum | received <= T | medium | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| last_service_was_breakdown | services | last eligible flag | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| last_service_was_warranty | services | last eligible flag | received <= T | low | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| last_service_task_count | tasks + services | completed tasks of last service | completed/received <= T | low | null | SOURCE_TASK_HISTORY | task/part-derived |
| last_service_spend | services | frozen last grand total | received <= T | medium | null | SOURCE_SERVICE_HISTORY | service-history-derived |
| service_bay_count | workshops | linked master | unversioned | high | null | HISTORY_DERIVED | directly available |
| appointment_rate | workshops | linked master (not event aggregate) | unversioned | high | null | HISTORY_DERIVED | directly available |
| avg_parts_lead_days | workshops | linked master | unversioned | high | null | HISTORY_DERIVED | directly available |
| customer_volume_index | workshops | linked master | unversioned | high | null | HISTORY_DERIVED | directly available |
| landmark_month_sin | landmark date | sin(2πm/12) | request T | none | always resolved | LANDMARK_DERIVED | landmark-derived |
| landmark_month_cos | landmark date | cos(2πm/12) | request T | none | always resolved | LANDMARK_DERIVED | landmark-derived |

## Reuse and parity obligation

The offline builder remains the frozen semantic reference. Prompt 2 should reuse/refactor `_primary_policy_table`, `_applicable_policies`, `_history_features`, and `_due_task_features` where practical instead of copying formulas. Any refactor must preserve the frozen modeling table and artifact behavior. Prompt 3 must compare every feature and predictions; current Prompt 1 tests are contract/leakage tests, not parity proof.

## Currently unavailable for exact historical reproduction

- Historically correct workshop capacity/rate/lead-time/volume after master-data changes.
- Historically correct maintenance-policy/model-master values after reference-data changes.
- Appointment status as it was at T when a booking row was updated later.
- A service-part row's insertion/update time when its parent was already eligible.
- Historically correct mutable motorcycle/customer state and relationship changes.

These gaps stay explicit; they are not filled with guessed history. A real adapter needs temporal versions or append-only change/audit data.
