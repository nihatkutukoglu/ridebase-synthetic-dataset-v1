# RideBase V2.1 — Prompt 6: Memory-Safe Production History Serving & Live Unblock Report

## 1. Executive Verdict: PASS (PRODUCTION UNBLOCKED)

The memory root-cause on Render Free tier (512 MB cgroup limit) has been **fully resolved**. The production history pipeline is now backed by a compact, indexed SQLite serving store (`v2_1_history_serving.sqlite`).

- **Live Backend**: `https://ridebase-inference-api.onrender.com`
- **Live Frontend**: `https://ridebase-ml-control-center.vercel.app`
- **Git Commit**: `a6b6501` (`HEAD == origin/main`)
- **Scientific Parity**: **54/54 features exact**, **16,200/16,200 cells exact**, **Max probability delta: 0.000000000**
- **Leakage & Gates**: Future-injection gate PASS, boundary gate PASS, leakage guard PASS
- **Memory**: Peak request memory surge reduced from **+87.4 MB to +0.33 MB** (~265x reduction). Total resident memory under 100 requests remains **366.58 MB**, preserving **145.42 MB safe headroom** below the 512 MB limit.
- **Retraining / Schema Changes**: Strictly ZERO. Model `xgb_cox` and isotonic calibration are completely frozen.
- **Real Fleet Status**: `PENDING` (Honest labeling preserved across all endpoints and UI).

---

## 2. Architecture & Root Cause Resolution

### Root Cause
In Render Free tier (512 MB Linux cgroup limit), resident models (V1, V2.0, V2.1) occupy ~362 MB. The previous `SyntheticRideBaseSourceAdapter` loaded raw CSV tables on demand via PyArrow/pandas (~177 MB disk, 344k+ mileage rows, 215k+ tasks). Reading these files caused an instant heap allocation surge of +87.4 MB to +130+ MB, breaching the 512 MB container limit and triggering Linux OOM killer (`SIGKILL`, exit 137) resulting in 502/503 worker restarts.

### Solution: Derived SQLite Serving Store (`v2_1_history_serving.sqlite`)
1. **Compact Offline Build**: Extracted only the columns required by the frozen 54-feature contract across 12 source tables.
2. **Targeted B-Tree Indexes**: Point-in-time indexed queries on `(motorcycle_id, received_at)`, `(motorcycle_id, period_end_date)`, `(motorcycle_id, created_at)`, etc.
3. **Footprint**: Reduced raw data size from **176.93 MB** to **66.35 MB** (-62.5%).
4. **SyntheticSQLiteSourceAdapter**:
   - Strictly read-only (`mode=ro`, `PRAGMA query_only = ON`).
   - Thread-safe local connections (`threading.local()`).
   - Zero full-table in-memory caching. Queries only pull the ~5-50 rows needed for the specific motorcycle.
   - Preserves exact point-in-time boundary semantics: latest valid `closing_odometer_km` from monthly timeline, never falls back to `initial_mileage_km`.

---

## 3. Memory & Performance Benchmark (100 Deterministic Requests)

| Metric | CSV Adapter (Baseline) | SQLite Adapter (Production) | Improvement / Safety |
|---|---|---|---|
| **Resident Base RSS** (V1+V2+V2.1) | 362.42 MB | 362.97 MB | Full model suite loaded |
| **RSS After Adapter Init** | 362.42 MB | 364.73 MB | +1.76 MB (zero table preloads) |
| **First Request Peak RSS** | **449.80 MB** | **365.06 MB** | **-84.74 MB lower peak** |
| **First Request Memory Delta** | **+87.38 MB** | **+0.33 MB** | **~265x lower memory footprint** |
| **Final Peak RSS (100 requests)** | 449.80+ MB (OOM Kill) | **366.58 MB** | **Comfortably below 370 MB** |
| **Remaining Headroom (512 MB limit)**| 62.20 MB (Critical OOM) | **145.42 MB** | **+83.22 MB safe headroom** |
| **Disk Footprint** | 176.93 MB | **66.35 MB** | **-62.5% disk reduction** |
| **Latency p50** | 12.0 ms | **8.99 ms** | -25% faster |
| **Latency p95** | 24.5 ms | **10.76 ms** | -56% faster |
| **Latency Max** | 192.0 ms | **14.94 ms** | Zero cold-load spike |
| **Memory Leak Check** | Monotonic rise | **PASS (Zero leak)** | Plateaued at req #60 |

---

## 4. Scientific Parity & Leakage Gates

- **300 Golden Landmarks Parity**:
  - Reconstructed Features: **54 / 54** exact match
  - Reconstructed Matrix: **16,200 / 16,200** exact cells
  - Mismatches: **0**
  - Probability Deltas (P30, P60, P90, P120): **0.000000000**
  - Median Service Days Diffs: **0**
