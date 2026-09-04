# RideBase Production Reconciliation Completion Report

Date: 2026-09-04

## 1. Git Ancestry

- Current HEAD: `4b84aac19b9eb0add20973348b145de75497af0b`
- `origin/main`: `4b84aac19b9eb0add20973348b145de75497af0b` (== HEAD, confirmed after `git fetch`)
- `7272fa6` ancestor? **YES**
- `b3467eb` ancestor? **YES**
- Equivalent functionality verified? **YES** (also true by direct ancestry — not a squash/rebase case; verified in code too: `maintenance_urgency_score/level/reason`, `determining_dimension`, `progress_ratio` all present, backend-first with documented fallback, canonical calc has the ≥5× saturation rule)
- Reconciliation required? **NO**

Detail: [git_ancestry_reconciliation_audit.md](git_ancestry_reconciliation_audit.md)

## 2. Frozen V2.1 Safety

| Artifact | SHA256 (before + after full regression) |
|---|---|
| `champion_model.joblib` | `52f7b64a040745342860915e42ddc2774357ef444b306ad9c1881a4c809d8def` |
| `calibrator.joblib` | `02f9d5955d922621eca65920aa0abd7fbd8a250f174c122e460aa6a61b350945` |
| `feature_list.json` | `aa8164987383bd2e1acb95456d735eae0586ae5ca9e8d73154a09892047a876a` |
| `v2_1_history_serving.sqlite` | `a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657` |

Identical before and after Phase 9's full regression run, and identical to
what the live (pre-redeploy) production API itself reports.
- Retraining: **NO**
- Probability mutation: **NO**

Detail: [frozen_v2_1_safety_check.md](frozen_v2_1_safety_check.md)

## 3. Backend Deploy

- Target commit: `4b84aac` (origin/main, no reconciliation needed)
- Render deploy ID: **none — no deploy was triggered**
- READY status: **not applicable, nothing deployed**
- Env var configured: **NO** — `RIDEBASE_ADMIN_TOKEN` not set (no Render access from this environment; never generated/printed a token)
- `autoDeploy` status: **false** (confirmed in `render.yaml:20`)

**Blocker**: no `render` CLI, no `RENDER_API_KEY` in this environment.
Manual action required (Render Dashboard → `ridebase-inference-api` →
Manual Deploy → latest commit on `main`, plus adding `RIDEBASE_ADMIN_TOKEN`
under Environment).

Detail: [render_backend_deploy_audit.md](render_backend_deploy_audit.md), [render_admin_token_check.md](render_admin_token_check.md)

## 4. Live Backend Verification

| Check | HTTP | Result |
|---|---|---|
| `/health` | 200 | OK — V2.1 `xgb_cox`/isotonic/SQLite loaded, synthetic/pending wording correct |
| `/api/v2_1/sample` | 404 | Still old behavior — K2 fix not deployed |
| `/docs` | 200 | Should be gated in prod — O2 fix not deployed |
| `/admin/reload` no token | 403 `"reload disabled in production"` | Old guard, not the new bearer-token check — K3 fix not deployed |
| `/admin/reload` bogus token | 403, same message | Same — token isn't read yet |
| `/api/v2_1/model/info` | 200 | OK |
| `/api/v2_1/metrics` | 200 | OK, golden parity PASS live |
| `/api/v2_1/predict/scenario` | 200 | OK, monotonic |
| `/api/v2_1/predict/by-motorcycle` | 200 | OK — the previously-blocking OOM bug is confirmed resolved live |
| CORS (Vercel origin) | 200 | Allowed correctly |

Detail: [live_backend_postdeploy_verification.md](live_backend_postdeploy_verification.md)

## 5. True Extreme Overdue Case

