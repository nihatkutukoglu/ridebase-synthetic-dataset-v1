"""V3 point-in-time feature construction.

Every feature here is computed from events with ``received_at <= landmark_at``.
Nothing reads the target service. The one structural guarantee that makes this
checkable is that all history joins go through :func:`_asof_last`, which is a
backward ``merge_asof`` -- it is not *possible* for a row dated after the
landmark to be selected. Phase 8 verifies this empirically by injecting fake
post-landmark services and asserting the feature matrix is byte-identical.

Feature blocks (used by the Phase 19 ablation):

F0  base   -- motorcycle identity-free attributes, odometer, time/km since last
              service. Inherited from the frozen V2.1 54-column contract.
F1  policy -- deterministic OEM maintenance state per task code at the landmark
              (``policy_due_ratio__X``, ``policy_overdue__X``).
F2  hist   -- per-task prior occurrence counts and share of prior services.
F3  recency-- per-task days/km since that task was last performed.
F4  behav  -- observable service/appointment behaviour aggregates.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .sources import load_sources
from .target import eligible_taxonomy

#: the 54-column V2.1 PIT-safe contract, reused verbatim as V3's F0 base
BASE_CATEGORICAL = [
    "brand", "category", "powertrain_type", "policy_group", "customer_type",
    "usage_type", "riding_intensity", "climate_zone", "storage_condition",
    "workshop_region", "workshop_price_level", "last_service_type_code",
    "last_arrival_mode",
]
BASE_NUMERIC = [
    "production_age_days", "ownership_age_days", "is_fleet_customer",
    "current_odometer_km_at_landmark", "annual_km_baseline", "recent_90d_km",
    "recent_vs_baseline_usage_ratio", "days_since_last_service",
    "km_since_last_service", "avg_km_per_day_since_last_service",
    "oem_interval_days", "oem_interval_km", "days_due_ratio", "km_due_ratio",
    "max_due_ratio", "days_overdue", "km_overdue", "maintenance_due_now",
    "due_task_count", "critical_due_task_count", "days_until_next_scheduled_due",
    "km_until_next_scheduled_due", "landmark_month_sin", "landmark_month_cos",
]
#: F4 behavioural block -- also from the V2.1 contract, but split out so the
#: ablation can measure what broader behaviour history adds over task history.
BEHAVIOURAL_NUMERIC = [
    "recent_service_count_90d", "recent_service_count_365d", "prior_service_count",
    "prior_periodic_service_count", "prior_breakdown_count", "prior_repair_count",
    "historical_service_delay_mean_days", "historical_on_time_rate",
    "cumulative_service_spend", "last_service_was_breakdown",
    "last_service_was_warranty", "last_service_task_count", "last_service_spend",
    "service_bay_count", "appointment_rate", "avg_parts_lead_days",
    "customer_volume_index",
]

_DAY = np.timedelta64(1, "D")


def task_event_log(root: str | None = None) -> pd.DataFrame:
    """Every performed task line as (motorcycle, task, date, odometer).

    This is the raw substrate for both the history features and the policy
    state. Only ``status = COMPLETED`` lines are events -- a declined
    recommendation did not reset any maintenance interval.
    """
    src = load_sources(root)
    st = src["service_tasks"]
    sv = src["services"][["service_id", "received_at", "odometer_km"]].copy()
    sv["event_at"] = pd.to_datetime(sv["received_at"], format="mixed").dt.normalize()
    codes = set(eligible_taxonomy(root)["task_code"])
    ev = st.loc[(st["status"] == "COMPLETED") & st["task_code"].isin(codes),
                ["service_id", "motorcycle_id", "task_code"]]
    ev = ev.merge(sv[["service_id", "event_at", "odometer_km"]], on="service_id", how="left")
    return ev.sort_values("event_at").reset_index(drop=True)


def _asof_last(landmarks: pd.DataFrame, events: pd.DataFrame,
               by: str, value_cols: list[str]) -> pd.DataFrame:
    """Backward as-of join: for each landmark, the last event at or before it.

    ``merge_asof(direction="backward")`` cannot select a row with
    ``event_at > landmark_at``. This is the single choke point through which all
    V3 history flows, which is what makes the Phase 8 injection test meaningful.
    """
    left = landmarks[["_row", by, "landmark_at"]].sort_values("landmark_at", kind="stable")
    # stable sort matters: when a motorcycle has two events of the same task on
    # the same day, merge_asof returns the last tied row, and only a stable sort
    # guarantees that is the one with the highest occurrence index
    right = events[[by, "event_at", *value_cols]].sort_values("event_at", kind="stable")
    joined = pd.merge_asof(
        left, right, by=by, left_on="landmark_at", right_on="event_at",
        direction="backward", allow_exact_matches=True,
    )
    # merge_asof requires a globally sorted left frame; restore caller order so
    # every feature block lines up positionally with ``landmarks``
    return joined.set_index("_row").reindex(landmarks["_row"].to_numpy())


def task_history_features(landmarks: pd.DataFrame, labels: list[str],
                          root: str | None = None,
                          events: pd.DataFrame | None = None) -> pd.DataFrame:
    """F2 + F3: per-task prior occurrence count, days since, and km since.

    ``landmarks`` must carry ``_row``, ``motorcycle_id``, ``landmark_at`` and
    ``current_odometer_km_at_landmark``.

    ``events`` overrides the real task event log. It exists so the Phase-8 audit
    can inject fabricated post-landmark events and assert the feature matrix does
    not move; production callers always leave it None.
    """
    ev = task_event_log(root) if events is None else events
    ev = ev.loc[ev["task_code"].isin(labels)].copy()
    # sort by (motorcycle, task, date, service) so the occurrence index is a
    # deterministic function of the data rather than of row arrival order
    ev = ev.sort_values(["motorcycle_id", "task_code", "event_at", "service_id"],
                        kind="stable")
    # running per-(motorcycle, task) occurrence index: the as-of join then reads
    # off how many times the task had been performed as of the landmark
    ev["prior_n"] = ev.groupby(["motorcycle_id", "task_code"], sort=False).cumcount() + 1
    ev = ev.sort_values("event_at", kind="stable")

    lm = landmarks[["_row", "motorcycle_id", "landmark_at",
                    "current_odometer_km_at_landmark"]].copy()
    lm_at = lm.set_index("_row")["landmark_at"]
    lm_km = lm.set_index("_row")["current_odometer_km_at_landmark"]

    order = lm["_row"].to_numpy()
    cols: dict[str, np.ndarray] = {}
    for code, grp in ev.groupby("task_code", sort=False):
        j = _asof_last(lm, grp, by="motorcycle_id", value_cols=["prior_n", "odometer_km"])
        cols[f"hist_count__{code}"] = j["prior_n"].fillna(0.0).to_numpy(dtype="float64")
        cols[f"days_since__{code}"] = (
            (lm_at.loc[j.index].to_numpy() - j["event_at"].to_numpy()) / _DAY
        ).astype("float64")
        cols[f"km_since__{code}"] = (
            lm_km.loc[j.index].to_numpy() - j["odometer_km"].to_numpy()
        ).astype("float64")
        assert np.array_equal(j.index.to_numpy(), order), "as-of join reordered rows"

    out = pd.DataFrame(cols, index=order)
    # A task never performed gets -1, not 0: "never done" and "done today" are
    # opposite states and must not collide. hist_count == 0 marks the same rows
    # for linear models that cannot split on the sentinel.
    for c in out.columns:
        if c.startswith(("days_since__", "km_since__")):
            out[c] = out[c].fillna(-1.0)
    # a task in the label set that never appears in the event log still needs
    # its columns, so every feature matrix has the same shape
    for code in labels:
        for prefix, fill in (("hist_count__", 0.0), ("days_since__", -1.0), ("km_since__", -1.0)):
            if f"{prefix}{code}" not in out.columns:
                out[f"{prefix}{code}"] = fill
    return out.reindex(landmarks["_row"].to_numpy())


def policy_intervals(root: str | None = None) -> dict[tuple[str, str], tuple[float, float]]:
    """(policy_group, task_code) -> (recurring_km, recurring_months).

    Wear-based policies have no recurring_km, so their ``wear_mean_km`` is used
    as the nominal interval. MODEL-scope rows override GROUP-scope rows for the
    same pair. This is the single source of the deterministic rule layer -- both
    the F1 policy features and the Phase-11 rule baselines read it.
    """
    pol = load_sources(root)["maintenance_policies"]
    pol = pol.loc[pol["is_generator_active"] == 1]
    out: dict[tuple[str, str], tuple[float, float]] = {}
    for _, r in pol.iterrows():
        key = (r["policy_group"], r["task_code"])
        km = r["recurring_km"] if pd.notna(r["recurring_km"]) else r.get("wear_mean_km")
        if key not in out or r["scope_type"] == "MODEL":
            out[key] = (float(km) if pd.notna(km) else np.nan,
                        float(r["recurring_months"]) if pd.notna(r["recurring_months"]) else np.nan)
    return out


def policy_state_features(landmarks: pd.DataFrame, labels: list[str],
                          hist: pd.DataFrame, root: str | None = None) -> pd.DataFrame:
    """F1: deterministic OEM maintenance state per task code at the landmark.

    For each (policy_group, task_code) with a recurring km and/or month interval,
    the due ratio is ``max(km_since / recurring_km, months_since / recurring_months)``
    under ``WHICHEVER_FIRST`` semantics. Tasks never performed before fall back to
    the odometer / ownership age at landmark, matching the generator's initial
    trigger. Wear-based policies use ``wear_mean_km`` as the nominal interval.

    This block *is* the rule layer. Baseline 1 (Phase 11) uses it alone.
    """
    interval = policy_intervals(root)

    lm = landmarks[["_row", "policy_group", "current_odometer_km_at_landmark",
                    "ownership_age_days"]].reset_index(drop=True)
    groups = lm["policy_group"].to_numpy()
    out = {}
    for code in labels:
        km_int = np.array([interval.get((g, code), (np.nan, np.nan))[0] for g in groups], dtype="float64")
        mo_int = np.array([interval.get((g, code), (np.nan, np.nan))[1] for g in groups], dtype="float64")
        km_since = hist[f"km_since__{code}"].to_numpy()
        d_since = hist[f"days_since__{code}"].to_numpy()
        never = hist[f"hist_count__{code}"].to_numpy() == 0
        # never performed: measure against the bike's own odometer / ownership age
        km_since = np.where(never, lm["current_odometer_km_at_landmark"].to_numpy(), km_since)
        d_since = np.where(never, lm["ownership_age_days"].to_numpy(), d_since)
        with np.errstate(invalid="ignore", divide="ignore"):
            km_ratio = np.where(km_int > 0, km_since / km_int, np.nan)
            mo_ratio = np.where(mo_int > 0, (d_since / 30.4375) / mo_int, np.nan)
        stacked = np.vstack([km_ratio, mo_ratio])
        # a task with no policy on either axis is an all-NaN column -> -1 below
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            ratio = np.nanmax(stacked, axis=0)
        ratio = np.where(np.isfinite(ratio), ratio, -1.0)  # -1 == no policy for this pair
        out[f"policy_due_ratio__{code}"] = ratio
        out[f"policy_overdue__{code}"] = (ratio >= 1.0).astype("float64")
    return pd.DataFrame(out, index=landmarks["_row"].to_numpy())


def aggregate_task_features(hist: pd.DataFrame, labels: list[str]) -> pd.DataFrame:
    """Cheap cross-task summaries: how much task history exists at all."""
    cnt = hist[[f"hist_count__{c}" for c in labels]].to_numpy()
    days = hist[[f"days_since__{c}" for c in labels]].to_numpy()
    seen = days >= 0
    return pd.DataFrame({
        "prior_task_line_total": cnt.sum(axis=1),
        "distinct_prior_tasks": (cnt > 0).sum(axis=1),
        "min_days_since_any_task": np.where(seen.any(axis=1),
                                            np.where(seen, days, np.inf).min(axis=1), -1.0),
    }, index=hist.index)