- **Future Injection Gate**: Injected future services, mileage timeline, service tasks, service parts, and appointments at $T+1$ — **Feature leakage: 0 (PASS)**.
- **Boundary Gate**: Evaluated at $T-1$, $T$, and $T+1$ — **Temporal integrity: PASS**.

---

## 5. Live Production Audit (Render: `https://ridebase-inference-api.onrender.com`)

All 10 live test cases returned **HTTP 200**, strict risk monotonicity ($P_{30} \le P_{60} \le P_{90} \le P_{120}$), exact determinism on repeat, and zero container crashes:

| Case | Motorcycle ID | Landmark Date | Status | P30 | P60 | P90 | P120 | Median (Days) | Latency | Monotonic | Deterministic |
|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **normal** | `MC000001` | `2025-06-01` | 200 OK | 0.1580 | 0.3297 | 0.5202 | 0.6756 | 292.0 | 1156 ms | PASS | PASS |
| **sparse_history** | `MC000001` | `2024-06-25` | 200 OK | 0.1482 | 0.3030 | 0.4874 | 0.6295 | 308.0 | 413 ms | PASS | PASS |
| **rich_history** | `MC000001` | `2024-07-31` | 200 OK | 0.0291 | 0.1155 | 0.2183 | 0.3436 | None | 514 ms | PASS | PASS |
| **not_due** | `MC000002` | `2024-01-15` | 200 OK | 0.0874 | 0.2137 | 0.3191 | 0.4835 | 353.0 | 425 ms | PASS | PASS |
| **near_due** | `MC000002` | `2024-09-01` | 200 OK | 0.0291 | 0.0839 | 0.1538 | 0.2625 | None | 513 ms | PASS | PASS |
| **overdue** | `MC000003` | `2025-08-01` | 200 OK | 0.1286 | 0.2611 | 0.4441 | 0.6295 | 322.0 | 511 ms | PASS | PASS |
| **high_km** | `MC000005` | `2025-06-01` | 200 OK | 0.0830 | 0.1988 | 0.3191 | 0.4753 | None | 614 ms | PASS | PASS |
| **diff_category** | `MC000004` | `2026-01-15` | 200 OK | 0.0291 | 0.0773 | 0.1483 | 0.2434 | None | 410 ms | PASS | PASS |
| **old_landmark** | `MC000006` | `2024-08-01` | 200 OK | 0.0291 | 0.0773 | 0.1483 | 0.2434 | None | 552 ms | PASS | PASS |
| **recent_landmark**| `MC000007` | `2026-02-01` | 200 OK | 0.1286 | 0.2603 | 0.4441 | 0.6295 | 326.0 | 500 ms | PASS | PASS |

### Error Handling & CORS
- **Unknown Motorcycle (`MC999999`)**: Returned honest `HTTP 404 {"detail": "unknown motorcycle_id 'MC999999'"}`.
- **Pre-observation Landmark (`2023-01-01`)**: Returned honest `HTTP 422 {"detail": "unknown motorcycle_id 'MC000001' at 2023-01-01"}`.
- **CORS Preflight (OPTIONS)**: Returned `HTTP 200` with `Access-Control-Allow-Origin: https://ridebase-ml-control-center.vercel.app`.
- **Live Health Post-Audit**:
  ```json
  {
    "status": "ok",
    "v2_1_status": "ok",
    "v2_1_model_loaded": true,
    "v2_1_champion": "xgb_cox",
    "v2_1_history_status": "ok",
    "v2_1_history_source": "SYNTHETIC_V1_4",
    "v2_1_history_adapter": "SQLITE",
    "v2_1_history_store_loaded": true,
    "v2_1_history_store_version": "1.4.0",
    "v2_1_history_store_hash": "a057573c9c35b1155aacabb0cf98269a6e57a87f51fa41d926741b817f2fa657"
  }
  ```

---

## 6. Live Regression Status

| Component | Endpoint | Live Status | Verdict / Note |
|---|---|:---:|---|
| **V1 Predict** | `POST /api/v1/predict` | **200 OK** | Days & KM prediction verified (`next_service_days: 337.5`) |
| **V2.0 Scenario** | `POST /api/v2/predict/scenario` | **200 OK** | Ensemble Cox working; retains honest `LIVE-SCENARIO AUDIT FAILED` |
| **V2.1 Scenario** | `POST /api/v2_1/predict/scenario` | **200 OK** | Partial scenario heuristic working (`risk_30d: 0.207218`) |
| **V2.1 History** | `POST /api/v2_1/predict/by-motorcycle` | **200 OK** | Point-in-time SQLite history serving (`risk_30d: 0.158015`) |
| **V3 Model** | N/A | **ON HOLD** | Kept on hold |
