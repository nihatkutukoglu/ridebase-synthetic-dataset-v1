# RideBase Maintenance Urgency Policy Audit Report

**Date:** 2026-09-04  
**Audit Target:** Deterministic maintenance policy engine in `ridebase-v1-dashboard/backend/app/v2_scenario.py` and `ridebase-control-center/template.html`

---

## 1. Existing Policy Implementation Analysis

The deterministic maintenance evaluation is implemented in `_maintenance_assessment(req, model)` in `app/v2_scenario.py` (lines 278–360).

### Inputs Required
- `current_odometer_km`
- `last_service_odometer_km`
- `last_service_date`
- `maintenance_policy`: Resolved from `maintenance_policies.csv` or catalog override (e.g. Bajaj NS200: 3,000 km / 182.6 days).

If any of the three historical/odometer inputs are missing, `service_history_complete` is `False` and maintenance status is `UNKNOWN`.

### Metrics & Formulas

| Metric | Code Formula | Semantics |
|---|---|---|
| **`km_since_service`** | `current_odometer_km - last_service_odometer_km` | Total distance covered since last service event |
| **`days_since_service`** | `(snapshot_date - last_service_date).days` | Total elapsed calendar days since last service |
| **`km_ratio`** | `km_since_service / interval_km` | Proportion of distance maintenance interval consumed |
| **`day_ratio`** | `days_since_service / interval_days` | Proportion of calendar maintenance interval consumed |
| **`progress_ratio`** | `max(km_ratio, day_ratio)` | Dominant interval consumption ratio |
| **`progress_pct`** | `progress_ratio * 100.0` | Percentage of maintenance interval consumed |
| **`driving_metric`** | `"KM"` if `km_ratio >= day_ratio` else `"DAYS"` | Dimension currently driving the maintenance decision |
| **`overdue_km`** | `max(0.0, km_since_service - interval_km)` | Excess kilometers beyond the OEM maintenance threshold |
| **`overdue_days`** | `max(0.0, days_since_service - interval_days)` | Excess calendar days beyond the OEM time threshold |
| **`remaining_km`** | `max(0.0, interval_km - km_since_service)` | Distance remaining until scheduled service |
| **`remaining_days`** | `max(0.0, interval_days - days_since_service)` | Days remaining until scheduled service |

### Existing State Classifications

| Threshold | State (`status`) | Label (`label`) | Action Label (`action_label`) |
|---|---|---|---|
| `progress_ratio < 0.80` | `NOT_DUE` | `BAKIM PERİYODU İÇİNDE` | `HEMEN SERVİS GEREKMİYOR` |
| `0.80 <= progress_ratio < 1.00` | `DUE_SOON` | `BAKIM YAKLAŞIYOR` | `SERVİSİ PLANLA` |
| `progress_ratio >= 1.00` | `OVERDUE` | `BAKIM GECİKMİŞ` | `SERVİS ŞİMDİ GEREKLİ` |

---

## 2. Policy Decoupling Confirmation

- The deterministic policy state (`OVERDUE`, `DUE_SOON`, `NOT_DUE`) is **100% independent** of machine learning models.
- The new **Maintenance Urgency Score (0–100)** must derive strictly from these exact same quantities (`progress_ratio`, `overdue_km`, `overdue_days`, `driving_metric`, `interval_km`, `interval_days`).
- No secondary or conflicting policy calculation will be introduced.
