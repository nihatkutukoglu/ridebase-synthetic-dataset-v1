# Deployment

Two independently deployable services. Nothing here contains provider secrets —
set them in the platform's dashboard / CI secret store.

```
frontend (Next.js, static+SSR)  ──HTTPS──▶  backend (FastAPI + model artifacts)
```

---

## 1. Backend — any Python-container platform (Render / Railway / Fly.io / Cloud Run)

**Build:** `backend/Dockerfile` (python:3.11-slim, `libgomp1` for LightGBM/XGBoost).
**Start:** `uvicorn app.main:app --host 0.0.0.0 --port 8000` (in the image).
**Health check:** `GET /health` (already wired as a Docker `HEALTHCHECK`).

### Artifacts

The container needs the notebook artifacts at:

```
/artifacts/models      ← ridebase-ml/models        (V1 + V2 model bundles)
/artifacts/reports     ← ridebase-ml/reports        (V2 /metrics reads reports/tables/*)
/artifacts/outputs     ← ridebase-ml/outputs
/artifacts/dataset     ← ridebase_v1_3/derived_outputs   (only for the input-feature catalog)
/app/app/data/ridebase_motorcycle_models_v1.csv ← authoritative scenario model catalog
/app/app/data/maintenance_policies.csv ← frozen policy catalog for deterministic maintenance status
```

**V2 also needs the `ridebase_ml` inference package importable.** Either:
- `pip install -e ./ridebase-ml` in the image (adds `ridebase_ml.v2`, requires
  `scikit-survival==0.23.1` → pins `scikit-learn==1.5.2`; this is already in
  `backend/requirements.txt`), **or**
- copy `ridebase-ml/ridebase_ml/` to `/artifacts/ridebase_ml/` — `v2_service.py`
  auto-adds `MODEL_DIR.parent` to `sys.path`. Override with `RIDEBASE_ML_ROOT` if
  the package lives elsewhere.

If the package or the V2 bundle is missing the app still starts — `/api/v2/*`
returns 503 and `/health.v2_status` shows the reason; V1 is unaffected. Use
`backend/requirements-prod.txt` for an inference-only image (no notebook stack).

Pick one:

- **Bake them in** — add to `backend/Dockerfile` before `CMD`:
  ```dockerfile
  COPY --chown=root:root artifacts/ /artifacts/
  ```
  and copy `ridebase-ml/{models,reports,outputs}` + `ridebase_v1_3/derived_outputs`
  into `backend/artifacts/` in your build pipeline. Simplest for immutable deploys.
- **Mount a volume / object store** at `/artifacts` (Fly volumes, Cloud Run + GCS
  FUSE, Render disk). Lets you ship a new model without rebuilding — then call
  `POST /admin/reload`.

### Env

| var | value |
|-----|-------|
| `APP_ENV` | `production` (also hides `/docs`, `/redoc`, `/openapi.json`) |
| `RIDEBASE_ADMIN_TOKEN` | a generated secret (`openssl rand -hex 32`); required to call `POST /admin/reload` |
| `ALLOWED_ORIGINS` | `https://<your-frontend-domain>` (comma-separated, no trailing slash) |
| `MODEL_DIR` / `REPORTS_DIR` / `OUTPUTS_DIR` / `DATASET_DIR` | `/artifacts/models` … (image defaults already set) |
| `MODEL_CATALOG_PATH` | `/app/app/data/ridebase_motorcycle_models_v1.csv` (`Dockerfile.prod` copies it from v1.3 source tables) |
| `MAINTENANCE_POLICY_PATH` | `/app/app/data/maintenance_policies.csv` (`Dockerfile.prod` copies it from v1.3 source tables) |
| `MAX_REQUEST_BYTES` | `1000000` (raise only if you use `/predict/batch` heavily) |

### Render — one-file blueprint (recommended)

`ridebase-v1-dashboard/render.yaml` is a ready Render Blueprint (Docker, `/health`
check, `APP_ENV=production`, all `*_DIR` env vars). It builds
`backend/Dockerfile.prod` from the **repo root** so the `ridebase_ml` V2 package
goes in.

```bash
# 1. curate the ~50 MB inference artifact subset (skips 5 GB of AutoML experiments)
bash ridebase-v1-dashboard/scripts/collect_prod_artifacts.sh
#    -> ridebase-v1-dashboard/backend/artifacts/{models,reports,outputs,dataset}
# 2. commit backend/artifacts/  (or upload it to a Render Disk mounted at /artifacts
#    and comment out the `COPY ... /artifacts` line in Dockerfile.prod)
# 3. Render dashboard -> New -> Blueprint -> pick render.yaml
# 4. edit ALLOWED_ORIGINS to your exact Control Center origin(s)
```

Then point the Control Center at it: publish with `RIDEBASE_V2_API=https://<the-render-url>`
in the environment when running `ridebase-control-center/build.py`, **or** open the
published artifact with `?v2api=https://<the-render-url>`. No URL configured → the
Live Prediction screen stays offline and says so (no fake fallback).

The V2.1 dynamic-landmark model adds a **separate** route family
(`/api/v2_1/{model/info,features,metrics,sample,predict,predict/batch,predict/scenario}`)
— `/api/v2/*` and `/api/v1/*` are untouched. An existing Render service with
`autoDeploy: false` must be redeployed for these to appear:

1. `bash ridebase-v1-dashboard/scripts/collect_prod_artifacts.sh`
   — now also bundles `models/v2_1_v1_4/` (champion + preprocessor + calibrator +
   baseline hazard + `metrics.json` + `golden_parity.json`). No new pip deps:
   `requirements-prod.txt` already has `scikit-learn`, `xgboost`, `joblib`.
