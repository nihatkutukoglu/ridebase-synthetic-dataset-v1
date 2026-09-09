# Render Port-Bind Investigation — `fc9fc6f`

Investigation of why the `fc9fc6f` deploy did not open a port on Render, run
locally and in a staged container environment. **No model was retrained and no
model artifact was changed** (`ridebase-ml/` untouched, V3 11/11 and V2.1 21/21
hashes identical).

## 1. What was deployed

| item | value |
|---|---|
| `fc9fc6f` | `docs(v3): record deployment verification addendum` — **docs only** |
| code it carries | `a14d8f9` (`feat(v3): add PIT-safe motorcycle context UX`) |
| last known-good live build | `a397ca6` |
| code diff `a397ca6 → fc9fc6f` | `Dockerfile.prod` (+1 ENV line), `app/v3_context.py` (new), `v3_routes.py`, `v3_schemas.py`, `v3_service.py`, tests |

**Live service state during this investigation:** `GET /health` returns 200, but
`GET /api/v3/sample` has **no `motorcycle_context`** — the instance still runs
`a397ca6`. The new deploy never took over.

## 2. The mechanism: startup blocks the socket bind

Render's start command is `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`.

Read from the installed uvicorn, `Server.startup()`:

```
  0: async def startup(self, sockets=None) -> None:
  1:     await self.lifespan.startup()          # <-- @app.on_event("startup")
 40:     server = await loop.create_server(...)  # <-- the socket bind
```

`lifespan.startup()` completes **before** `create_server()`. Every second spent
loading models in the startup hook is a second with **no listening port**, and a
platform waiting to detect a port sees nothing at all.

### Measured, before the fix

| stage | time | note |
|---|---|---|
| import `app.main` | 0.82–1.39 s | before anything else |
| startup: V1 artifact store | 2.11 s | dominant cost |
| startup: V2.0 bundle | 0.12 s | |
| startup: V2.1 predictor + history | 0.02 s | |
| startup: V3 CatBoost (44 models) | 0.38 s | |
| **time to first TCP connect on `$PORT`** | **3.24–3.54 s** | warm cache, fast local disk |

Peak RSS at end of startup: **387 MB** against Render free's 512 MB.

### A second coupling: `/health` forced the load itself

`health()` called `v3_health_fields()` → `v3_loaded()` → **`init_v3()`**. The first
health probe therefore paid the full 44-model CatBoost load *on the request path* —
precisely when the platform is waiting for the service to answer. `get_store()` in
both `/health` and the request-logging middleware could likewise block on the
artifact lock.

## 3. Answering the specific hypothesis: does the new enrichment load datasets at import/startup?

**No.** Instrumented `ridebase_ml.v3.sources.load_table` and counted calls:

| phase | source-table loads |
|---|---|
| module import of `app.main` | **0** |
| startup warmup | **1** — `maintenance_tasks` (98 rows, 17 KB), from the frozen V3 predictor's taxonomy |
| a real context request | 2 — `motorcycles` (3.2 MB) + model master, lazily and then cached |

`v3_context.py` imports only stdlib, pandas and the schema module; every
`load_table` call sits inside a request-path function. The motorcycle-context
enrichment is **not** loading source or history data at import or startup, and it
runs strictly after the frozen predictor call.

## 4. What could not be reproduced

**The port opened in every configuration I could build locally**, in 3.24–3.54 s:

- plain `uvicorn app.main:app` with `PORT=10000`
- a staged container filesystem replicating every Dockerfile `COPY` and the exact
  Dockerfile `ENV` set, with only the four small v1.4 CSVs present

Also ruled out: import-time failure (imports cleanly on Python 3.9 **and** 3.11),
pydantic incompatibility (`pydantic>=2.6` satisfies `ConfigDict`), and missing build
inputs (all 18 `COPY` sources are tracked in git).

**No Docker daemon and no Render build/runtime logs were available here**, so the
exact Render-side failure is *not* proven. What follows are defects that were
proven locally and that each independently make a deploy fail to be seen as up.

## 5. Defects found and fixed

