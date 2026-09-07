# V3 Productization Phase 0 — Preflight

Session start 2026-09-07, continuing directly from the V3 research session.

## Repository state

| item | value |
|---|---|
| repo root | `/Users/nihatkutukoglu/Downloads/ridebase_synthetic_dataset_v1` |
| branch | `main` |
| HEAD at start | `43d2ba3d0ca564eae1e7cf96fc377039e16b267d` |
| `origin/main` | identical — in sync |
| working tree | clean |
| remote | `https://github.com/nihatkutukoglu/ridebase-synthetic-dataset-v1.git` |

The six V3 research commits (`6e4924b` … `43d2ba3`) sit on top of the pending
production-reconciliation work (`b25f3b7`). **Nothing from that pending work was
reverted, rebased or overwritten** — this session only adds commits on top.

## Discovered paths

| what | where |
|---|---|
| V3 completion report | `reports/v3/V3_OVERNIGHT_COMPLETION_REPORT.md` |
| V3 model artifacts | `ridebase-ml/models/v3_research/` |
| labels / features / thresholds / calibration | `label_list.json`, `feature_list.json`, `thresholds.json`, `calibration_report.json` |
| V3 dataset + split | rebuilt deterministically by `ridebase_ml.v3.dataset.build` (seed 20260907) |
| V3 research tests | `ridebase-ml/tests/test_v3_{target_contract,pit_safety,predictor}.py` |
| V2.1 frozen hashes | `reports/v3/01_frozen_hashes.json` (21 artifacts) |
| Control Center | `ridebase-control-center/template.html` → `build.py` → `RideBase_Control_Center.html` |
| backend routes | `ridebase-v1-dashboard/backend/app/routes.py` (+ `v2_1_routes.py` pattern) |

## Verification of the brief's claimed V3 state

The brief supplied approximate figures and instructed not to trust them. Each was
checked against the actual artifacts:

| claim | actual | verdict |
|---|---|---|
| champion CatBoost Binary Relevance | `catboost`, binary relevance | correct |
| 44 labels | 44 | correct |
| 277 PIT-safe features | 277 | correct |
| v1.4 world / V2.1 landmark grid reused read-only | `v1_4`, `random_one` | correct |
| TEST Micro F1 ~0.519 | 0.5192 | correct |
| TEST Micro PR-AUC ~0.561 | 0.5611 | correct |
| TEST mAP ~0.133 | 0.1330 | correct |
| TEST P@1 ~0.801 | 0.8014 | correct |
| unseen-motorcycle P@1 ~0.804 | 0.8035 | correct |
| ~15/44 labels weak or unlearnable | 15 `HIDDEN_BY_DEFAULT` (Phase-9 class E) | correct |
| global threshold ~0.31 | global, 0.31 | correct |
| V2.1 frozen and untouched | 21/21 hashes match | correct |
| Maintenance Urgency untouched | `policy/urgency.py` hash matches | correct |

Every figure in the brief verified. No correction was needed.
