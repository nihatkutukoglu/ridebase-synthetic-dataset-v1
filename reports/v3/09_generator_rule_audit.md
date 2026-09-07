# V3 Phase 9 — Generator-Rule / Synthetic Artifact Study

The question this phase exists to answer: **is V3 just re-deriving a deterministic
maintenance rule that the generator also used to emit the labels?**

Short answer: **no, and the reason is more interesting than a yes.** The
deterministic policy table is a *gate*, not the emitter. It decides which tasks are
*allowed* onto a work order; a stochastic process then decides which of the allowed
ones actually appear. A pure rule baseline consequently performs *worse* than
predicting each label's base rate.

## Important caveat on method

**The core generator source is not in this repository.** `services.csv` and
`service_tasks.csv` originate from a `MAINTENANCE_EVENT_SIM_V1` run whose code is
not checked in — the repo contains `build_ridebase_v1_1.py` (a QA/normalisation
pass) and the `v1_4`/`v1_5` tail extenders, none of which emit
`INSPECTION_BUNDLE`. A repository-wide search for that token finds no generator.

This audit is therefore **empirical**: the generating process for each label is
inferred from the `trigger_reason` and `is_policy_due` columns the generator
stamped on every task line, cross-checked against rule-baseline performance. That
is weaker than reading the source, and it is stated as such rather than presented
as a code audit.

## Classification of each modelled label

Assignment rule (`scripts/v3_research.py generator`):

- `FAULT` ≥ 0.9 → **E** random breakdown event
- `INSPECTION_FINDING` ≥ 0.9 → **E** random finding during a service
- `WEAR` ≥ 0.9 → **B** stochastic wear draw
- threshold share ≥ 0.95 **and** `policy_due` rate ≥ 0.95 → **A** deterministic
- `INSPECTION_BUNDLE` ≥ 0.6 → **D** behavioural bundle attachment
- otherwise → **F** mixed

where threshold share = `MILEAGE` + `TIME` + `MILEAGE_AND_TIME`.

| process | labels | mean rule PR-AUC | mean ML PR-AUC | ML/rule |
|---|---|---|---|---|
| A_DETERMINISTIC_THRESHOLD | 11.0 | 0.2147 | 0.3640 | 1.70x |
| F_MIXED_THRESHOLD_AND_BUNDLE | 13.0 | 0.0928 | 0.1951 | 2.10x |
| D_STOCHASTIC_BUNDLE_ATTACHMENT | 4.0 | 0.0588 | 0.1153 | 1.96x |
| B_STOCHASTIC_WEAR | 1.0 | 0.0061 | 0.0105 | 1.72x |
| E_INSPECTION_FINDING_RANDOM | 10.0 | 0.0067 | 0.0164 | 2.45x |
| E_BREAKDOWN_RANDOM_EVENT | 5.0 | 0.0170 | 0.0498 | 2.93x |

### A — deterministic maintenance threshold — 11 labels

