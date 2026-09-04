# Phase 2 — Frozen V2.1 Safety Check

## SHA256 (local working tree, current HEAD 4b84aac)

| Artifact | SHA256 |
|---|---|
| `champion_model.joblib` | `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def` |
| `calibrator.joblib` | `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945` |
| `feature_list.json` | `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a` |
| `v2_1_history_serving.sqlite` | `a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657` |

`ridebase-ml/models/v2_1_v1_4/*` and the backend's bundled copy under
`ridebase-v1-dashboard/backend/artifacts/models/v2_1_v1_4/*` are byte-identical
(diffed directly). `git status --short` on all these paths is empty — no
local, uncommitted modification versus the last commit that touched them.

## Comparison against known-live values

The prior session's live audit (same day) captured these exact hashes from
the **currently-running** production backend:

- `GET /api/v2_1/model/info` → `artifact_manifest.champion_model.joblib` =
  `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def` — **MATCH**
- `artifact_manifest.calibrator.joblib` =
  `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945` — **MATCH**
- `artifact_manifest.feature_list.json` =
  `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a` — **MATCH**
- `GET /health` → `v2_1_history_store_hash` =
  `a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657` — **MATCH**

## Result

**No unexpected change.** Local artifacts, the backend's bundled copy, and
the hashes reported by the live (pre-redeploy) production API are all
identical. No retraining occurred, no calibrator/feature-contract edits, no
history-dataset mutation. This baseline is safe to carry into the Phase 5
backend redeploy — the redeploy only ships code changes (routes, config,
Dockerfile COPY lines for a *different*, previously-missing parquet file,
predictor median-interpolation logic), never these 4 artifacts.
