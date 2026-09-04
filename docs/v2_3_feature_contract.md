# V2.3 Observable Behavior-State Feature Contract

V2.3 appends 35 point-in-time observable summaries to the frozen V2.2 EXTENDED60 contract. Latent generator profiles, outcomes after the landmark, absolute year, split, target/censor fields and `days_observed` are forbidden.

| Feature | Group | Source | Formula / cutoff | Missing |
|---|---|---|---|---|
| `appointments_180d` | appointment | appointments.csv | count scheduled appointments in [landmark-179d, landmark] created by landmark; effective timestamp <= landmark | 0 means no qualifying observed history |
| `attended_appointment_count` | appointment | appointments.csv | count prior appointments converted to service; effective timestamp <= landmark | 0 means no qualifying observed history |
| `no_show_rate` | appointment | appointments.csv | prior no-show count / prior completed appointment count; 0 with no history; effective timestamp <= landmark | 0 means no qualifying observed history |
| `cancellation_rate` | appointment | appointments.csv | prior cancellation count / prior completed appointment count; 0 with no history; effective timestamp <= landmark | 0 means no qualifying observed history |
| `successful_appointment_rate` | appointment | appointments.csv | prior converted count / prior completed appointment count; 0 with no history; effective timestamp <= landmark | 0 means no qualifying observed history |
| `rebook_after_no_show_rate` | appointment | appointments.csv | prior no-shows followed by a new appointment creation by landmark / prior no-shows; effective timestamp <= landmark | 0 means no qualifying observed history |
| `days_since_last_appointment` | appointment | appointments.csv | landmark minus latest prior scheduled appointment date; effective timestamp <= landmark | NaN when no prior scheduled appointment |
| `known_open_appointment_count` | appointment | appointments.csv | created by landmark and scheduled after landmark; outcome ignored; effective timestamp <= landmark | 0 means no qualifying observed history |
| `recent_no_show_without_rebook` | appointment | appointments.csv | 1 when a no-show in prior 180d has no later creation by landmark; effective timestamp <= landmark | 0 means no qualifying observed history |
| `overdue_service_share` | adherence | services.csv | share of completed services with positive recorded pre-service overdue days or km; effective timestamp <= landmark | 0 means no qualifying observed history |
| `prior_service_delay_median` | adherence | services.csv | median service_delay_days over completed prior services; effective timestamp <= landmark | 0 means no qualifying observed history |
| `prior_service_delay_p90` | adherence | services.csv | 90th percentile service_delay_days over completed prior services; effective timestamp <= landmark | 0 means no qualifying observed history |
| `last3_service_delay_trend` | adherence | services.csv | OLS slope by order over the last three completed service delays; effective timestamp <= landmark | 0 means no qualifying observed history |
| `interservice_days_cv` | adherence | services.csv | coefficient of variation of completed-service date gaps; 0 with <3 services; effective timestamp <= landmark | 0 means no qualifying observed history |
| `interservice_km_cv` | adherence | services.csv | coefficient of variation of positive odometer gaps; 0 with <3 services; effective timestamp <= landmark | 0 means no qualifying observed history |
| `recency_weighted_adherence_score` | adherence | services.csv | exp(-age/365)-weighted share with delay <= 0; 0.5 with no history; effective timestamp <= landmark | 0 means no qualifying observed history |
| `service_gap_acceleration` | adherence | services.csv | last completed-service day gap / prior-gap mean - 1; 0 with <3 services; effective timestamp <= landmark | 0 means no qualifying observed history |
| `days_since_last_any_interaction` | engagement | appointments.csv + services.csv | landmark minus latest appointment creation or service delivery; effective timestamp <= landmark | NaN when no prior appointment creation or completed service |
| `interaction_count_90d` | engagement | appointments.csv + services.csv | appointment creations plus service deliveries in prior 90d; effective timestamp <= landmark | 0 means no qualifying observed history |
| `interaction_count_180d` | engagement | appointments.csv + services.csv | appointment creations plus service deliveries in prior 180d; effective timestamp <= landmark | 0 means no qualifying observed history |
| `appointment_frequency_365d` | engagement | appointments.csv + services.csv | appointment creations in prior 365d; effective timestamp <= landmark | 0 means no qualifying observed history |
| `distinct_workshops_before_landmark` | workshop | services.csv | distinct workshops across completed prior services; effective timestamp <= landmark | 0 means no qualifying observed history |
| `dominant_workshop_share` | workshop | services.csv | largest completed-service workshop share; 0 with no history; effective timestamp <= landmark | 0 means no qualifying observed history |
| `same_workshop_streak` | workshop | services.csv | consecutive completed services at the most recent workshop; effective timestamp <= landmark | 0 means no qualifying observed history |
| `recent_30d_km` | usage | mileage_timeline_monthly.csv | sum monthly km_added for observations ending in prior 30d; effective timestamp <= landmark | 0 means no qualifying observed history |
| `recent_180d_km` | usage | mileage_timeline_monthly.csv | sum monthly km_added for observations ending in prior 180d; effective timestamp <= landmark | 0 means no qualifying observed history |
| `usage_velocity_ratio_30_vs_180` | usage | mileage_timeline_monthly.csv | 30d daily km / 180d daily km; 0 when 180d km is zero; effective timestamp <= landmark | 0 means no qualifying observed history |
| `usage_volatility_6m` | usage | mileage_timeline_monthly.csv | coefficient of variation of last six observed monthly km values; effective timestamp <= landmark | 0 means no qualifying observed history |
| `odometer_observation_recency_days` | usage | mileage_timeline_monthly.csv | landmark minus latest completed mileage period end; effective timestamp <= landmark | NaN when no completed monthly observation |
| `km_growth_slope_6m` | usage | mileage_timeline_monthly.csv | OLS slope per observation over last six monthly km values; effective timestamp <= landmark | 0 means no qualifying observed history |
| `breakdown_count_90d` | breakdown | services.csv | completed breakdown services in prior 90d; effective timestamp <= landmark | 0 means no qualifying observed history |
| `repair_count_90d` | breakdown | services.csv | completed REPAIR services in prior 90d; effective timestamp <= landmark | 0 means no qualifying observed history |
| `safety_critical_repair_recent` | breakdown | services.csv | 1 for HIGH/CRITICAL completed failure in prior 180d; effective timestamp <= landmark | 0 means no qualifying observed history |
| `days_since_last_breakdown` | breakdown | services.csv | landmark minus latest completed breakdown; effective timestamp <= landmark | NaN when no prior completed breakdown |
| `repeated_breakdown_flag` | breakdown | services.csv | 1 for at least two completed breakdowns in prior 365d; effective timestamp <= landmark | 0 means no qualifying observed history |

Every retained feature is available from the same raw history tables in production. Appointment final outcomes are used only after `scheduled_at <= landmark`; an open future appointment is represented solely when `created_at <= landmark`, and its future status is ignored.
