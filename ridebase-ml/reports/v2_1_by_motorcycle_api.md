# V2.1 by-motorcycle history API

**Status: PASS.** `POST /api/v2_1/predict/by-motorcycle` accepts only a motorcycle ID and an explicit landmark date, reconstructs the frozen 54-feature contract from synthetic V1.4 history, and invokes the unchanged V2.1 predictor.

## Contract and semantics

- History source: `SYNTHETIC_V1_4`
- Model status: `SYNTHETICALLY_VALIDATED`; real-fleet validation remains `PENDING`
- Risk means service-return probability within each horizon, not maintenance-needed probability.
- Unknown motorcycles return 404, invalid/pre-observation landmarks return 422, and adapter/model failures return 503 without a prediction.
- `/api/v2_1/predict/scenario` remains a separate partial-information what-if route.

## Verification

- Golden direct-builder/API pairs: 5; maximum absolute probability delta: `0.0`
- New history API tests: 15
- Backend suite: 81 passed
- ML suite: 51 passed
- Future leakage, horizon monotonicity, deterministic repeat, privacy, and V1/V2.0/existing-V2.1 regression checks: PASS

## Local latency

Fifty warm deterministic TestClient requests produced 11.194 ms p50 and 22.521 ms p95 total-route latency. Median history-build latency was 8.426 ms and median predictor latency was 2.720 ms. The first route request was 139.567 ms. Source tables are cached and are not reloaded per request.

The production Dockerfile now packages the frozen V1.4 source tables and source-schema contract. The local Docker daemon was unavailable, so the actual container build is intentionally verified by the Prompt 5 Render deployment.

`PROMPT 4 PASS — BY-MOTORCYCLE API READY FOR UI`
