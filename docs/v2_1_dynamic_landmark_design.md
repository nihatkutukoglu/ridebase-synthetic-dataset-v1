# V2.1 Dynamic Landmark Survival Design

## Question and time origin

V2.1 is designed to answer: “At this landmark date, given only information
known by that date, what is the probability that the next delivered service
occurs within 30, 60, 90 or 120 days?” The survival time origin is
`landmark_at`; no manual shift of a service-origin survival curve is required.
Left truncation is therefore not part of this formulation.

## Immutable source architecture

RideBase Synthetic Dataset v1.3 remains frozen. No source table, column, key,
relationship or meaning is changed. The exact source contract is stored in
`ridebase-ml/config/source_schema_contract_v1_3.json` and is enforced before
landmark generation and in tests.

The only new data lives under `ridebase-ml/derived_outputs/v2_1/`:

```
frozen v1.3 source tables
        ↓ read-only
monthly landmark and history builder
        ↓
V2.1 derived feature/target/manifest tables
```

## Landmark strategy

One landmark is created at each known monthly mileage period end after the
motorcycle's first delivered service and before its per-motorcycle
administrative cutoff. The current odometer is the period's closing odometer;
it is not `initial_mileage_km`. Past services and completed tasks are joined
only when their dates are on or before the landmark. The next eligible service
must be strictly after the landmark.

If no next delivered service is observed by the motorcycle cutoff, the episode
is right-censored at that cutoff. Repeated landmarks intentionally represent
the current-day product problem, but evaluation prevents their leakage through
time and motorcycle holdouts.

## Maintenance pressure vs return

Canonical/model maintenance policies create derived due ratios and due-task
counts. These describe maintenance pressure, not the target. The target remains
an actually observed synthetic service return. No `if due then return`
probability is injected into labels.

## Current gate result

Structural QA passes for 251,054 landmarks across 8,420 motorcycles. The
synthetic-world gate fails: the 90-day event rate falls from roughly 20.4% for
overdue states to 1.2% for severely overdue states. This creates an overdue
dead region and violates the required behavioral direction. Per the stop rule,
no V2.1 model is trained or exposed as an inference route. A new versioned
same-schema synthetic event generator is the next required phase; v1.3 must not
be rewritten.
