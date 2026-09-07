# V3 Product Output Contract (Phase 25)

**Research API contract only. Not a production deployment. No route is mounted.**

Produced by `ridebase_ml.v3.predictor.V3TaskPredictor`. If a research-only endpoint
is ever added it must be disabled by default.

## Response shape

```json
{
  "model_version": "v3.0-research",
  "status": "RESEARCH_OFFLINE_SYNTHETIC_ONLY",
  "landmark_date": "2026-07-31",
  "predicted_tasks": [
    {
      "task": "ENGINE_OIL_CHANGE",
      "probability": 0.9134,
      "predicted": true,
      "rank": 1,
      "applicable": true,
      "support_class": "A_CORE"
    }
  ],
  "top_k": [ "... same shape, truncated to k applicable tasks ..." ],
  "warnings": [
    "13 of 44 tasks are not applicable to this motorcycle's powertrain/drivetrain and are forced to 0.0",
    "low-support labels in the top 5: WHEEL_BALANCE — these clear the V3 modelling gate but have wide uncertainty",
    "V3 estimates which tasks may be performed at the next completed service. These are NOT mechanical failure probabilities, NOT a maintenance urgency score, and NOT a V2.1 service-return probability."
  ],
  "provenance": {
    "source_world": "v1_4",
    "champion_family": "<frozen champion family>",
    "label_count": 44,
    "labels_applicable": 31,
    "threshold_policy": "per_label_f1",
    "calibration_policy": { "none": 0, "isotonic": 0, "sigmoid": 0 },
    "target_semantics": "task recorded with status=COMPLETED on the first service strictly after the landmark",
    "real_fleet_validation": "PENDING — never claimed",
    "deployed": false
  }
}
```

## Field semantics

| Field | Meaning |
|---|---|
| `model_version` | frozen artifact version. Always carries the `-research` suffix. |
| `status` | `RESEARCH_OFFLINE_SYNTHETIC_ONLY`. There is no "production" status value. |
| `landmark_date` | the point in time the prediction is made from. A V3 answer without it is meaningless. |
| `predicted_tasks[].probability` | calibrated probability that this task is performed at the next completed service. |
| `predicted_tasks[].predicted` | the binary decision at that label's frozen threshold. Thresholds are per-label and are **not** 0.5. |
| `predicted_tasks[].rank` | rank by probability across all modelled labels, before the applicability filter. |
| `predicted_tasks[].applicable` | whether the task is physically possible on this motorcycle. |
| `predicted_tasks[].support_class` | `A_CORE` or `B_LOW_FREQUENCY`, from the frozen label set. |
| `top_k` | the first *k* applicable tasks by rank. This is what a UI renders. |
| `warnings` | always non-empty: the semantics disclaimer is unconditional. |
| `provenance` | coverage, frozen policy, and the explicit "not deployed / not real-fleet-validated" statement. |

## Coverage

Only the **44 modelled labels** appear. The 30 excluded labels are never emitted —
not at 0.0, not as `null`. `config/v3_label_set.json` is the authority on which
labels exist and why the others do not.

Within those 44, a task inapplicable to the motorcycle is forced to probability
`0.0`, marked `applicable: false`, and omitted from `predicted_tasks` and `top_k`.

## Hard exclusions

The response contains **no** Maintenance Urgency score and **no** V2.1
service-return probability. These are separate surfaces with separate
denominators; combining them into one payload is the most likely path to a task
probability being read as a failure probability.

## Invariants (enforced by tests)

- every probability is finite and in `[0, 1]`
- identical input produces byte-identical output
- ranks are `1..n` with no gaps and no ties broken non-deterministically
- an inapplicable task always has `probability == 0.0`
- the semantics disclaimer is always present in `warnings`
- `provenance.deployed` is always `false`
- passing a target-derived or identifier column raises `V3PredictionError`
