# V3 Phase 6 — Landmark Design

Every strategy draws from the same frozen V2.1 monthly landmark grid; they differ
only in which landmarks are kept. That keeps the comparison about *placement*
rather than about feature semantics.

Data: [`06_landmark_strategies.csv`](06_landmark_strategies.csv),
[`06_landmark_strategy_models.csv`](06_landmark_strategy_models.csv).

## Candidate strategies

| strategy | rule |
|---|---|
| `all` | every observed landmark — arbitrary current-day historical landmarks |
| **`random_one`** | **exactly one landmark per (motorcycle, target service), seeded** |
| `earliest` | the landmark with the longest lead to the target service |
| `latest` | the landmark immediately before the target service |
| `annual` | one landmark per motorcycle-year — fixed cadence |

## Duplication

| strategy | rows | target services | landmarks/target | max/target | landmarks/motorcycle |
|---|---|---|---|---|---|
| all | 157887 | 39451 | 4.0020 | 31 | 21.7000 |
| **random_one** | 39451 | 39451 | 1.0000 | 1 | 5.4200 |
| earliest | 39451 | 39451 | 1.0000 | 1 | 5.4200 |
| latest | 39451 | 39451 | 1.0000 | 1 | 5.4200 |
| annual | 22826 | 20341 | 1.1220 | 3 | 3.1400 |

Un-deduplicated, **each target service is shared by 4.0 landmarks on average and up
to 31**. Those rows are near-identical: consecutive monthly landmarks for the same
bike differ only by one month of odometer drift, and they all carry the *same*
label vector. Left in, they inflate effective sample size, over-weight motorcycles
with long histories, and make every metric a measure of how often the model can
re-answer a question it has already seen.

## Lead-time distribution

| strategy | lead p10 | lead median | lead mean | lead p90 | % lead <= 30d |
|---|---|---|---|---|---|
| all | 13.0000 | 70.0000 | 98.7000 | 231.0000 | 0.2465 |
| **random_one** | 8.0000 | 39.0000 | 61.3000 | 142.0000 | 0.4252 |
| earliest | 19.0000 | 78.0000 | 106.8000 | 244.0000 | 0.1905 |
| latest | 3.0000 | 16.0000 | 15.6000 | 28.0000 | 0.9811 |
| annual | 11.0000 | 59.0000 | 89.1000 | 215.0000 | 0.2964 |

This is where `latest` disqualifies itself: **98.1% of its landmarks sit within 30
days of the target service** (median lead 16 days). That is precisely the
"trivially placing every landmark immediately before a known service" design the V3
brief warns against — at a 16-day horizon, `days_since_last_service` and the policy
due ratio have almost already resolved the answer, and the resulting model would
not survive contact with a real user asking the question three months out.

`random_one` spreads lead time across the whole inter-service interval (p10 8 days,
median 39, p90 142), which matches how the question would actually be asked.

## Does the strategy inflate its own metrics?

Same model family (unweighted XGBoost), same features, each strategy trained and
evaluated on its own split:

| strategy | micro F1 | macro F1 | mAP | micro PR-AUC | P@3 | R@3 |
|---|---|---|---|---|---|---|
| all | 0.4076 | 0.2121 | 0.1555 | 0.5583 | 0.4816 | 0.5830 |
| **random_one** | 0.4215 | 0.2234 | 0.1650 | 0.5771 | 0.5008 | 0.5690 |
| earliest | 0.4107 | 0.2153 | 0.1532 | 0.5575 | 0.4981 | 0.5590 |
| latest | 0.4392 | 0.2363 | 0.1737 | 0.5880 | 0.5046 | 0.5736 |
| annual | 0.4164 | 0.2126 | 0.1536 | 0.5532 | 0.4811 | 0.5800 |

**`latest` reports the best micro F1 in the table (0.4392 against `random_one`'s
0.4215) purely by standing closer to the answer.** Its features are not better; its
question is easier. Reporting that number as V3's performance would overstate the
product by roughly 4% micro F1 for free.

`all` scores *worst* on micro F1 (0.4076) despite having four times the rows — the
duplicate landmarks add correlated noise rather than information, and the model
spends capacity fitting motorcycles that appear 31 times.

## Chosen primary strategy: `random_one`

Justification, in order:

1. **Exactly one row per target service** (39,451 rows, 39,451 distinct target
   services, max 1 per target). Duplication is eliminated by construction, not by
   a weighting correction.
2. **Lead-time distribution matches real usage.** The question "what will happen at
   the next service" is asked at arbitrary points in the interval, not 16 days
   before it.
3. **It does not flatter itself.** It scores below `latest` on micro F1. A strategy
   chosen for honesty rather than for its own number is the right default.
4. **Reproducible.** Seeded permutation, then one row per
   `(motorcycle_id, next_service_id)`; `test_dataset_build_is_reproducible` and
   `test_seed_change_moves_the_landmark_sample` pin both directions.

`annual` was the runner-up on design grounds but discards 42% of target services
for no measurable gain (mAP within noise of `random_one`), so it loses on data
efficiency.

## Proximity and cross-split audits

- **Landmark density**: 5.42 landmarks per motorcycle under `random_one`, versus
  21.70 under `all`.
- **Target-service duplication**: 1.000 landmarks per target, max 1.
- **Cross-split target sharing**: **0** target services span two splits even in the
  worst case (the un-deduplicated purged pool). The Phase-7 purge makes this
  structurally impossible, and it is asserted in
  `test_no_target_service_bleeds_across_a_split_boundary`.
- **Proximity leakage**: the minimum lead is 1 day by construction
  (`test_next_service_is_strictly_after_landmark`), and no feature is computed from
  anything after the landmark (Phase 8).
