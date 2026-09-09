# V3 Motorcycle Identity UX Preflight

Date: 2026-09-08 (Europe/Istanbul)

## Repository state

- Repository: `ridebase-synthetic-dataset-v1`
- Branch: `main`
- Baseline HEAD / `origin/main`: `8a6435af03401c851876de56349940fc2c7f2211`
- Ahead / behind: `0 / 0`
- Worktree before this report: clean

## Existing V3 product flow

The existing product route is `POST /api/v3/predict/by-motorcycle`:

`motorcycle_id + landmark_date` → shared read-only V2.1 SQLite history adapter →
54 PIT-safe V2.1 base features → 277 frozen V3 features → frozen V3 predictor →
44 unchanged task probabilities → presentation-only Top-K policy.

`GET /api/v3/sample` currently returns only a valid synthetic `motorcycle_id` and
`landmark_date`. The Control Center places those identifiers in the form, and the
result currently leads with Top-K predictions. It does not identify the subject's
brand, model, year, odometer, or prior-service context.

## Available motorcycle metadata

| Field | Exists | Source | PIT-safe rule | Product useful | Notes |
|---|---:|---|---|---:|---|
| motorcycle_id | Yes | `motorcycles.motorcycle_id` | motorcycle must exist with `observation_start_date <= landmark` | Yes | Stable backend key |
| brand | Yes | `motorcycles.brand` | immutable identity row, gated by observation start | Yes | 10,000 / 10,000 present |
| model | Yes | `motorcycles.model_name` | immutable identity row, gated by observation start | Yes | 10,000 / 10,000 present |
| variant | Yes | model master `variant_or_generation` | unversioned model master; not needed for primary card | No | Kept out of the compact product card |
| model year | Yes | `motorcycles.production_year` | immutable identity row, gated by observation start | Yes | 10,000 / 10,000 present |
| registration date/year | Yes | `motorcycles.first_registration_date` | immutable identity row, gated by observation start | No | Model year is clearer for this UX |
| engine cc | Mostly | model master `engine_displacement_cc` | unversioned model master | No | 37 / 39 models; not required by target card |
| category | Yes | `motorcycles.category` | immutable identity row, gated by observation start | Optional | 10,000 / 10,000 present |
| current odometer | Yes | latest valid `mileage_timeline_monthly.closing_odometer_km` | `period_end_date <= landmark` | Yes | Same canonical source used by V2.1/V3 features |
| last service date | Yes when history exists | latest eligible `services.received_at` | status `DELIVERED` and date `<= landmark` | Yes | Never uses the next/target service |
| last service odometer | Yes when history exists | odometer on the same eligible service | same row and boundary as last service date | Yes | Hidden when missing |
| km since last service | Derivable | current odometer minus last eligible service odometer | both operands must be PIT-safe and odometer order must be consistent | Yes | Hidden when either operand is missing or the result would be negative; no fake zero |
| days since last service | Derivable | landmark minus last eligible service date | both dates PIT-safe | Yes | Hidden when service is missing |
| annual usage | Yes | active `usage_profiles.annual_km_baseline` | `profile_start_date <= landmark` and active at landmark | Yes | 10,000 / 10,000 source rows present |
| maintenance interval | Yes | maintenance policy/model master | not needed for identity card | No | Maintenance Urgency remains unchanged |
| last service type | Yes when history exists | same eligible service row | `received_at <= landmark` | No | Avoids irrelevant detail in primary card |

The production image already ships the full V1.4 `motorcycles` and model-master
reference files under `RIDEBASE_V3_SOURCE_DIR`. Per-motorcycle mileage, service,
task, and usage history remains sourced from the unchanged V2.1 SQLite adapter.

## Frozen baseline hashes

### V3

| Artifact | SHA-256 |
|---|---|
| `champion_model.joblib` | `2a1f0103c32a10bfcf56b6f7fd7073fa9d49eac3b718df519378c0ebfbc16eb1` |
| `calibrator.joblib` | `f64c9dab5d2886645f7c80fe2c01d192d58abead376625c20115dc2ff5347bb4` |
| `feature_list.json` | `9566bf2439a3876c8569e359461c8dc07f7883d486a2af7729b60c00184955ec` |
| `label_list.json` | `f1bd6d5c70d0776fbf76b1273510d411e54e6a0d015e526e4ec498c62e5d1e56` |
| `thresholds.json` | `12415d4f67cf62d9810aaaa0aecb42b5546ff4ce4fac39f15fb3e406e22ff550` |

### V2.1 / shared history

| Artifact | SHA-256 |
|---|---|
| `champion_model.joblib` | `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def` |
| `calibrator.joblib` | `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945` |
| `feature_list.json` | `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a` |
| `preprocessor.joblib` | `6b24e0ebc027f52bebb52841ec551cadb14b63bf2f540687a69ee0445ec9f990` |
| `v2_1_history_serving.sqlite` | `a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657` |

## Baseline regression

- Backend: PASS (130 tests)
- Control Center: PASS (110 tests)
- Legacy Next.js frontend: PASS (5 tests + TypeScript)
- Full ML suite was started as a separate baseline process; the final completion
  report records its terminal result together with the post-change regression.

## Implementation decision

Add response-only `motorcycle_context` and context provenance after the frozen V3
feature vector has been built and predictions have been calculated. The context
must never enter the predictor input. Enrich `/api/v3/sample` with the same safe
context and a derived friendly label. Missing metadata will be omitted, never
replaced by fabricated zeroes or placeholders.
