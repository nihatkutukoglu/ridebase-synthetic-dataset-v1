# V3 Phase 0 — Preflight

Session start: 2026-09-07. Working directory `/Users/nihatkutukoglu/Downloads/ridebase_synthetic_dataset_v1`.

## Repository state at start

| Item | Value |
|---|---|
| Repo root | `/Users/nihatkutukoglu/Downloads/ridebase_synthetic_dataset_v1` |
| Branch | `main` |
| HEAD | `b25f3b7b1f870c995b1e133a76230537d83d7365` |
| `origin/main` | `b25f3b7b1f870c995b1e133a76230537d83d7365` (in sync) |
| Working tree | clean (`git status --short` empty, `git diff --stat` empty) |
| Remote | `https://github.com/nihatkutukoglu/ridebase-synthetic-dataset-v1.git` |

Last 5 commits:

```
b25f3b7 Production reconciliation audit: ancestry safe, backend redeploy pending
4b84aac Finalize Control Center production hardening (FAZ 1-5)
69549f7 feat: add V1 natural-input live scenarios
b3467eb Record maintenance urgency live verification
2ecedf4 Harden maintenance urgency production contract
```

Tree was clean, so no unrelated work was at risk and nothing was discarded.

## Python environment

The repository has no checked-in virtualenv. Three interpreters were probed:

| Interpreter | pandas | sklearn | xgboost | lightgbm | catboost | pyarrow |
|---|---|---|---|---|---|---|
| `/opt/homebrew/Caskroom/miniconda/base/bin/python3` (3.14.7) | — | — | — | — | — | — |
| `/opt/homebrew/Caskroom/miniconda/base/envs/nlp/bin/python3` (3.11.16) | 3.0.5 | 1.9.0 | — | — | — | — |
| **`/usr/bin/python3` (3.9.6)** | **2.3.3** | **1.5.2** | **2.1.4** | **4.6.0** | **1.2.10** | **21.0.0** |
| `/opt/homebrew/bin/python3.11` (3.11.15) | 2.3.3 | 1.5.2 | 3.2.0 | 4.6.0 | 1.2.10 | 23.0.1 |

`/usr/bin/python3` is the project interpreter: it loads the frozen V2.1
`champion_model.joblib` / `preprocessor.joblib` with **no** XGBoost
version-mismatch warning, whereas `python3.11` (xgboost 3.2.0) emits a
serialisation warning on the same artifact. All V3 work uses `/usr/bin/python3`.
LightGBM and CatBoost are available, so Phase 12 can include them without
installing anything new.

## Data discovery (no filenames assumed)

### Source tables — four generator worlds coexist

| Location | services | service_tasks | motorcycles | Role |
|---|---|---|---|---|
| `source_tables/` (repo root) | 41,518 | 201,800 | 10,000 | v1.1-era core; byte-identical to `ridebase-ml/data/raw/source_tables/` (md5 `562af029…`) |
| `ridebase_v1_3/source_tables/` | 41,518 | 204,000 | 10,000 | frozen V1.3 core |
| **`ridebase_v1_4/source_tables/`** | **52,700** | **215,182** | **10,000** | **V2.1 production world** |
| `ridebase_v1_5/source_tables/` | 64,985 | 227,467 | 10,000 | V2.2 behavioural branch (challenger, never promoted) |

Thirteen tables per world: `appointments`, `customers`, `maintenance_policies`,
`maintenance_tasks`, `mileage_timeline_monthly`, `motorcycles`,
`ridebase_motorcycle_models_v1`, `service_parts`, `service_tasks`, `services`,
`services_enriched`, `usage_profiles`, `workshops`.

**V3 will use `ridebase_v1_4`** — the same world the frozen V2.1 production
champion was trained and served on (`data_freeze_manifest.json` →
`"dataset_version": "1.4.0-v2.1-dynamic-landmark"`). v1.5 is the V2.2 branch that
was *not* promoted; building V3 on it would make V3 incomparable with the live
product surface. This is recorded as a research decision, not a data preference.

### Task representation (the V3 target substrate)