| label | prevalence | threshold share | bundle share | random share | policy_due rate | rule PR-AUC | ML PR-AUC | ML/rule | signal |
|---|---|---|---|---|---|---|---|---|---|
| `ENGINE_OIL_CHANGE` | 0.8230 | 1.000 | 0.000 | 0.000 | 1.000 | 0.788 | 0.915 | 1.16x | WEAK |
| `CHAIN_CLEAN` | 0.4591 | 1.000 | 0.000 | 0.000 | 1.000 | 0.367 | 0.702 | 1.92x | MEDIUM |
| `CHAIN_LUBRICATE` | 0.3757 | 1.000 | 0.000 | 0.000 | 1.000 | 0.302 | 0.577 | 1.91x | MEDIUM |
| `BATTERY_TEST` | 0.2357 | 0.986 | 0.000 | 0.014 | 0.986 | 0.202 | 0.397 | 1.97x | STRONG |
| `CHAIN_INSPECTION` | 0.2169 | 0.980 | 0.020 | 0.000 | 0.980 | 0.188 | 0.380 | 2.02x | STRONG |
| `AIR_FILTER_CHANGE` | 0.1970 | 1.000 | 0.000 | 0.000 | 1.000 | 0.173 | 0.341 | 1.97x | STRONG |
| `CVT_BELT_CHANGE` | 0.0802 | 1.000 | 0.000 | 0.000 | 1.000 | 0.082 | 0.169 | 2.07x | STRONG |
| `BRAKE_FLUID_CHANGE` | 0.0762 | 1.000 | 0.000 | 0.000 | 1.000 | 0.078 | 0.214 | 2.72x | STRONG |
| `COOLANT_CHANGE` | 0.0632 | 1.000 | 0.000 | 0.000 | 1.000 | 0.068 | 0.133 | 1.97x | STRONG |
| `FINAL_GEAR_OIL_CHANGE` | 0.0564 | 1.000 | 0.000 | 0.000 | 1.000 | 0.072 | 0.091 | 1.26x | STRONG |
| `SPARK_PLUG_CHANGE` | 0.0322 | 1.000 | 0.000 | 0.000 | 1.000 | 0.042 | 0.086 | 2.03x | STRONG |
### F — mixed process (threshold gate + stochastic bundle) — 13 labels

| label | prevalence | threshold share | bundle share | random share | policy_due rate | rule PR-AUC | ML PR-AUC | ML/rule | signal |
|---|---|---|---|---|---|---|---|---|---|
| `AIR_FILTER_INSPECTION` | 0.2339 | 0.935 | 0.065 | 0.000 | 0.935 | 0.194 | 0.381 | 1.96x | STRONG |
| `BRAKE_FLUID_CHECK` | 0.2038 | 0.921 | 0.079 | 0.000 | 0.921 | 0.178 | 0.343 | 1.92x | STRONG |
| `COOLANT_LEVEL_CHECK` | 0.1448 | 0.878 | 0.122 | 0.000 | 0.878 | 0.149 | 0.256 | 1.71x | STRONG |
| `CVT_CASE_INSPECTION` | 0.1406 | 0.859 | 0.141 | 0.000 | 0.859 | 0.130 | 0.224 | 1.73x | MEDIUM |
| `CVT_BELT_INSPECTION` | 0.1302 | 0.851 | 0.149 | 0.000 | 0.851 | 0.121 | 0.241 | 1.99x | STRONG |
| `CVT_ROLLER_INSPECTION` | 0.0966 | 0.801 | 0.199 | 0.000 | 0.801 | 0.094 | 0.147 | 1.57x | MEDIUM |
| `FORK_INSPECTION` | 0.0771 | 0.749 | 0.215 | 0.036 | 0.749 | 0.066 | 0.173 | 2.60x | STRONG |
| `FRONT_TIRE_CHANGE` | 0.0657 | 0.877 | 0.000 | 0.000 | 0.123 | 0.071 | 0.247 | 3.49x | VERY_STRONG |
| `FRONT_BRAKE_PAD_INSPECTION` | 0.0558 | 0.649 | 0.351 | 0.000 | 0.649 | 0.049 | 0.126 | 2.59x | STRONG |
| `VALVE_CLEARANCE_INSPECTION` | 0.0518 | 0.690 | 0.310 | 0.000 | 0.690 | 0.046 | 0.097 | 2.12x | STRONG |
| `WHEEL_BEARING_INSPECTION` | 0.0448 | 0.586 | 0.351 | 0.063 | 0.586 | 0.040 | 0.087 | 2.17x | STRONG |
| `FRONT_TIRE_INSPECTION` | 0.0398 | 0.527 | 0.406 | 0.000 | 0.594 | 0.037 | 0.110 | 2.94x | STRONG |
| `SPARK_PLUG_INSPECTION` | 0.0394 | 0.636 | 0.363 | 0.000 | 0.636 | 0.031 | 0.105 | 3.35x | STRONG |
### D — customer/workshop behaviour (stochastic inspection bundle) — 4 labels

