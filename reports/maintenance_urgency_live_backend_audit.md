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

## Post-deploy result

- Timestamp (UTC): `2026-09-04T15:51:11Z`
- Render deployment: `dep-dadegu1t0dsc7389ekag`
- Source commit: `2ecedf4cff79a289d932ff44ebc6346affaaa0a6`
- HTTP status: `200`
- Latency: `1.179737 s`
- Classification: **CURRENT**

The identical request now returns all required canonical fields:

```json
{
  "maintenance_urgency_score": 100,
  "maintenance_urgency_level": "KRİTİK",
  "maintenance_urgency_reason": "27.000 km gecikmiş (kilometre periyodu 10.0× seviyesinde)",
  "determining_dimension": "KM",
  "progress_ratio": 10.0
}
```

The V2.0 regression baseline is an exact match before and after deployment: P30 `0.0797877`,
P60 `0.38654509`, P90 `0.49490988`, P120 `0.82370121`. Therefore the deployment changed
the deterministic maintenance contract without changing the frozen prediction behavior.
