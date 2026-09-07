# V3 Phase 19 — Security and Resource Hardening

Data: [`19_performance_security.json`](19_performance_security.json).

## Artifact loading

| check | result |
|---|---|
| artifacts load once at startup | **yes** — `init_v3()` in the app startup hook |
| model reloaded per request | **no** — same object identity across 30 requests |
| V3 predictor load time | 343.6 ms |
| full stack cold start | 2.13 s |

## Latency

| stage | value |
|---|---|
| `by-motorcycle` p50 | **58.9 ms** |
| `by-motorcycle` p95 | 65.8 ms |
| range over 30 calls | 58.2–67.4 ms |
| of which history build | 32.12 ms |
| of which inference | 23.99 ms |

Latency is dominated by rebuilding 277 features from history (~32 ms), not by the
44 CatBoost models (~24 ms).

## Memory

| stage | RSS |
|---|---|
| baseline (interpreter) | 11.5 MB |
| after full startup (V1 + V2.0 + V2.1 + V3) | 392.9 MB |
| after first V3 request | 419.7 MB |
| after 30 V3 requests | 420.0 MB |
| **growth across 30 requests** | **0.3 MB** |
| Render free plan limit | 512 MB |

**No leak:** 0.3 MB across 30 predictions. Steady-state peak is
420.0 MB against a 512 MB limit — about
18% headroom.

This headroom exists because of a fix made during productization: the V3 serving
path was eagerly loading all ten v1.4 source tables (**385 MB**), when it needs four
small reference tables and takes per-motorcycle history from the V2.1 SQLite store.
Table loading is now lazy per table, which cut V3's own footprint from 473 MB to
113 MB. `services.csv` and `service_tasks.csv` are deliberately not shipped in the
container at all.

The margin is real but not generous, and this service has been OOM-killed before.
**`V3_ENABLED=false`** remains a no-code-change kill switch: `/api/v3/*` degrades to
503 while V1 / V2.0 / V2.1 keep serving. Upgrading the Render plan is the durable fix.

## Request validation and error handling

| probe | status | expected |
|---|---|---|
| batch over the 100-row limit | 422 | 422 — rejected by schema before the handler allocates |
| empty feature row on `/predict` | 422 | 422 — never filled in from a sample |
| unknown `motorcycle_id` | 404 | 404 |
| landmark before observation window | 422 | 422 |
| `/predict/scenario` | 404 | 404 — deliberately not implemented |
| error body contains a stack trace | **False** | must be false |

**No failure path returns a fabricated prediction.**

## Attack surface

| risk | status |
|---|---|
| request-controlled artifact path | **none** — `_MODEL_DIR` is a module constant derived from `settings.MODEL_DIR` |
| path traversal via request field | **none** — no request field reaches a filesystem path |
| pickle / model upload endpoint | **none** — V3 adds no upload route |
| arbitrary code via input | **none** — inputs are validated pydantic scalars, never evaluated |
| unbounded batch memory | **bounded** at 100 rows, enforced in schema *and* handler |
| debug stack traces to client | **none** — the global handler returns `{"detail": "internal error"}` |
| secret exposure | **none** — no V3 route reads or echoes `RIDEBASE_ADMIN_TOKEN` |

## Unaffected existing behaviour

- `POST /admin/reload` bearer-token auth is untouched; V3 added no admin route and
  no bypass. The token is never printed by any V3 code path.
- `/docs`, `/redoc` and `/openapi.json` remain disabled when `APP_ENV=production`.
- CORS configuration is unchanged; V3 routes inherit the existing allow-list.
- V1, V2.0 and V2.1 routes are untouched, and remain functional when V3 is disabled
  or fails to load.
