# RideBase V2.1 Synthetic Sanity Gate

**Verdict: FAIL. Model training allowed: FALSE.**

Landmarks: 251,054; motorcycles: 8,420; events: 140,860; censored: 110,194.

## Due-state behavior

| due_state        |   landmarks |   event_30d_rate |   event_90d_rate |   eventual_event_rate |
|:-----------------|------------:|-----------------:|-----------------:|----------------------:|
| NOT_DUE          |      159866 |       0.116836   |        0.362864  |            0.721066   |
| NEAR_DUE         |       34993 |       0.298734   |        0.552313  |            0.592061   |
| OVERDUE          |       23444 |       0.116328   |        0.203563  |            0.19425    |
| SEVERELY_OVERDUE |       32751 |       0.00670802 |        0.0121322 |            0.00958749 |

## Gate checks

- PASS — `source_schema_unchanged`
- PASS — `feature_hygiene_passed`
- PASS — `maintenance_pressure_not_deterministic`
- FAIL — `overdue_direction_physically_coherent`
- FAIL — `severely_overdue_not_dead_region`
- PASS — `breakdown_noise_present`
- PASS — `landmark_coverage_adequate`

## Conclusion

STOP BEFORE MODELING: the frozen v1.3 synthetic event process creates a severe overdue dead region; increasing due pressure is associated with sharply lower near-term return. A versioned same-schema synthetic event generator must be designed before V2.1 training can be valid.