- `source_tables/maintenance_tasks.csv` — **86 task codes**, columns
  `task_code, canonical_name_tr, canonical_name_en, component_group, action_type,
  is_periodic, is_wear_based, is_fault_based, requires_part,
  applicable_powertrain, required_final_drive, required_cooling_type,
  required_transmission_type, part_category_hint, can_be_next_service_target,
  notes, taxonomy_version`. The `can_be_next_service_target` flag and the
  powertrain/drivetrain applicability columns are the taxonomy's own eligibility
  contract and are used in Phase 2/3 rather than a hand-written label list.
- `service_tasks.csv` — one row per task line on a service
  (`service_task_id, service_id, motorcycle_id, task_code, trigger_reason,
  is_policy_due, policy_id, status, completed, severity, …`).
  `status ∈ {COMPLETED (200,385), DECLINED (1,415)}`.
- `maintenance_policies.csv` — 621 policy rows
  (`policy_kind, initial_trigger_km, recurring_km, initial_trigger_months,
  recurring_months, trigger_mode, *_multiplier, wear_mean_km, …`). This is the
  deterministic OEM rule layer that Phase 9 and Baseline 1 need.

**Early Phase-9 signal already visible in the raw data:** 82.5% of task lines carry
`is_policy_due = 1`, and `trigger_reason` is dominated by
`MILEAGE` (81,924), `MILEAGE_AND_TIME` (48,979), `TIME` (34,564) — i.e. ~82% of
all task lines are emitted by a deterministic threshold. `INSPECTION_BUNDLE`
(27,759), `INSPECTION_FINDING` (4,177), `FAULT` (3,283) and `WEAR` (1,114) make up
the remainder. This is flagged now and quantified properly in Phase 9.

### Pre-existing next-task target table

`derived_outputs/ml_next_task_targets.parquet` (41,518 × 106) already ships a
generator-authored multi-hot next-task target:
`target_definition = TASK_PRESENT_IN_NEXT_SERVICE_PLAN_COMPLETED_OR_DECLINED`,
`target_version = NEXT_TASK_TARGET_V1`, 81 task columns, 8,442 right-censored rows.

V3 **does not adopt it as-is**, for two reasons:
1. its landmark is the *previous service event*, one row per service, which is a
   single landmark strategy and cannot be compared against alternatives (Phase 6);
2. its label counts a task as positive when it was **declined**, whereas the V3
   mission statement is "which tasks are likely to be **performed**".

It is kept as a cross-check reference for Phase 3 taxonomy discovery.

### Existing V2.1 feature machinery (reused)

`ridebase-ml/ridebase_ml/v2_1/landmarks.py` (628 lines) builds a monthly dynamic
landmark grid with a 54-column PIT-safe feature contract, already materialised at
`ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet`
(**256,841 rows × 74 cols, 8,907 motorcycles, 2021-01-31 → 2026-07-31**), carrying
`primary_split` (TRAIN 159,336 / VALIDATION 42,588 / TEST 54,917),
`is_unseen_motorcycle_holdout` (39,360 rows) and `modeling_role`. It also carries
`next_service_id`, the exact pointer V3 needs to attach its multi-label target.

Reusing this grid is the single biggest correctness lever available: the landmark
placement, the point-in-time feature semantics and the temporal split have already
been leakage-audited and shipped for V2.1. V3 adds task-history features and the
multi-label target on top; it does not re-derive the base.

Known issue carried forward to Phase 6: on the observed subset (208,746 rows,
41,580 distinct target services) there are **5.0 landmarks per target service on
average (median 4, max 31)**. Un-deduplicated this would inflate every metric, so
Phase 6 must impose a landmark-selection policy.

### Existing V3-related code/config

None. `ridebase_ml` contains `policy/`, `v2/`, `v2_1/`, `v2_2/`, `v2_2_1/`, `v2_3/`
— no `v3` package, no `v3_*` config, no V3 reports. V3 starts from a clean slate.

### Tests and reports

- `ridebase-ml/tests/` — V2.1 history contract/builder/parity suites and others.
- `ridebase-v1-dashboard/backend/tests/` — API, config, V2.1 history API suites.
- `ridebase-control-center/tests/` — frontend/product suites.
- `reports/`, `ridebase-ml/reports/`, `docs/` — existing V1/V2.x research record.

Full inventory of existing suites and their pass/fail state is recorded in Phase 29.

## Preflight conclusion

Tree clean, production world identified (v1.4), task taxonomy and policy layer
located, PIT-safe landmark grid available for reuse, no pre-existing V3 code to
reconcile. Proceeding to Phase 1 freeze.
