# Phase 6 — Live Backend Verification

No deploy occurred (Phase 5 stopped on missing tooling), so this is a
**current-state** live audit, not post-deploy — its purpose here is to prove
exactly what's still on the old commit vs what already works, so Phase 10's
gate can be judged honestly.

| Check | HTTP | Result |
|---|---|---|
| `GET /health` | 200 | V2.1 loaded, `xgb_cox` champion, isotonic calibration, `SYNTHETIC_V1_4`/`SQLITE` history adapter loaded, `SYNTHETICALLY_VALIDATED` / `PENDING` wording correct |
| `GET /api/v2_1/sample` | **404** | `{"detail":"V2.1 modeling table not available for a sample"}` — **unchanged from before, confirms K2 fix NOT deployed** |
| `GET /docs` | **200** | Should be gated in prod per the new `main.py` — **confirms O2 fix NOT deployed** |
| `POST /admin/reload` no token | 403 `"reload disabled in production"` | Old `APP_ENV`-based guard, not the new bearer-token check (which would say `"unauthorized"`, 401) — **confirms K3 fix NOT deployed** |
| `POST /admin/reload` bogus Bearer token | 403, same message | Same old guard — token isn't even being read yet |
| `POST /admin/reload` with valid token | not tested | No token exists yet (Phase 4 manual step not done) — correctly skipped, nothing to test |
| `GET /api/v2_1/model/info` | 200 | OK |
| `GET /api/v2_1/features` | 200 | OK |
| `GET /api/v2_1/metrics` | 200 | OK, golden parity PASS |
| `POST /api/v2_1/predict/scenario` | 200 | OK, monotonic prediction |
| `POST /api/v2_1/predict/by-motorcycle` | 200 | OK (known id `MC000001`) |
| CORS (`Origin: ridebase-ml-control-center.vercel.app`) | 200 | `access-control-allow-origin` echoes the origin correctly |

## Conclusion

Backend is healthy and every **pre-existing** route works correctly. The
three fixes that specifically require this session's commit (`/sample` K2,
`/docs` gating O2, bearer-token admin auth K3) are demonstrably still on old
behavior — this is not a new regression, it's live proof the Phase 5 manual
Render deploy has not happened yet. Re-run this same probe set after the
manual deploy to confirm the flip.
