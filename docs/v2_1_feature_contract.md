# V2.1 Feature Contract

All V2.1 fields are derived ML fields. None is added to RideBase source tables.

## Identifiers and audit fields

`landmark_id`, `motorcycle_id`, `customer_id`, `workshop_id`, `model_id`,
`landmark_at`, `source_last_service_id`, `observation_start_date` and
`initial_mileage_km` remain trace/audit fields and are excluded from model
features.

## Model feature families

- Stable domain state: brand, category, powertrain, policy group, production
  age, ownership age and customer type.
- Usage: usage type/intensity, annual baseline, recent 90-day mileage and
  recent-to-baseline ratio.
- Current landmark state: `current_odometer_km_at_landmark`, cyclical month
  sine/cosine, days/km since last service and recent driving rate.
- Maintenance pressure: canonical interval days/km, due ratios, overdue
  days/km, due-now flag, due-task count and distance/time to the next scheduled
  due point.
- Past service history: rolling counts, past event types, historical delay and
  on-time rate, cumulative spend, and last known service attributes.
- Workshop constraints: bays, appointment rate, parts lead time, volume and
  price level.

The authoritative machine-readable list and dtypes are generated in
`v2_1_feature_dictionary.csv`.

## Explicitly forbidden

Targets, censor flags, future/next-service information, split labels,
`snapshot_year`/`landmark_year`, `days_observed`, and arbitrary-day
`current_service_*` fields are forbidden model inputs. Absolute year is not
used. Seasonality is represented only by cyclical month.

## Real-data migration

Every feature can be calculated from the unchanged future RideBase contract:
motorcycle/model data, monthly or event-time mileage, services and completed
tasks, customer/usage history, policies and workshop attributes. In a real
deployment the caller supplies `motorcycle_id`; the backend reads those tables
and invokes the same landmark feature builder. Users never enter dozens of ML
features manually.
