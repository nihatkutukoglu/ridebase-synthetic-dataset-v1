# Required Production Extract — Issue #579

STATUS: BLOCKED until a read-only, anonymized production extract is supplied.

No production schema/export was available in the RideBase ML workspace. The following is the minimum semantic contract; source-native column names should be retained and documented in a manifest.

## motorcycles
- `motorcycle_id` — stable pseudonymous key
- `tenant_id` or `workshop_id` — pseudonymous tenant/workshop key
- `mileage` or current odometer
- `model` — if available
- `created_at`

## services
- `service_id` — stable pseudonymous key
- `motorcycle_id`
- `tenant_id` or `workshop_id`
- service date/timestamp
- service mileage/odometer
- `created_at`

## service_todos
- `todo_id`
- `service_id`
- title
- status — if available
- `created_at`

## part_categories
- `category_id`
- `tenant_id` or `workshop_id`
- category name

## Optional but useful
- `service_parts`, `parts`, `workshops`/`tenants`
- motorcycle brand/model/year
- maintenance policy or schedule fields

## Privacy and delivery rules
- Remove names, email, phone, address, VIN/chassis, plate, identity numbers and free-form personal notes.
- Keep stable pseudonymous entity and tenant IDs so joins and longitudinal ordering remain possible.
- Include an observation-window end timestamp and an export manifest with table row counts, schema, timezone and extraction time.
- Deliver CSV, Parquet, JSON or SQLite. SQLite will be opened read-only.
