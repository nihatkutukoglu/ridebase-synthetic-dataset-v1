# V3 Productization Phase 2 — V2.1 / Maintenance Urgency Safety

Re-verified against the hashes recorded before the V3 **research** session
(`reports/v3/01_frozen_hashes.json`, taken at HEAD `b25f3b7b1f870c995b1e133a76230537d83d7365`).

**RESULT: 21/21 artifacts identical. 0 mismatches.**

| artifact | SHA256 (recorded) | now |
|---|---|---|
| `ridebase-ml/models/v2_1_v1_4/champion_model.joblib` | `52f7b64a040745342860915e…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/calibrator.joblib` | `02f9d5955d922621eca65920…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/preprocessor.joblib` | `6b24e0ebc027f52bebb52841…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/baseline_hazard.joblib` | `70d87de08a6b44146a115134…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/feature_list.json` | `aa8164987383bd2e1acb9545…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/artifact_manifest.json` | `b1c6dbb5dcdf0dfb57430259…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/data_freeze_manifest.json` | `28eb9a183e796e55833bc504…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/metrics.json` | `0ff23e697eb12dc4f670914d…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/frozen_test_predictions.parquet` | `696a90bfceea87c7a52bb26b…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/selection_before_test.json` | `d123e3ab045a6b95046af1b1…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/test_first_touch.json` | `c8a9203b80239f42d51fb927…` | MATCH |
| `ridebase-ml/models/v2_1_v1_4/golden_parity.json` | `bb0cc3e31e7fe9b777c953b5…` | MATCH |
| `ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet` | `427e9e1fd321977f95c65c58…` | MATCH |
| `ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite` | `a057573c9c35b1155aacabb0…` | MATCH |
| `ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_store_manifest.json` | `950ef47221ab89f934580cdf…` | MATCH |
| `ridebase-ml/ridebase_ml/v2_1/predictor.py` | `5a1881b19b6ca935ae3aa2e5…` | MATCH |
| `ridebase-ml/ridebase_ml/v2_1/landmarks.py` | `32e52556e018e348ea0a71bb…` | MATCH |
| `ridebase-ml/ridebase_ml/v2_1/survival.py` | `d670f88c9c2234dde7bad532…` | MATCH |
| `ridebase-ml/ridebase_ml/policy/urgency.py` | `7e11476156d0a55544f32686…` | MATCH |
| `docs/v2_1_feature_contract.md` | `e51cfea345fff1eee059e4b5…` | MATCH |
| `docs/maintenance_urgency_score.md` | `dba1ed90dc4a85b7126cfd91…` | MATCH |

## What this proves

- The V2.1 champion, its calibrator, its Breslow baseline, its preprocessor and its
  feature contract are byte-identical. **V2.1 was not retrained and not mutated.**
- `ridebase_ml/v2_1/predictor.py`, `landmarks.py` and `survival.py` are unchanged.
- `ridebase_ml/policy/urgency.py` is unchanged — **Maintenance Urgency is untouched.**
- The V2.1 history serving SQLite store is unchanged. V3 *reads* it through the same
  read-only adapter and never writes to it.
- `docs/v2_1_feature_contract.md` and `docs/maintenance_urgency_score.md` unchanged.

## Code-level separation

```
git diff --name-only b25f3b7..HEAD -- ridebase-ml/ridebase_ml/v2_1 \
                                      ridebase-ml/ridebase_ml/policy \
                                      ridebase-ml/models/v2_1_v1_4 \
                                      ridebase-ml/derived_outputs/v2_1_v1_4
```
returns empty across the whole V3 research **and** productization work.

The V3 backend service imports V2.1's history adapter (`get_history_adapter`) and
nothing else. It never imports the V2.1 predictor, never reads a V2.1 probability,
and never writes to a V2.1 artifact path.

## Behavioural separation

- `/api/v2_1/*` responses contain no V3 field (asserted by
  `test_v2_1_routes_are_untouched`).
- `/api/v3/*` responses contain no urgency score and no V2.1 horizon probability
  (asserted by `test_response_never_carries_urgency_or_v2_1_scores`).
- Control Center: V2.1 and Maintenance Urgency copy is unchanged, asserted by
  `V3Module.test_v2_1_wording_is_unchanged` and
  `test_maintenance_urgency_wording_is_unchanged`.
- If V3 fails to load or is disabled, `/api/v3/*` returns 503 and V1 / V2.0 / V2.1
  keep serving — verified by `test_v3_can_be_disabled_without_affecting_other_surfaces`.
