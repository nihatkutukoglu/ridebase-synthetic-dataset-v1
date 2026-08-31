# Production Checklist — RideBase V1 Intelligence

Status legend: ✅ done in this repo · ⚙️ config step for your environment

## Model / artifacts
- [x] ✅ Final models loaded at startup (singleton, not per-request) — `artifacts.get_store()`
- [x] ✅ Preprocessors loaded once; inference is `transform`-only, never `fit`
- [x] ✅ Feature schema verified against the frozen model metadata (`feature_cols`)
- [x] ✅ Feature-order guard — request row `reindex`-ed to trained column order
- [x] ✅ Leakage check passes at startup **and** per request (`/health` → `leakage_guard: PASS`)
- [x] ✅ LATEST-VALID discovery — falls back to `v1_3_final_*` if `v1_final_*` absent
- [x] ✅ No hard-coded metrics — every value read from `reports/ outputs/ models/`
- [x] ✅ Missing artifact → "artifact not available", never a fabricated number
- [ ] ⚙️ Artifacts present at `MODEL_DIR / REPORTS_DIR / OUTPUTS_DIR / DATASET_DIR` in the target env

## API
- [x] ✅ `GET /health` returns `ok` / `degraded` with per-model load flags
- [x] ✅ `GET /api/v1/model/info` exposes dataset version + **production_validation_status = PENDING**
- [x] ✅ `POST /api/v1/predict` — typed request, 422 on invalid/missing-required/target fields
- [x] ✅ Derived `estimated_service_date` (snapshot_date + days) and `estimated_service_odometer_km`
- [x] ✅ OOD warning for inputs outside train `p01..p99` (does not block)
- [x] ✅ No confidence interval faked — "typical model error" = TEST MAE, labelled as such
- [x] ✅ Prediction logging = technical metadata only (`request_id`, latency, status) — never payload
- [x] ✅ `POST /admin/reload` to pick up a new model without redeploying the frontend

## Security
- [x] ✅ CORS allow-list (`ALLOWED_ORIGINS`), methods limited to GET/POST/OPTIONS
- [x] ✅ Request-size cap (`MAX_REQUEST_BYTES`, default 1 MB) → 413
- [x] ✅ Schema validation on every request body (Pydantic)
- [x] ✅ Safe error responses — no stack traces to the client (500 → `{"detail":"internal error"}`)
- [x] ✅ No secrets in the repo; `.env.example` only
- [ ] ⚙️ Rate limiting at the edge (platform / reverse proxy) if the API is public
- [ ] ⚙️ HTTPS termination + set `ALLOWED_ORIGINS` to the real frontend origin

## Frontend
- [x] ✅ `npm run build` passes (also type-checks + lints)
- [x] ✅ Dashboard renders (SSR) — 10 sections, sticky nav
- [x] ✅ Loading / API-offline / artifact-unavailable / prediction-error states (no blank page)
- [x] ✅ Live prediction form (simple + advanced) driven by `/api/v1/features`
- [x] ✅ Prediction result: days, km, estimated date, estimated odometer, typical error, OOD flags
- [x] ✅ Synthetic-validation badge + "real fleet validation pending" shown in nav, hero, verdict, result
- [x] ✅ R² never presented as an accuracy percentage (tooltip clarifies)
- [x] ✅ Responsive (desktop / laptop / tablet / mobile), no horizontal page overflow, tables scroll in-container
- [x] ✅ Accessibility: semantic headings, focus-visible ring, tooltips reachable by keyboard, color not the only signal
- [ ] ⚙️ `NEXT_PUBLIC_API_BASE_URL` set to the deployed backend

## Tests / CI
- [x] ✅ Backend pytest — health, model-load, model-info, features, feature-order, valid/missing/invalid predict, leakage, OOD, determinism, analytics (12 tests)
- [x] ✅ E2E smoke — `scripts/smoke_e2e.py` (14 checks, `--inproc` or live)
- [x] ✅ Frontend vitest — nav, metric card, error state, overview load, prediction form→result (5 tests)
- [x] ✅ GitHub Actions workflow: backend tests + frontend typecheck/lint/build/test
- [ ] ⚙️ `docker compose up --build` verified on the deploy host (needs Docker; compose file provided)

## Explicitly NOT claimed
- [x] ✅ Model is **not** described as "production validated" anywhere
- [x] ✅ No fake predictions, no fake historical metrics, no hidden negative results
  (the external-manufacturer-knowledge "NO VALUE on v1.3" result is shown in full)

## Open items before calling the *model* production-ready
- [ ] Real RideBase fleet data connected and the pipeline re-run on it
- [ ] Right-censoring handled → V2 survival analysis
- [ ] Drift monitoring on live inputs vs the training distribution