| label | prevalence | threshold share | bundle share | random share | policy_due rate | rule PR-AUC | ML PR-AUC | ML/rule | signal |
|---|---|---|---|---|---|---|---|---|---|
| `GENERAL_SAFETY_INSPECTION` | 0.1957 | 0.060 | 0.940 | 0.000 | 0.060 | 0.171 | 0.316 | 1.85x | STRONG |
| `REAR_TIRE_INSPECTION` | 0.0254 | 0.086 | 0.702 | 0.000 | 0.298 | 0.025 | 0.061 | 2.42x | STRONG |
| `REAR_BRAKE_PAD_INSPECTION` | 0.0248 | 0.241 | 0.759 | 0.000 | 0.241 | 0.020 | 0.046 | 2.31x | STRONG |
| `STEERING_BEARING_INSPECTION` | 0.0239 | 0.020 | 0.823 | 0.157 | 0.020 | 0.019 | 0.039 | 1.98x | STRONG |
### B — stochastic wear draw — 1 labels

| label | prevalence | threshold share | bundle share | random share | policy_due rate | rule PR-AUC | ML PR-AUC | ML/rule | signal |
|---|---|---|---|---|---|---|---|---|---|
| `REAR_TIRE_CHANGE` | 0.0060 | 0.000 | 0.000 | 0.000 | 1.000 | 0.006 | 0.011 | 1.72x | STRONG |
### E — random inspection finding discovered during a service — 10 labels

| label | prevalence | threshold share | bundle share | random share | policy_due rate | rule PR-AUC | ML PR-AUC | ML/rule | signal |
|---|---|---|---|---|---|---|---|---|---|
| `WHEEL_BEARING_CHANGE` | 0.0073 | 0.000 | 0.000 | 1.000 | 0.000 | 0.007 | 0.013 | 1.74x | STRONG |
| `BATTERY_CHANGE` | 0.0067 | 0.000 | 0.000 | 1.000 | 0.000 | 0.012 | 0.031 | 2.63x | VERY_STRONG |
| `STEERING_BEARING_CHANGE` | 0.0067 | 0.000 | 0.000 | 1.000 | 0.000 | 0.007 | 0.013 | 1.90x | STRONG |
| `WHEEL_BALANCE` | 0.0064 | 0.000 | 0.000 | 1.000 | 0.000 | 0.006 | 0.010 | 1.58x | MEDIUM |
| `BRAKE_DISC_CHANGE` | 0.0064 | 0.000 | 0.000 | 1.000 | 0.000 | 0.006 | 0.013 | 2.06x | STRONG |
| `BRAKE_SYSTEM_BLEED` | 0.0060 | 0.000 | 0.000 | 1.000 | 0.000 | 0.006 | 0.013 | 2.22x | STRONG |
| `THROTTLE_BODY_CLEAN` | 0.0058 | 0.000 | 0.000 | 1.000 | 0.000 | 0.006 | 0.013 | 2.17x | STRONG |
| `FUEL_INJECTOR_CLEAN` | 0.0058 | 0.000 | 0.000 | 1.000 | 0.000 | 0.006 | 0.038 | 6.64x | VERY_STRONG |
| `FORK_SEAL_CHANGE` | 0.0054 | 0.000 | 0.000 | 1.000 | 0.000 | 0.005 | 0.013 | 2.35x | STRONG |
| `VALVE_CLEARANCE_ADJUST` | 0.0052 | 0.000 | 0.000 | 1.000 | 0.000 | 0.005 | 0.007 | 1.37x | MEDIUM |
### E — random breakdown / fault event — 5 labels

