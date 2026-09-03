# RideBase ML Control Center

One central admin view of the whole RideBase ML project — EDA, V0 baseline, V1
regression and the **V2 survival** model (packaged, 10 sub-tabs, live prediction)
as modules of a single system; V3 declared-but-empty.

## Production deployment

```
Vercel (this static site)  ──HTTPS──▶  Render FastAPI  ──▶  frozen V1 + V2 models
https://ridebase-ml-control-center.vercel.app     https://ridebase-inference-api.onrender.com
```

- **Production frontend:** <https://ridebase-ml-control-center.vercel.app> — a
  normal browser web app (no Claude iframe / artifact runtime). `build.py` emits
  `public/index.html` (+ `public/fig/`), Vercel serves `public/` as a static site
  (`vercel.json`).
- **Production API:** <https://ridebase-inference-api.onrender.com> (V1, V2.0,
  and V2.1; `/api/v1/*`, `/api/v2/*`, `/api/v2_1/*`, `/api/predict/service`).
- **API base URL** resolves: `?v2api=` query param → build-time
  `NEXT_PUBLIC_API_BASE_URL` / `RIDEBASE_V2_API` → hard-coded Render default.
  No `?v2api=` needed.
- **Claude Artifact** (<https://claude.ai/code/artifact/3366dcd0-0e51-4f81-ba96-9d24253402bc>)
  stays as **preview / development only** — its sandbox CSP can block the API call.
- **CORS:** the Vercel origin must be in the Render service's `ALLOWED_ORIGINS`
  (see `ridebase-v1-dashboard/render.yaml` / `DEPLOYMENT.md`).

Redeploy the frontend after a rebuild: `python3 build.py && vercel --prod` (or
push — Vercel builds `public/` from `vercel.json`).

## V1 live prediction

The authoritative Control Center now includes **V1 Regression → Canlı Tahmin**
at `#v1/predict`:

- **Örnek motorla demo** loads an anonymised, complete snapshot from
  `GET /api/v1/sample`, shows the understandable motorcycle fields first, and
  runs the frozen DAYS/KM models only after the user clicks the prediction
  button (`POST /api/v1/predict`). No static or fallback prediction is used.
- **Kendi motosikletimle tahmin** is intentionally non-predictive until the
  real RideBase service-history feature-derivation pipeline is connected. The
  frontend never overlays a few user fields onto sample/default values and
  presents that as a personal result.
- V1 point timing is shown in the combined V2 scenario only when both last-service
  inputs are present and deterministic maintenance is not overdue. Missing history
  or an overdue policy suppresses the future date/km so it cannot contradict the
  primary maintenance action.
- Model status remains **SYNTHETICALLY VALIDATED**; real-fleet validation is
  **PENDING**.

## V2 live prediction modes

`V2 Survival → Canlı Tahmin` has three explicitly different product modes:

- **Senaryo tahmini** loads the read-only 39-model inventory from
  `GET /api/v2/motorcycle-models`, provides cascading brand → model → year
  selection, and calls `POST /api/v2/predict/scenario`. The backend resolves
  model-master specs, derives only deterministic date/mileage fields, and sends
  those partial raw inputs to the frozen V2 preprocessor. It never calls or
  overlays `/api/v2/sample`; genuinely unknown service-history fields remain
  missing. With incomplete last-service history the result is labelled as a
  cohort/general scenario, not a personal prediction.
- **Örnek motorla demo** is the only mode allowed to call `GET /api/v2/sample`.
  The response includes separate human-readable identity metadata, while
  `model_name`/`model_id` are not added to the frozen 117-feature model vector.
- **Gerçek RideBase motoru** is disabled until `motorcycle_id → motorcycle →
  usage profile → full service history → 117-feature snapshot` is connected.

Every scenario response reports all 117 fields as `USER_INPUT`, `MODEL_MASTER`,
`DERIVED`, or `MISSING_PREPROCESSOR`, plus real per-group coverage. Coverage is
an input-completeness indicator, not model confidence. Frozen train-time
missing-value handling is legitimate; copying another motorcycle's values is
not.

Mileage terminology is explicit: `initial_mileage_km` is the synthetic
motorcycle's mileage at `observation_start_date` (basis:
`AGE_CUSTOMER_TYPE_CATEGORY_PRIOR`) and is not current odometer.
The product-level current odometer is used as V1 `snapshot_odometer_km` and,
with last-service odometer, derives V2 `km_since_previous_service`; it is never
silently mapped to `initial_mileage_km`.

The deterministic maintenance decision is the product source of truth. A due
or overdue policy is shown before ML and overdue means **SERVİS ŞİMDİ GEREKLİ**.
V2 is explicitly labelled as customer self-return behaviour, not maintenance
need. Personal maintenance status requires current odometer, last-service
odometer, and last-service date together. The Türkiye NS200 product policy is
year-aware: 2016–2023 uses the confirmed 3,000 km RideBase operating cadence;
current UG2 keeps its separate verified catalog cadence.

## V2.1 history and scenario modes

`V2.1 Landmark → Canlı Tahmin` keeps two non-interchangeable modes:

- **HISTORY PIPELINE** sends only `motorcycle_id + landmark_date` to
  `POST /api/v2_1/predict/by-motorcycle`. The backend reads immutable synthetic
  V1.4 history at or before the landmark, builds the canonical 54 features, and
  invokes the frozen V2.1 predictor. The UI labels this source
  `SYNTHETIC_V1_4`; it is not real RideBase customer history.
