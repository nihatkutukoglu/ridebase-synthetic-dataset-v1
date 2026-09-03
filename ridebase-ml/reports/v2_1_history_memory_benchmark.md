# RideBase V2.1 History Serving Memory & Performance Benchmark

## Status: PASS

Comprehensive memory profiling and latency benchmarking comparing the raw CSV PyArrow adapter against the compact indexed SQLite serving store (`v2_1_history_serving.sqlite`).

### Benchmark Metrics (100 Deterministic Requests, Full Model Stack Resident)

| Metric | CSV Adapter (Previous) | SQLite Adapter (Current) | Difference / Gate |
|---|---|---|---|
| **Cold Baseline RSS** (V1 + V2 + V2.1) | 362.42 MB | 362.97 MB | Models resident |
| **RSS After Adapter Init** | 362.42 MB | 364.73 MB | +1.76 MB (zero table preloads) |
| **First Request Peak RSS** | **449.80 MB** | **365.06 MB** | **-84.74 MB** lower peak |
| **First Request Memory Delta** | **+87.38 MB** | **+0.33 MB** | **~265x less memory jump** |
| **Final Peak RSS (100 reqs)** | 449.80+ MB (OOM in container) | **366.58 MB** | Comfortably below 400 MB |
| **Remaining Headroom (512 MB limit)** | 62.20 MB (High OOM risk) | **145.42 MB** | **+83.22 MB additional headroom** |
| **Disk Store Footprint** | 176.93 MB (11 CSVs) | **66.35 MB** (1 SQLite DB) | **-62.5% disk footprint** |
| **Latency p50** | 12.0 ms | **8.99 ms** | -25% latency |
| **Latency p95** | 24.5 ms | **10.76 ms** | -56% latency |
| **Latency Max** | 192.0 ms | **14.94 ms** | No cold-table load penalty |
| **Monotonic Leak Check** | N/A (crashes) | **PASS** (zero leak) | Peak plateaued at req 60 |

### Gate Verification
- [x] No full ~171 MB source tables loaded during requests.
- [x] Peak RSS stays strictly below 400 MB (366.58 MB).
- [x] Headroom at peak is >= 145 MB under the 512 MB container limit.
- [x] Usable latency well below 50 ms (p50: 8.99 ms, max: 14.94 ms).
- [x] 300 golden landmark parity is 0.0 delta across all survival horizons.
- [x] Future injection and boundary gates pass.
