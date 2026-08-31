# RideBase ML Control Center

One central, publishable admin view of the whole RideBase ML project — EDA, V0
baseline and V1 regression as **modules of a single system**, with V2 / V3 as
declared-but-empty placeholders.

Published as a Claude Artifact (single self-contained HTML page). It does **not**
replace the V1 production dashboard — it links out to it for live inference.

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
