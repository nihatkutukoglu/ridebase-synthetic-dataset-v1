# Maintenance Urgency Live Backend Audit

## Pre-hardening result

- Timestamp (UTC): `2026-09-04T15:41:56Z`
- Endpoint: `POST https://ridebase-inference-api.onrender.com/api/v2/predict/scenario`
- HTTP status: `200`
- Latency: `1.079783 s`
- Classification: **STALE**

The known NS200-like request returned `progress_ratio: 10.0`, but the live response omitted
`maintenance_urgency_score`, `maintenance_urgency_level`, `maintenance_urgency_reason`, and
`determining_dimension`. The V2.0 probability values were recorded as a regression baseline:
P30 `0.0797877`, P60 `0.38654509`, P90 `0.49490988`, P120 `0.82370121`.

This is direct live-response evidence. The existing Control Center fallback is not evidence that Render is current.
