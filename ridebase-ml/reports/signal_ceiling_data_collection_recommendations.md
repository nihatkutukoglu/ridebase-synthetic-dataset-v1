# RideBase Data-Value & Real-World Collection Recommendations

## Executive Context
The Signal Ceiling & Oracle Gap Study demonstrates that feature engineering from existing transactional tables has hit diminishing returns:
- Expanding from 60 observable features (Tier O1) to 95 observable features (Tier O2) yielded an IPCW C-index improvement of only **+0.000098** on validation.
- Even perfect access to latent traits and generator dynamic hazards (Tier M4 Oracle) only lifted C-index by **+0.010216** (from 0.7367 to 0.7469), because **~89.6% of prediction variance is irreducible aleatoric noise** in the event generation process.
- The residual epistemic gap is heavily concentrated in **unobserved churn, off-platform servicing, and appointment friction**.

To break through this ceiling in real-world fleet deployments, RideBase should **not** engage in further ad-hoc feature expansion on the same operational database schemas. Instead, RideBase should prioritize collecting **genuine operational signals** that directly observe customer engagement, reminder responses, and vehicle status.

---

## Ranked Real-World Data Collection Recommendations

| Priority | Recommended Operational Signal | Latent Behavioral Gap Addressed | Expected Information Value | Implementation Complexity | Privacy / Sensitivity Impact | Collection Mechanism |
|:---:|---|---|:---:|:---:|:---:|---|
| **1** | **Explicit Cancellation & No-Show Reasons** | `oracle_latent_no_show_tendency`, `adherence` | **HIGH** | Low | Low (operational survey/dropdown) | Add mandatory structured reason code in CRM/App when an appointment is cancelled or missed (e.g. *Rescheduled*, *Serviced Elsewhere*, *Bike Sold*, *Financial/Price*). |
| **2** | **Maintenance Reminder Engagement Signals** | `oracle_latent_adherence`, `churn_tendency` | **HIGH** | Medium | Low (opt-in app/SMS telemetry) | Track timestamped reminder delivery, open event, click-through, and appointment booking conversion from digital service notifications. |
| **3** | **Vehicle Inactivity / Ownership Transfer Indicator** | `oracle_latent_is_churned_at_landmark` | **HIGH** | Medium | Medium (ownership declaration) | Allow customer or workshop to flag motorcycle as *Inactive/Stored*, *Sold/Transferred*, or *Stolen*, preventing false "extreme overdue" predictions on departed bikes. |
| **4** | **Off-Platform Servicing Self-Report** | `oracle_latent_churn_tendency`, `loyalty` | **MEDIUM–HIGH** | Low–Medium | Low (customer incentive/warranty book) | Digital maintenance log allowing riders to upload external oil/tire change receipts, resetting the overdue interval. |
| **5** | **Periodic Odometer Sync (Bluetooth/Telemetry/App)** | `km_ratio`, usage volatility | **MEDIUM** | Medium–High | Medium (consented vehicle telemetry) | Low-frequency Bluetooth odometer ping from rider mobile app or OBD dongle to avoid stale odometer estimates. |
| **6** | **Multi-Workshop Search & Lead Inquiry Telemetry** | `oracle_latent_loyalty`, `price_sensitivity` | **MEDIUM** | Medium | Low (anonymized web/app search logs) | Log workshop profile views, quote requests, and price inquiries across the RideBase dealer network. |

---

## What NOT to Collect
- **Forbidden**: Raw personal demographic data, social media scrapers, or intrusive real-time GPS tracking.
- **Forbidden**: Synthetic latent labels (which cannot exist in real physical operations).
- **Guiding Principle**: Focus strictly on **consented, operational interactions** around vehicle maintenance, appointment lifecycle, and communication feedback.
