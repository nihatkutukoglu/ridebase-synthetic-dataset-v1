# V3 Productization Phase 1 — Frozen V3 Product Inputs

Recorded before any productization work. Re-verified in Phase 26; any difference is
a stop condition.

Machine-readable: [`01_v3_frozen_hashes.json`](01_v3_frozen_hashes.json).
Frozen at HEAD `43d2ba3d0ca564eae1e7cf96fc377039e16b267d`.

## Model identity

| item | value |
|---|---|
| model_version | `v3.0-research` |
| status | `RESEARCH_OFFLINE_SYNTHETIC_ONLY` |
| deployed | `False` |
| champion family | `catboost` (binary relevance, one classifier per label) |
| source world | `v1_4` |
| landmark strategy | `random_one` |
| seed | `20260907` |
| label count | 44 |
| feature count | 277 |
| threshold policy | `global` @ 0.31 |
| calibration | {'none': 28, 'isotonic': 14, 'sigmoid': 2} |
| train-fit / calibration rows | 22,552 / 5,639 |
| real fleet validation | `PENDING` |

## Frozen artifacts

| path | SHA256 | bytes |
|---|---|---|
| `ridebase-ml/models/v3_research/champion_model.joblib` | `2a1f0103c32a10bfcf56b6f7fd7073fa9d49eac3b718df519378c0ebfbc16eb1` | 15,986,675 |
| `ridebase-ml/models/v3_research/calibrator.joblib` | `f64c9dab5d2886645f7c80fe2c01d192d58abead376625c20115dc2ff5347bb4` | 18,206 |
| `ridebase-ml/models/v3_research/feature_list.json` | `9566bf2439a3876c8569e359461c8dc07f7883d486a2af7729b60c00184955ec` | 10,639 |
| `ridebase-ml/models/v3_research/label_list.json` | `f1bd6d5c70d0776fbf76b1273510d411e54e6a0d015e526e4ec498c62e5d1e56` | 3,029 |
| `ridebase-ml/models/v3_research/thresholds.json` | `12415d4f67cf62d9810aaaa0aecb42b5546ff4ce4fac39f15fb3e406e22ff550` | 3,501 |
| `ridebase-ml/models/v3_research/artifact_manifest.json` | `182d5ac7f4da9fe8fa8331a0aa337ce98b5655ea53b8e9463116a75584c3e193` | 1,635 |
| `ridebase-ml/models/v3_research/selection_before_test.json` | `74735ab53e4d37ac9c1f0bb2955863b20cb51d526bcd4731308ea5f58437d740` | 1,656 |
| `ridebase-ml/models/v3_research/calibration_report.json` | `8c92418ee0b68aa334951c174dff9bd34517e81e238cddf39cc6cdf94f3f8234` | 51,344 |
| `ridebase-ml/models/v3_research/test_evaluation.json` | `bb0fdb031e66eba145d0b43c968bf52f5ad3f6be2570fa5db76f42828f9c8f4b` | 8,640 |
| `config/v3_label_set.json` | `ab89e0099c0f0a2f21f28e8e0142ce46799a4e628a2032a9e176f8420b46e08c` | 7,715 |
| `config/v3_target_contract.json` | `4bb810a9fe93654310d50487a740c968bdf8352ac8f02870a5ee411e624748d6` | 3,902 |

## Frozen synthetic TEST metrics

| metric | TEST | unseen-motorcycle TEST |
|---|---|---|
| Micro F1 | 0.5192 | 0.4931 |
| Macro F1 | 0.1107 | 0.0958 |
| Micro PR-AUC | 0.5611 | 0.5442 |
| mAP | 0.1330 | 0.1282 |
| P@1 *(ranking, not accuracy)* | 0.8014 | 0.8035 |
| P@3 | 0.3994 | 0.3855 |
| R@3 | 0.6799 | 0.6967 |
| Hamming loss | 0.0575 | 0.0588 |

Unseen-motorcycle TEST rows: 871.

## Weak / unlearnable labels

15 of 44, all Phase-9 generating-process class E (random fault or inspection
finding). They are marked `HIDDEN_BY_DEFAULT` in the product policy and can never
reach a confidence above DÜŞÜK:

`FUEL_SYSTEM_DIAGNOSTIC`, `ENGINE_COMPRESSION_TEST`, `ABS_DIAGNOSTIC`, `ENGINE_FAULT_DIAGNOSTIC`, `WHEEL_BALANCE`, `THROTTLE_BODY_CLEAN`, `BRAKE_DISC_CHANGE`, `ECU_DIAGNOSTIC_SCAN`, `WHEEL_BEARING_CHANGE`, `VALVE_CLEARANCE_ADJUST`, `BRAKE_SYSTEM_BLEED`, `STEERING_BEARING_CHANGE`, `FORK_SEAL_CHANGE`, `FUEL_INJECTOR_CLEAN`, `BATTERY_CHANGE`

## What productization is allowed to touch

Nothing in `ridebase-ml/models/v3_research/`. The frozen champion, its calibrators
and its thresholds are consumed read-only. No retraining, no re-thresholding, no
re-calibration.
