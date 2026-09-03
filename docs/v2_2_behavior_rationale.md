# RideBase V2.2 synthetic behavior rationale

V2.2 is a challenger, not a production replacement. Its purpose is to test whether a more coherent synthetic customer-return process produces a model with better overdue/high-usage behavior while preserving calibration, discrimination, temporal integrity, and unseen-motorcycle generalization. No target percentage is specified or optimized.

## Central distinction

Maintenance due and service-return risk answer different questions. Deterministic policy logic can say that a motorcycle needs service now; the survival model estimates whether the customer will actually return within 30, 60, 90, or 120 days. A severely overdue customer can still no-show, use another workshop, sell the vehicle, stop riding, or churn.

## Synthetic assumptions

The V1.5 simulation assumes that due pressure, usage, adherence, prior appointment behavior, repair pressure, known appointment intent, seasonality, and segment affect return hazard through smooth, saturating functions. These relationships are hypotheses for simulation—not measured facts about RideBase customers.

- Increasing kilometre or time pressure generally raises return hazard, with diminishing marginal effect. Neither a due threshold nor severe overdue guarantees a return.
- Higher recent/annual usage generally shortens return timing, especially when maintenance pressure is already high.
- Historically adherent customers generally return sooner than chronic delayers.
- Repeated no-shows, cancellations, price sensitivity, and churn tendency can counteract overdue pressure.
- A recent breakdown/repair increases pressure, particularly for high-use motorcycles.
- An appointment created by the landmark and scheduled after it represents known intent. Its later outcome is never exposed at the landmark.
- Segment differences are modest; observable individual history should dominate them.
- Seasonality is cyclical. Absolute year is neither a generator shortcut nor a model feature.

Latent generator profiles may shape observable event histories but are prohibited from source tables and model features. The model may only learn from point-in-time observable history.

## Point-in-time contract

Every feature uses information effective on or before the landmark. Future services, post-landmark mileage, future tasks/parts, future appointment outcomes, targets, censoring data, split labels, `days_observed`, and absolute year are forbidden. An appointment scheduled after the landmark is usable only when its `created_at` is on or before the landmark; its eventual status remains unknown.

## Evaluation philosophy

Behavior is tested directionally across broad grids. Pairwise/trend rates are used rather than forcing every noisy pair or any exact probability. Statistical and behavioral gates are both required. Candidate selection and calibration use TRAIN/VALIDATION only; TEST is opened once after the selection manifest is frozen. V2.1 remains the production champion regardless of the V2.2 result, real-fleet validation remains pending, and V3 stays on hold.

> These are synthetic behavioral assumptions and are not validated on real RideBase fleet data.