- Interval (real, live-resolved): **3,000 km** / 182.62 days (RideBase TR operational policy, `ENGINE_OIL_CHANGE`) — not the 5,000 km figure the previous audit mistakenly used
- Current odo: 40,000 km / Last service odo: 10,000 km
- Km since service: 30,000 km / Overdue km: 27,000 km
- Ratio: **10.0×**
- Maintenance due: **true** (`status: OVERDUE`)
- Urgency score/level: **100 / KRİTİK** (correctly saturated — ratio exceeds the code's ≥5× threshold)
- V2.1 P30/P60/P90/P120: **0.358 / 0.703 / 0.819 / 0.888** — monotonic, no exact-zero, deterministic on repeat
- Warnings: 33/54 features imputed (partial-scenario input, expected)
- Semantic separation: urgency pinned at 100 while V2.1's own P30 sits at 36% — no synchronization between the deterministic and ML systems

Detail: [true_extreme_overdue_regression.md](true_extreme_overdue_regression.md) / [.json](true_extreme_overdue_regression.json)

## 6. Frontend Regression

- Production URL: `https://ridebase-ml-control-center.vercel.app` — 200, byte-identical to the previously-verified `4b84aac` build
- Backend connectivity: page code correctly pings the real `/health` (verified by reading the shipped JS, not by running a browser)
- Sample flow: **not verified working** — will still show the old error until the backend redeploy happens (honestly reported, not glossed over)
- Urgency UI: present, backend-first with documented fallback
- V2.1 primary / V2.0 legacy: confirmed via literal copy string and registry `status` fields
- Wording: no mechanical failure/breakdown claims, no real-fleet-validation claim, zero `NaN`/`undefined`

Note: verification method was HTTP + static-content inspection only, not a
real browser — stated explicitly, not implied otherwise.

Detail: [frontend_regression_check.md](frontend_regression_check.md)

## 7. Tests

| Suite | Passed | Failed | Result |
|---|---|---|---|
| `ridebase-v1-dashboard/backend` pytest | 106 | 0 | ✅ |
| backend E2E smoke (`smoke_e2e.py --inproc`) | 14/14 | 0 | ✅ |
| `ridebase-ml` pytest (full, incl. urgency + saturation test) | 120 | 0 | ✅ |
| `ridebase-control-center` pytest | 94 | 0 | ✅ |
| manifest-vs-live-health gate | — | — | ✅ PASS (live, real comparison this run — backend was warm) |
| `test_maintenance_urgency_api.py` (backend) | 7 | 0 | ✅ |
| `test_maintenance_urgency.py` (ridebase-ml, incl. `test_saturation_at_extreme_overdue`) | 6 | 0 | ✅ |

No frontend Next.js suite run — that app (`ridebase-v1-dashboard/frontend`)
was untouched by every commit in scope, matching the CI workflow's own path
filters.

## 8. Git Final State

- No code changes were required this run (ancestry, hashes, and behavior
  were all already correct) — a rebuild-only timestamp diff
  (`manifest.json`'s `generated_at`) was discarded rather than committed, per
  "no pointless commit."
- Final HEAD: `4b84aac19b9eb0add20973348b145de75497af0b`
- `origin/main`: same — in sync
- Working tree: clean of code changes; only this `reports/` directory's new
  audit files are untracked, to be committed as documentation

## 9. Next Step

Gates:
- Ancestry safe: ✅
- Backend latest commit live: ❌ **NOT live** — manual Render deploy pending
- `/sample` fixed live: ❌ pending the same deploy
- Docs gating live: ❌ pending the same deploy
- New admin auth live: ❌ pending the same deploy + env var
- True overdue audit passes: ✅
- Frozen V2.1 unchanged: ✅

**Blocker, exact and singular**: the K1/K2/K3/O2/O9 backend fixes are
code-complete, fully tested (106+14+120+94+7+6 = 347 passing checks), and
already pushed to `origin/main` — but Render has not deployed them
(`autoDeploy: false`, no CLI/API access from this environment). Everything
else this task's gates ask for is already true. Do **not** start the
overnight real-data readiness work until:

```
Render Dashboard → ridebase-inference-api → Manual Deploy → main (4b84aac)
Render Dashboard → ridebase-inference-api → Environment → add RIDEBASE_ADMIN_TOKEN
```

then re-run Phase 6's probe set to confirm the flip (`/sample` 200,
`/docs` gated, `/admin/reload` giving the new 401 contract).

## FINAL VERDICT

**PRODUCTION RECONCILIATION PARTIAL — MANUAL RENDER ACTION STILL REQUIRED**
