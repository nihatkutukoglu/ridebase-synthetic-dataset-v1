# V3 Phase 1 — Production Freeze Inventory

Recorded before any V3 work. These hashes are re-verified in Phase 30; any
difference is a stop condition.

- Frozen at HEAD: `b25f3b7b1f870c995b1e133a76230537d83d7365`
- Branch: `main`
- Interpreter: `/usr/bin/python3 (3.9.6)`
- Machine-readable copy: `reports/v3/01_frozen_hashes.json`

## Frozen artifacts

| Path | SHA256 | Bytes |
|---|---|---|
| `ridebase-ml/models/v2_1_v1_4/champion_model.joblib` | `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def` | 543550 |
| `ridebase-ml/models/v2_1_v1_4/calibrator.joblib` | `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945` | 7315 |
| `ridebase-ml/models/v2_1_v1_4/preprocessor.joblib` | `6b24e0ebc027f52bebb52841ec551cadb14b63bf2f540687a69ee0445ec9f990` | 12111 |
| `ridebase-ml/models/v2_1_v1_4/baseline_hazard.joblib` | `70d87de08a6b44146a115134ddbd1e68b3972c5f5d5e94b9e7d4cebd732d2dc0` | 12298 |
| `ridebase-ml/models/v2_1_v1_4/feature_list.json` | `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a` | 1354 |
| `ridebase-ml/models/v2_1_v1_4/artifact_manifest.json` | `b1c6dbb5dcdf0dfb57430259486a5e22d2bf22924ac0f057287411563fb2a1b8` | 954 |
| `ridebase-ml/models/v2_1_v1_4/data_freeze_manifest.json` | `28eb9a183e796e55833bc5043d79e37dbbeeb5a8fcda359b5b83cf96f2a43c78` | 1925 |
| `ridebase-ml/models/v2_1_v1_4/metrics.json` | `0ff23e697eb12dc4f670914da2ae6caa49a5039d49ebf501bebf5509b4ba462c` | 27136 |
| `ridebase-ml/models/v2_1_v1_4/frozen_test_predictions.parquet` | `696a90bfceea87c7a52bb26b7c006ea33c42cb37dd65ca403a8d9dddf368047a` | 887579 |
| `ridebase-ml/models/v2_1_v1_4/selection_before_test.json` | `d123e3ab045a6b95046af1b1b26d4c160a239551f20b1c0ad0d0bd63997e7942` | 287 |
| `ridebase-ml/models/v2_1_v1_4/test_first_touch.json` | `c8a9203b80239f42d51fb927a889bdb5336acd54672fbfd7f60583b3c9e6272f` | 204 |
| `ridebase-ml/models/v2_1_v1_4/golden_parity.json` | `bb0cc3e31e7fe9b777c953b55153b4a9569505870d0a9565751373aeb3ab71da` | 269 |
| `ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet` | `427e9e1fd321977f95c65c581df719c779747d0b8026aacefe0a4abb5fecdcc4` | 13347698 |
| `ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite` | `a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657` | 69570560 |
| `ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_store_manifest.json` | `950ef47221ab89f934580cdfc600f1dd6a428b25a055d90fe8641708eeb671f5` | 7037 |
| `ridebase-ml/ridebase_ml/v2_1/predictor.py` | `5a1881b19b6ca935ae3aa2e5193eab94d868ad463f73cb26d97401e846b2bada` | 10497 |
| `ridebase-ml/ridebase_ml/v2_1/landmarks.py` | `32e52556e018e348ea0a71bb5890df513dd1664827b1de2e5a603bf247d221de` | 31971 |
| `ridebase-ml/ridebase_ml/v2_1/survival.py` | `d670f88c9c2234dde7bad5325697713209d381262a599713acb1896014537d1b` | 2851 |
| `ridebase-ml/ridebase_ml/policy/urgency.py` | `7e11476156d0a55544f326867f6089b0432debe33110b6bd472f173cdb7cfbcf` | 4477 |
| `docs/v2_1_feature_contract.md` | `e51cfea345fff1eee059e4b5331537bb92eb1c7990e4a44a2eab8ac3256ac161` | 1989 |
| `docs/maintenance_urgency_score.md` | `dba1ed90dc4a85b7126cfd9119bd8adbad118a0c951d8dc47ba9fd294f2f2c16` | 6318 |

## What each frozen item is

- **`champion_model.joblib`** — V2.1 champion, XGBoost `survival:cox` regressor.
- **`calibrator.joblib`** — per-horizon isotonic calibration for 30/60/90/120d.
- **`baseline_hazard.joblib`** — persisted Breslow baseline cumulative hazard.
- **`preprocessor.joblib`** — TRAIN-fit transformer for the 54-column contract.
- **`feature_list.json` / `data_freeze_manifest.json`** — the V2.1 feature contract.
- **`v2_1_history_serving.sqlite`** — the history serving store used by
  `/api/v2_1/predict/by-motorcycle`.
- **`v2_1_modeling_table.parquet`** — the V2.1 landmark modeling table. V3 reads
  it **read-only** as its landmark and base-feature source.
- **`policy/urgency.py`** — deterministic Maintenance Urgency implementation.

## Cross-check

`v2_1_modeling_table.parquet` hashes to
`427e9e1fd321977f95c65c581df719c779747d0b8026aacefe0a4abb5fecdcc4`, which equals
`modeling_table_sha256` recorded inside the V2.1 `data_freeze_manifest.json`. The
production data freeze is internally consistent at session start.

## Maintenance Urgency version

`ridebase-ml/ridebase_ml/policy/urgency.py` last touched by:

```
8b58c2ed84df4869d02c3c5cd2f1afccfc8cca56 2026-09-04 14:56:46 +0300
```

No V3 phase writes to this file, to `ridebase_ml/v2_1/`, to `models/v2_1_v1_4/`,
or to `derived_outputs/v2_1_v1_4/`.
