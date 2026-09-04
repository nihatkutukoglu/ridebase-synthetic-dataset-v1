# Maintenance Urgency Production Hardening — Preflight

- Preflight timestamp (UTC): `2026-09-04T15:38:00Z`
- Branch: `main`
- HEAD: `7272fa6` (`Deploy maintenance urgency Control Center update`)
- Expected HEAD: `7272fa6` — **MATCH**
- `origin/main...HEAD`: `0 0` — **IN SYNC**
- Initial working tree: **CLEAN**
- V2.1 retraining: **NOT RUN**

## Frozen V2.1 artifact hashes

| Artifact | SHA-256 |
|---|---|
| `ridebase-ml/models/v2_1_v1_4/champion_model.joblib` | `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def` |
| `ridebase-ml/models/v2_1_v1_4/calibrator.joblib` | `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945` |
| `ridebase-ml/models/v2_1_v1_4/feature_list.json` | `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a` |
| `ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite` | `a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657` |

## Baseline gates

| Surface | Command | Result |
|---|---|---|
| ridebase-ml | `python3 -m pytest -q` | **PASS — 119 tests** (one existing XGBoost serialization warning) |
| Backend | `python3 -m pytest -q` | **PASS — 85 tests** |
| Control Center | `python3 -m unittest discover -s tests -v` | **PASS — 27 tests** |
| Legacy Next.js frontend | `npm run test -- --run` | **PASS — 5 tests** |
| Legacy Next.js frontend | `npm run typecheck` | **PASS** |
| Legacy Next.js frontend | `npm run build` | **PASS** |

The baseline was completed before implementation changes. No model training, calibration, or prediction artifact command was run.
