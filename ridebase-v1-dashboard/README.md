# RideBase V1 Intelligence

Production-architecture dashboard **and** prediction API for the RideBase **V1
next-service regression** models (days & km to the next service).

> **Model status:** SYNTHETICALLY VALIDATED (RideBase Synthetic Dataset v1.3)
> **Production data validation:** PENDING — the *app* is production-ready; the
> *model* has not yet been validated on a real fleet, and the UI says so
> everywhere.

---

## What it does

| Part | Purpose |
|------|---------|
| **Model analytics** | How the models were trained & selected, TEST performance, error distribution, feature importance, segment/cold-history errors, temporal drift, and every V1 experiment (V0 → final tuning, incl. the external-manufacturer-knowledge result). |
| **Live prediction** | Enter a motorcycle snapshot → predicted next-service **days** and **km**, plus the derived absolute service **date** and **odometer**. |

Every number in the dashboard is read from the notebook artifacts
(`ridebase-ml/reports`, `outputs`, `models`) at request time — **nothing is
hard-coded**. When a newer model is dropped in, the backend picks it up on the
next `POST /admin/reload` (or restart); the frontend needs no changes.

---

## Architecture

```
ridebase-v1-dashboard/
├── backend/          FastAPI · loads the frozen joblib models + preprocessors
│   ├── app/
│   │   ├── artifacts.py   LATEST-VALID artifact discovery, feature catalog, leakage guard
│   │   ├── predictor.py   transform-only inference, derived date/odometer, OOD check
│   │   ├── analytics.py   CSV/parquet/markdown → normalised JSON
│   │   ├── routes.py      /health, /api/v1/*  (predict + analytics)
│   │   └── main.py        app wiring, CORS, request logging, startup model load
│   ├── scripts/smoke_e2e.py   end-to-end chain test
│   └── tests/                  pytest (health, model-load, predict, validation, feature-order…)
└── frontend/         Next.js 14 (App Router) · TypeScript · Tailwind · Recharts
    └── src/
        ├── app/page.tsx            10-section tabbed shell
        ├── components/sections/    Overview · DAYS · KM · Models · Features · Errors · Drift · Experiments · Live prediction · Verdict
        ├── components/charts/      Recharts wrappers (scatter, histogram, tolerance, h-bar, grouped, line)
        └── lib/                    api client + useApi hook, formatting, types
```

**Data flow:** browser → `NEXT_PUBLIC_API_BASE_URL` (FastAPI) → frozen
preprocessor `.transform()` → DAYS model + KM model → JSON. The frontend never
touches a joblib file.

---

## Model artifacts consumed

Discovered with a **LATEST VALID MODEL** strategy — notebook-12 first, else the
notebook-10 v1.3 final regression:

| Artifact | Used for |
|----------|----------|
| `models/v1_final_{days,km}_model.joblib` | inference (LGBM / HGB, native-cat or encoded, incl. `log1p` transform) |
| `models/v1_final_{days,km}_preprocessor.joblib` | train-time `ColumnTransformer` (transform-only) |
| `models/v1_final_tuning_config.json` | frozen config, hyperparameters, ensemble/specialist flags |
| `reports/tables/v1_final_tuning_*.csv` | metrics, leaderboards, feature importance, drift, calibration, worst segments |
| `outputs/v1_final_tuning_test_predictions.parquet` | actual-vs-predicted scatter, residual/abs-error histograms, sample motorcycle |
| `reports/v1_final_hyperparameter_tuning_report.md` | verdict / limitations text |

If notebook 12 is still running, the dashboard shows whatever is currently on
disk and never invents a missing value ("artifact not available").

---

## Run it locally

### Option A — Docker (full stack)

```bash
cd ridebase-v1-dashboard
docker compose up --build
# dashboard  → http://localhost:3000
# API + docs → http://localhost:8000/docs
```

`docker-compose.yml` mounts `../ridebase-ml/{models,reports,outputs}` and
`../ridebase_v1_3/derived_outputs` **read-only** into the backend.

### Option B — native

```bash
# backend
cd ridebase-v1-dashboard/backend
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload --port 8000

# frontend (second shell)
cd ridebase-v1-dashboard/frontend
npm install
cp .env.example .env.local          # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev                         # http://localhost:3000
```

or `make dev` from `ridebase-v1-dashboard/`.

---

## Environment

**Backend** (`backend/.env` / compose env)

| var | default | meaning |
|-----|---------|---------|
| `APP_ENV` | `development` | |
| `MODEL_DIR` / `REPORTS_DIR` / `OUTPUTS_DIR` / `DATASET_DIR` | repo-relative `ridebase-ml/*` | artifact locations |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORS allow-list |
| `MAX_REQUEST_BYTES` | `1000000` | request-size cap |
| `SCATTER_SAMPLE` | `1500` | max scatter points returned |

**Frontend**

| var | meaning |
|-----|---------|
| `NEXT_PUBLIC_API_BASE_URL` | base URL of the FastAPI backend |

No secrets are committed; `.env.example` files are provided.