- **SCENARIO / WHAT-IF** keeps the existing meaningful manual inputs and calls
  `POST /api/v2_1/predict/scenario`. Unknown history stays missing and is never
  filled from a sample motorcycle.

Both modes describe V2.1 as experimental live and synthetically validated,
with real-fleet validation pending. Service-return probability remains separate
from deterministic maintenance-due status.

---

## Purpose

A project manager opens one link and sees, at a glance:

1. what stage the project is at, which modules are done, which model is active
2. DAYS / KM performance, the dataset version, QA status
3. whether it is connected to real fleet data (it is not — clearly shown)
4. the last change made, and what the next stage is
5. every experiment, model, dataset and activity entry — drill-down per module

---

## Modules

| Module | Status | Source |
|--------|--------|--------|
| **EDA** | complete | `02_eda.ipynb` — 11 sections re-homed **verbatim** from the existing "RideBase Veri Paneli" artifact |
| **V0 Baseline** | complete | `04_v0_rule_baseline.ipynb` · `v0_rule_baseline_metrics.csv` · `v0_vs_v1_regression_comparison.csv` |
| **V1 Regression** | active / frozen | `06`–`12` · `v1_final_tuning_*` tables · `v1_final_tuning_config.json` · `v1_final_hyperparameter_tuning_report.md` |
| **V2 Survival** | planned | placeholder only — no results, no fake metrics |
| **V3 Next Task** | planned | placeholder — notes manufacturer knowledge is "available as prior" |

System pages: **Experiments** (12 notebooks), **Models** (registry), **Dataset**
(v1 / v1.1 / v1.2 / v1.3 registry), **Activity** (changelog), **System Status**.

---

## Design

Adopts the design system of the existing EDA artifact:

- Plus Jakarta Sans (UI) + JetBrains Mono (all KPI / data numerals)
- dark graphite/navy ground `#090c12`, RideBase orange `#ff7a29`, cyan `#3ec6ff`
- thin borders, 12–16px radii, semantic good/warn/critical separate from the accent
- left sidebar + hash routing (`#overview`, `#eda`, `#v0`, `#v1`, `#v1/km`, …);
  mobile → drawer. `⌘K` / `Ctrl-K` command palette + fuzzy search.

---

## Data flow — nothing is hard-coded

```
repo artifacts ──> build.py ──> data/manifest.json + data/changelog.json ──┐
                                                                           ├─> RideBase_Control_Center.html  (JSON inlined)
assets/eda_source.html (existing EDA artifact) ──> 11 <section> blocks ─────┘        published as a Claude Artifact
```

`build.py`:

1. reads `ridebase-ml/reports/`, `outputs/`, `models/`, `notebooks/`,
   `external_knowledge/` and the `ridebase_v1_*/derived_outputs/` metadata
2. writes **`data/manifest.json`** (module registry, V0/V1 metrics, model &
   dataset registries, evolution table, QA, verdict text) and
   **`data/changelog.json`** (activity feed derived from report content + file
   mtimes)
3. inlines both, plus the EDA `<section>` fragment, into the HTML template and
   writes `RideBase_Control_Center.html` (publish-ready, content-only) and
   `RideBase_Control_Center.full.html` (a full document for local `file://` preview)

A missing artifact yields "artifact not available" in the UI — never a fabricated
number. The V1 numbers currently reflect the notebook-12 **FAST** run; re-running
`build.py` after the FULL run repoints them with no template change.

---

## Run

```bash
cd ridebase-control-center
python3 build.py                 # regenerates data/*.json + the HTML
open RideBase_Control_Center.full.html   # local preview
```

Then publish `RideBase_Control_Center.html` as a Claude Artifact.

---

## Adding a module (e.g. V2)

No rewrite. Three steps:

1. Add the notebook + artifacts to the repo.
2. In `build.py`: flip the module's `status` in `MODULES`, add its metric
   readers (mirror `v1_block()` / `v0_block()`), and add an `e(...)` line in
   `changelog()`.
3. `python3 build.py` → re-publish the HTML.

The sidebar, routing, command palette and registries pick the new module up from
`manifest.json` automatically.

---

## Updating after a new model / notebook result

`build.py` re-reads the artifacts every run. After a model refit or a new
report: `python3 build.py`, then re-publish. Metrics live in `manifest.json`,
never in the markup, so the front end never changes.

---

## Production status (shown throughout the UI)

| | |
|---|---|
| Application | **PILOT** (deployable — see `ridebase-v1-dashboard/`) |
| Model | **SYNTHETICALLY VALIDATED** on RideBase Synthetic Dataset v1.3 |
| Real fleet validation | **PENDING** — not connected to real data |

No authentication is implemented: Claude Artifacts have no secure server-side
auth, so the page makes **no security claims**. It is an internal / pilot view;
real auth (Supabase / Clerk / Auth.js / RideBase SSO) belongs to a later
production deployment.

## Files

```
ridebase-control-center/
├── build.py                          artifact generator (repo scan → JSON → HTML)
├── template.html                     authoring template (full document, with markers)
├── assets/eda_source.html            the existing EDA artifact, verbatim (input)
├── data/manifest.json                generated — project state
├── data/changelog.json               generated — activity feed
├── RideBase_Control_Center.html      generated — PUBLISH THIS (content-only)
├── RideBase_Control_Center.full.html generated — local preview (full document)
└── README.md
```
