# Phase 8 — Frontend Regression Check

**Verification method — stated explicitly**: this was HTTP + static-content
inspection only (`curl` + text/JSON parsing of the served HTML and its
embedded `window.__MANIFEST__`). No headless/real browser was used, so JS
execution, DOM rendering, and interactive click-flows were **not**
observed directly — conclusions about runtime behavior below are inferred
from reading the shipped JS source and from the separate live API probes in
Phases 6/7, not from watching the page run.

Production URL: `https://ridebase-ml-control-center.vercel.app` — `200 OK`,
byte-identical to the copy fetched and verified earlier this session (same
content as commit `4b84aac`, confirmed unchanged, no accidental new deploy).

| Check | Result | Basis |
|---|---|---|
| V2.1 primary | ✅ | literal string "V2.1 primary (müşteri servis dönüşü) · V2.0 legacy research" present |
| V2.0 legacy/research only | ✅ | same string; registry row `status: "failed"` |
| Maintenance Urgency card present | ✅ | `maintenance_urgency_score`/urgency copy present (9 occurrences) |
| Deterministic-vs-ML microcopy present | ✅ | `v2CalculateUrgency`'s "Fallback only; backend urgency fields are canonical" + urgency card explicitly separate from V2.1 risk card (per Phase 1 code read) |
| No mechanical failure-risk wording | ✅ | only "arıza" occurrences are disclaimers ("tarihsel ... arızalar ... uydurulmaz" = explicitly *not* fabricated), none present V2.1/urgency output as a breakdown probability |
| No real-fleet-validation claim | ✅ | "real_fleet_validation": "PENDING" baked into manifest; SYNTHETICALLY_VALIDATED wording throughout |
| Sample workflow works after backend deploy | ⚠️ **not verified — cannot be, backend not deployed** | Phase 5/6 confirm `/sample` is still on old (broken) behavior live; the button will still surface the old error until the manual Render deploy happens |
| Backend health indicator correct | ✅ (as far as static content goes) | page's `wireStatusLive()`/`#liveHealthBox` code pings the real `/health`, which is genuinely healthy (Phase 6) — page code itself unchanged, correct |
| No stale old `/sample` error baked into the page | ✅ | 0 occurrences of "modeling table not available" in the static HTML — that string only ever appears at runtime, from the live API response, not hardcoded |
| No NaN/undefined in rendered payload | ✅ | 0 occurrences of literal `NaN` or `undefined` anywhere in the page |
| Charts/registry correct | ✅ | registry: V0 BASELINE, V1 FROZEN×2, V2.0 `failed`, V2.1 `active`, V3 `PLANNED` — matches Phase 1's read of `models_block()`, no fabricated rows |

## Conclusion

Everything that can be true of a **static** page is true and unchanged since
this session's earlier deploy — this was a no-op verification (nothing
redeployed the frontend since, nothing needed to). The one item that
requires the backend redeploy (live `/sample` workflow actually returning
data end-to-end) is correctly reported as not-yet-true, matching Phase 6's
finding — not glossed over.