---

## API

| method | path | purpose |
|--------|------|---------|
| GET | `/health` | model-load + leakage-guard status |
| GET | `/api/v1/model/info` | model names, feature counts, dataset version, **production-validation = PENDING** |
| GET | `/api/v1/metrics` | TEST metric bands + baseline-vs-tuned + QA |
| GET | `/api/v1/features?mode=all\|simple\|days\|km` | authoritative input schema (types, ranges, options, labels) |
| GET | `/api/v1/sample` | anonymised snapshot row (targets stripped) to seed the form |
| POST | `/api/v1/predict` | `{features, snapshot_date}` → days/km + derived date/odometer + typical error + OOD flags |
| POST | `/api/v1/predict/batch` | up to 200 items |
| GET | `/api/v1/analytics/{overview,models,features,errors,drift,experiments,verdict}` | normalised section payloads |
| GET | `/api/v1/analytics/target/{DAYS\|KM}` | per-target metrics + chart data |
| POST | `/admin/reload` | re-read artifacts without a restart (403 when `APP_ENV=production`) |

### V2 survival (`/api/v2/*`)

The frozen FULL/FINAL V2 ensemble (`ENSEMBLE[XGBoost survival:cox + CoxNet]`, weights
0.6 / 0.4, per-horizon IPCW-isotonic calibration) served through
`ridebase_ml.v2.V2SurvivalPredictor`. **Model status: SYNTHETICALLY VALIDATED
(RideBase Synthetic Dataset v1.3); real-fleet validation PENDING — not production-validated.**

| method | path | purpose |
|--------|------|---------|
| GET | `/api/v2/model/info` | artifact-driven metadata (family, run_mode=FULL, weights, horizons, TEST metrics) |
| GET | `/api/v2/features` | fixed 117-feature contract + training stats/options (caller cannot set order; `split` is internal) |
| GET | `/api/v2/metrics` | nb15/nb16 tables: horizon Brier/AUC/calibration, risk groups, grouped-bootstrap CIs, golden-parity flag |
| GET | `/api/v2/sample` | production-safe example request (training medians/modes) |
| POST | `/api/v2/predict` | `{features, snapshot_date?, strict?}` → `risk_30d/60d/90d/120d`, `median_service_days`, `risk_group_90d`, per-horizon calibration quality, `warning` |
| POST | `/api/v2/predict/batch` | up to 2000 items |
| POST | `/api/predict/service` | **V1 + V2 combined** — point days/km *and* probability-over-time for one snapshot |

**Risk interpretation:** `risk_90d = 0.67` means the model estimates a 67 % chance the
bike is back for service within 90 days of the snapshot. `risk_group_90d` (LOW / MEDIUM /
HIGH) uses VALIDATION 90-day-risk terciles frozen in the config. Calibration is GOOD @30,
MODERATE @60/90/120 — the app must not imply equal confidence across horizons.

**Guarantees:** deterministic; leakage keys (`duration_days`, `next_service_*`,
`survival_target*`, `*_audit`, …) and unknown fields → 422; probabilities are bounds- and
monotonicity-checked (the predictor raises rather than return a bad result); bit-for-bit
parity with notebook 15's TEST predictions (`scripts/smoke_v2_inference.py`). If the bundle
or `ridebase_ml` package is absent, `/api/v2/*` → 503 and V1 is unaffected.

### Guards

- **Leakage guard** (startup + per request): no `next_service_*`, `*_to_next_service`,
  `target_*`, censoring/survival fields may appear in a model's `feature_cols`
  or in a request. Violation → health `degraded`, request → `422`.
- **Feature-order guard**: the request row is `reindex`-ed to the model's exact
  trained column order before `transform`.
- **Input validation**: negative odometer/mileage/age, non-finite numbers,
  unknown categorical values → `422` (values are never silently changed).
- **OOD warning**: numeric inputs outside train `p01..p99` are flagged (not blocked).
- **Prediction logging**: `request_id`, timestamp, path, status, latency,
  model generation — **never the payload**.

---

## Tests

```bash
# backend
cd backend && python3 -m pytest -q            # 12 tests
python3 scripts/smoke_e2e.py --inproc          # full chain, 14 checks

# frontend
cd frontend && npm run typecheck && npm run lint && npm run test && npm run build
```

CI (`.github/workflows/ci.yml`) runs backend pytest + frontend typecheck / lint /
build / vitest on every push & PR.

---

## Limitations (shown in the app, repeated here)

- Model trained on **synthetic** RideBase v1.3 — **no real-fleet validation yet**.
- **Right-censored** snapshots (next service unseen in the data window) are
  excluded from V1 regression → motivation for **V2 survival analysis**.
- **Temporal drift**: TRAIN/VALIDATION/TEST target distributions differ; future
  behaviour may not match history.
- External manufacturer maintenance schedules added **no** predictive value on
  v1.3 (redundant with the synthetic `policy_interval_km`); may matter on real data.

See `DEPLOYMENT.md` and `PRODUCTION_CHECKLIST.md`.
