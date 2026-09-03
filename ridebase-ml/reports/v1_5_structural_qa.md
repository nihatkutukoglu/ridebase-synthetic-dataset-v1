# RideBase V1.5 structural generator gate

**GATE 2: PASS.** V1.5 is a separate synthetic behavior world; V1.4 remains immutable.

- Source schema: unchanged `1.3.0` contract across 13 tables
- Seed: 52; step: 3 days
- New delivered services: 23,467
- New no-shows: 2,075
- New cancellations: 1,835
- Churn/non-return censor events: 172
- Services following a miss within 90 days: 2,525
- Latent archetypes represented in audit only: 8/8
- Schema, primary key, foreign key, timestamp order, service odometer monotonicity, observation-window, and policy mapping checks: PASS
- Source tables contain no latent-profile column: PASS
- Complete second regeneration source hashes: exact match
- Frozen V1.3 and V1.4 source hashes before/after: unchanged

V1.5 branches from the same frozen V1.3 core used by V1.4, replacing only the synthetic tail-generating hypothesis in a separate output directory. This makes V1.4-versus-V1.5 generator comparisons interpretable without stacking two synthetic event processes.

These are synthetic behavioral assumptions and are not validated on real RideBase fleet data.