| label | prevalence | threshold share | bundle share | random share | policy_due rate | rule PR-AUC | ML PR-AUC | ML/rule | signal |
|---|---|---|---|---|---|---|---|---|---|
| `FUEL_SYSTEM_DIAGNOSTIC` | 0.0245 | 0.000 | 0.000 | 1.000 | 0.000 | 0.025 | 0.062 | 2.54x | STRONG |
| `ENGINE_COMPRESSION_TEST` | 0.0226 | 0.000 | 0.000 | 1.000 | 0.000 | 0.023 | 0.080 | 3.53x | VERY_STRONG |
| `ABS_DIAGNOSTIC` | 0.0196 | 0.000 | 0.000 | 1.000 | 0.000 | 0.020 | 0.059 | 3.03x | VERY_STRONG |
| `ECU_DIAGNOSTIC_SCAN` | 0.0131 | 0.000 | 0.000 | 1.000 | 0.000 | 0.013 | 0.033 | 2.49x | STRONG |
| `ENGINE_FAULT_DIAGNOSTIC` | 0.0052 | 0.000 | 0.000 | 1.000 | 0.000 | 0.005 | 0.015 | 2.94x | STRONG |

## What the numbers say

**1. The rule alone is a bad predictor — worse than base rate.**
Baseline 1 (rule due *now*) scores mAP 0.090 and P@3 0.125; Baseline 1b (rule
projected to the next OEM due date) scores mAP 0.090 and P@3 0.132. Both are
*below* the prevalence-only baseline (mAP 0.099, P@3 0.438). If the target were a
deterministic replay of the policy table, the rule baseline would be near-perfect.
It is not close.

**2. The reason is that the generator gates on the rule and then samples.**
`FORK_INSPECTION` has the same 6,000 km / 12-month policy as `ENGINE_OIL_CHANGE`,
yet appears on 7.7% of next services against oil's 88%. Its due ratio is
*perpetually* above 1 precisely because it is rarely performed, so the rule shouts
"overdue" forever while the truth stays at 7.7%. Across the 30 labels that have a
policy row at all, the rule's due-ratio ordering is close to anti-correlated with
actual occurrence.

**3. Only the primary trigger follows the rule strictly.**
`ENGINE_OIL_CHANGE` is `primary_trigger_task` on 44,453 of 52,700 services, is
100% `MILEAGE_AND_TIME`, and is 100% `is_policy_due`. It is the one genuinely
deterministic label — and it is also the one with the **weakest ML lift**
(PR-AUC 0.915 against a prevalence of 0.823, lift 1.11x), because at 88%
prevalence there is very little headroom to win. The `primary_trigger_task` appears
as a completed task line on 90.9% of services.

**4. The value ML adds is time-to-next-visit, not rule replication.**
The rule evaluated at the landmark systematically *under*-fires: only 22% of
landmarks are overdue for an oil change, yet 88% of next services contain one —
because the next service is a median 39 days away, by which point it is due. The
rule baseline's own projection horizon `t*` (days until the next policy deadline)
has median 36.5 days, which is an independent confirmation that the rule logic is
implemented correctly: it lands almost exactly on the observed 39-day median lead.
What the model learns on top is the *emission probability given the gate*, which is
the part the policy table does not contain.

**5. Roughly a third of the label set is genuinely unpredictable, and V3 should
say so.** The 15 labels in class **E** (`FAULT` or `INSPECTION_FINDING`, 5 + 10
labels) are random events conditioned only on a service happening at all. Their
absolute PR-AUC stays in the 0.01–0.08 range. The large "lift over prevalence"
multiples they show in the Phase-10 signal study are an artifact of dividing by a
0.5% base rate; they are not usable predictions, and the product contract flags
them rather than displaying them as confident percentages.

## Verdict

This is **not** generator-rule replication. It is also not a strong observable
signal across the board. The honest characterisation is **mixed**:

- one near-deterministic, high-prevalence label (`ENGINE_OIL_CHANGE`) where ML adds
  little because the rule and the base rate already explain it;
- a middle band of ~28 threshold-gated / bundle-attached labels where ML roughly
  doubles PR-AUC over both the rule and the base rate — this is where the real
  value is;
- ~15 random-event labels that are not learnable from any observable and should be
  reported as such rather than modelled into false confidence.
