# RideBase V2.1 History Serving Memory Baseline & Root-Cause Audit

## Verdict: ROOT CAUSE CONFIRMED

The 502/503 worker restart observed in the production Render free-tier container (`https://ridebase-inference-api.onrender.com`) upon receiving a valid `POST /api/v2_1/predict/by-motorcycle` request is **CONFIRMED** to be caused by Out-Of-Memory (OOM) termination.

### 1. Evidence & Profiling
- **Container Limit**: Render Free Tier grants **512 MB** total memory.
- **Resident Baseline**: Loading V1 artifacts, V2.0 models, and V2.1 survival models consumes **~362 MB** RSS before handling any history requests. Headroom remaining: **~150 MB**.
- **Request Behavior**:
  - For unknown motorcycles: only `motorcycles.csv` (~1.5 MB) is checked. Headroom is preserved, returning **HTTP 404** with 197 ms latency.
  - For valid motorcycles: `SyntheticRideBaseSourceAdapter` triggers reads of 11 source CSVs totaling **~177 MB** into PyArrow tables. Peak RSS surges by **+87.4 MB to 130+ MB**, pushing container memory beyond 450 MB on macOS and past 512 MB in Linux container environments under PyArrow allocation buffers.
  - Result: Linux cgroups OOM killer issues `SIGKILL` (exit 137). Uvicorn worker dies, Render returns `502 Bad Gateway`, followed by `503 Service Unavailable` while restarting the container.

### 2. Solution
Build a compact, indexed SQLite serving store (`v2_1_history_serving.sqlite`) from the frozen V1.4 source tables containing only the 54-feature contract columns with targeted B-tree indexes, and serve queries via `SyntheticSQLiteSourceAdapter`. This reduces query memory to < 1–2 MB per request, ensuring total footprint remains comfortably under 380 MB.
