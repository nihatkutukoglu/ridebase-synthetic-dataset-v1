# V2.0 Live-Scenario Audit Status

Status: **SYNTHETIC RESEARCH BASELINE — FAILED LIVE-SCENARIO AUDIT.**

V2.0 was trained on post-service snapshots: each row starts immediately after a
completed service and predicts the following service. The public scenario UI,
however, asks about an arbitrary current day. Those are different landmarks.
The v1.3 metadata explicitly calls the old snapshot a “post-service canonical
state,” while the API manufactures a partial arbitrary-day row and leaves most
of its 117 service-event features missing.

The automated regression audit in
`ridebase-ml/reports/v2_1_live_behavior_audit.json` reproduces the product
failures:

- 92 of 100 realistic cases return exactly `0.0` at 30 days.
- Moving `km_since_previous_service` from 500 to 20,000 km changes calibrated
  90-day risk by only about 1.6 percentage points.
- Increasing elapsed time from 30 to 730 days moves 90-day risk from about
  26.9% to 0.0%, the wrong direction for maintenance pressure.
- Equivalent age/season/state cases vary materially across absolute years;
  `snapshot_year` is a direct V2.0 feature.
- Changing only `days_observed`, a collection-window artifact, changes 90-day
  risk by about 12.8 percentage points.
- A deterministically overdue motorcycle can still receive about 2.9% 90-day
  customer-return probability.

V2.0 routes and artifacts remain frozen for reproducibility. Their historical
C-index, AUC and Brier results are not evidence that arbitrary-day scenario
prediction works.