| # | Defect | Why it matters |
|---|---|---|
| 1 | All model loading ran synchronously in the lifespan startup hook | Blocks `create_server()`; the port cannot open until every model is loaded |
| 2 | `/health` triggered `init_v3()` on first probe | The health check itself waited on the 44-model bundle |
| 3 | `/health` and the request-log middleware blocked on the V1 artifact lock | A probe stalls behind whatever is loading |
| 4 | `HEALTHCHECK CMD curl … http://localhost:8000/health` hard-coded | Render sets `PORT=10000`; the container healthcheck **can never pass** |
| 5 | `RIDEBASE_V3_LABEL_POLICY` missing from Dockerfile `ENV` | In the image the package sits at `/opt/ridebase_ml/…` and the policy at `/app/config/…`; the parent-walk cannot bridge that, so `/api/v3/labels` depended entirely on a dashboard env var |
| 6 | No `.dockerignore` | The build context is the whole repo, including multi-GB dataset snapshots and zips that no `COPY` reads |

### The fix

- **`app/main.py`** — startup starts a daemon warmup thread and returns immediately.
  Each service keeps its own lazy init, so a request arriving mid-warmup still
  works; `get_store` and the `init_*` helpers are lock-guarded, so the warmup thread
  and an early request cannot double-load.
- **`app/v3_service.py`** — new `v3_ready()`; `health_fields()` *observes* readiness
  and never forces a load, reporting `v3_status: loading` while warming.
- **`app/artifacts.py`** — new `store_ready()`, a lock-free readiness peek.
- **`app/routes.py`** — `/health` reports `status: warming`, `v1: loading` instead of
  blocking on the store.
- **`Dockerfile.prod`** — healthcheck probes `${PORT:-8000}`; `start-period` 40 s → 90 s;
  `RIDEBASE_V3_LABEL_POLICY` added to `ENV`.
- **`.dockerignore`** — added. Verified against every `COPY`: **0 of 18 sources
  blocked**.
- **`tests/conftest.py`** — bounded wait for warmup so tests assert the warmed state
  deterministically instead of racing it.

### Measured, after the fix

| metric | before | after |
|---|---|---|
| time to first TCP connect | 3.24 s | **0.90 s** |
| what still blocks the bind | import + all model loading | module import only |
| `/health` during warmup | would trigger the V3 load | answers in ms with `status: warming`, `v3_status: loading` |
| `/health` once warm | `ok` | `ok` (2–12 ms) |

Health transition observed live in the container sim:

```
t=0.90s  port open
t=2.38s  /health  status=warming  v1=loading  v2_1=ok  v3=loading
t=2.84s  /health  status=ok       v1=ok       v2_1=ok  v3=loading
t=3.31s  /health  status=ok       v1=ok       v2_1=ok  v3=ok
```

## 6. Regression

| Suite | Passed | Failed |
|---|---|---|
| `ridebase-v1-dashboard/backend/tests` | 143 | 0 |
| `ridebase-ml/tests` | 203 | 0 |
| `ridebase-control-center/tests` | 115 | 0 |
| **total** | **461** | **0** |

Backend suite run 3× consecutively with no flakiness from the background warmup.

| safety check | result |
|---|---|
| V3 frozen hashes | 11/11 identical |
| V2.1 + Maintenance Urgency hashes | 21/21 identical |
| files changed under `ridebase-ml/` | **0** |
| retraining | **NO** |
| V3 probabilities | untouched — no serving code changed |

## 7. Honest status

Defect #1 is the one that matches the reported symptom directly: with all model
loading inside the lifespan hook, a slow cold instance has no open port for as long
as loading takes. Defect #4 would independently keep the container from ever being
marked healthy. Both are now fixed, and the port opens ~3.6× sooner while `/health`
no longer depends on any heavy V3 loading.

I did not observe the Render failure itself, so this is not presented as a
confirmed single root cause. If the next deploy still fails, the Render build and
runtime logs are the missing evidence, and the `status: warming` field now makes it
possible to tell "still loading" apart from "failed to start".