2. commit `backend/artifacts/` **or** upload `models/v2_1_v1_4/` to the Render
   Disk mounted at `/artifacts/models/`.
3. **Render → ridebase-inference-api → Manual Deploy → Deploy latest commit**
   (commit `4941069` or later).
4. verify: `GET /health` → `v2_1_model_loaded: true`;
   `GET /api/v2_1/model/info` → `champion: "xgb_cox"`.

Do not claim V2.1 is production-live until `/health.v2_1_model_loaded` is `true`
and `/api/v2_1/predict/scenario` returns monotone risks.

> **Backend deployment status: `BACKEND_DEPLOY_AUTH_BLOCKED`.** Triggering the
> Render deploy (or uploading to the Render Disk) needs the account owner — no
> Render CLI, API key or deploy hook is available in this environment, and
> `render.yaml` has `autoDeploy: false` so the GitHub push does not trigger it.
> Everything else is done: code pushed to `origin/main`, the Control Center
> frontend is deployed and verified on Vercel, artifacts stage cleanly, and the
> V2.1 route + scenario logic pass the full in-process behavioural audit.
> The single remaining manual action is step 3 above.

### Cloud Run (example)

### Cloud Run (example)

```bash
gcloud run deploy ridebase-v1-api \
  --source ridebase-v1-dashboard/backend \
  --region <r> --port 8000 --allow-unauthenticated \
  --set-env-vars APP_ENV=production,ALLOWED_ORIGINS=https://<frontend> \
  --add-volume name=art,type=cloud-storage,bucket=<bucket> \
  --add-volume-mount volume=art,mount-path=/artifacts
```

---

## 2a. Control Center frontend — Vercel (LIVE)

The **beginner-friendly Control Center** (`ridebase-control-center/`) is the
production frontend, deployed as a **static site** (no Next.js, no Claude iframe):

- **URL:** <https://ridebase-ml-control-center.vercel.app>
- Vercel project `ridebase-ml-control-center`, **Root Directory** =
  `ridebase-control-center`, framework **Other**.
- `vercel.json`: `buildCommand: python3 build.py` (stdlib only) → `outputDirectory: public`.
  Falls back to the committed `public/` if the build step fails.
- Env var: `NEXT_PUBLIC_API_BASE_URL = https://ridebase-inference-api.onrender.com`
  (also accepts `RIDEBASE_V2_API`; hard-coded fallback is the same URL).
- Redeploy: `cd ridebase-control-center && python3 build.py && vercel --prod`, or push.
- Claude Artifact (`3366dcd0-…`) is now **preview/development only**.

## 2b. V1-only dashboard frontend — Vercel (optional, legacy)

- Import the repo, set **Root Directory** = `ridebase-v1-dashboard/frontend`.
- Framework preset: **Next.js** (auto).
- Env var: `NEXT_PUBLIC_API_BASE_URL = https://<your-backend-domain>`
  (build-time — redeploy after changing it).
- Deploy. Vercel handles SSR + static automatically; `output: "standalone"` is
  harmless there.

**Node host (Docker)**

`frontend/Dockerfile` produces a standalone server:

```bash
docker build --build-arg NEXT_PUBLIC_API_BASE_URL=https://<backend> \
  -t ridebase-v1-dashboard-frontend ridebase-v1-dashboard/frontend
docker run -p 3000:3000 -e NEXT_PUBLIC_API_BASE_URL=https://<backend> \
  ridebase-v1-dashboard-frontend        # runs: node server.js
```

---

## 3. Wire CORS

Set on the Render service (`ridebase-inference-api` → **Environment** — saving an
env var auto-redeploys, even with `autoDeploy: false` for git):

| var | value |
|-----|-------|
| `ALLOWED_ORIGINS` | `https://ridebase-ml-control-center.vercel.app,https://claude.ai,https://preview.claude.ai` |
| `ALLOWED_ORIGIN_REGEX` | `https://(ridebase-ml-control-center-[a-z0-9-]+\.vercel\.app\|.*\.claudeusercontent\.com)` |

(Both are already in `render.yaml`; a dashboard env edit is the quickest way to
apply them without re-syncing the blueprint.) Verify:

```bash
curl -s -i -X OPTIONS https://ridebase-inference-api.onrender.com/api/predict/service \
  -H 'Origin: https://ridebase-ml-control-center.vercel.app' \
  -H 'Access-Control-Request-Method: POST' | grep -i 'access-control-allow-origin'
# expect: access-control-allow-origin: https://ridebase-ml-control-center.vercel.app
```

**Do not treat the frontend Live Prediction as working until this returns the
allow-origin header.** Render free instances also cold-start (~50 s) — the UI
shows "Model servisi uyanıyor…" and retries; that is expected, not an outage.

---

## 4. Shipping a new model

1. Drop new `models/v1_final_*` (+ refreshed `reports/tables/v1_final_tuning_*`,
   `outputs/v1_final_tuning_test_predictions.parquet`) into the artifact location.
2. `curl -X POST -H "Authorization: Bearer $RIDEBASE_ADMIN_TOKEN" https://<backend>/admin/reload` (or restart the service).
3. `GET /health` → `model_generation`, and `GET /api/v1/model/info` → new names/metrics.
   **No frontend change or redeploy.**

---

## 5. Smoke after deploy

```bash
API_BASE=https://<backend> python ridebase-v1-dashboard/backend/scripts/smoke_e2e.py
```

Expect `14/14 checks passed`.
