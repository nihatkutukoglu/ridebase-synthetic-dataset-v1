# V2.2 dynamic-landmark dataset audit

**GATE 4: PASS.**

Rows: 259,804; motorcycles: 9,212; features: 60 (frozen V2.1 54 + six observable point-in-time history fields).
Events: 225,279; censored: 34,525.

The six additions are prior appointment/no-show/cancellation counts, known appointment intent within 30 days, days to that known appointment, and recent 180-day breakdown count. Appointment outcomes after a landmark are not used.

## Integrity checks

- PASS — `landmark_builder_quality`
- PASS — `source_schema_unchanged`
- PASS — `feature_count_expected`
- PASS — `forbidden_feature_scan`
- PASS — `identifier_shortcuts_absent`
- PASS — `no_absolute_year`
- PASS — `no_split_feature`
- PASS — `no_latent_profile_feature`
- PASS — `unique_landmarks`
- PASS — `positive_duration`
- PASS — `event_binary`
- PASS — `observed_has_next_service`
- PASS — `censored_has_no_next_service`
- PASS — `horizon_targets_monotone`
- PASS — `train_end_respected`
- PASS — `validation_end_respected`
- PASS — `test_start_respected`
- PASS — `unseen_motorcycles_isolated`
- PASS — `output_hashes_match`
- PASS — `test_not_used_for_selection`

## Drift versus V2.1/V1.4

Maximum absolute standardized numeric mean difference: 0.4595.
Maximum categorical total-variation distance: 0.0617.
This is expected synthetic-world drift and was measured before TEST model evaluation.

TEST remains sealed for selection; TRAIN+VALIDATION only may choose the challenger and VALIDATION alone may choose calibration.
