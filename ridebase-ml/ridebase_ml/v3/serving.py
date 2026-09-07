"""Build the frozen V3 feature vector for one (motorcycle, landmark) from history.

Serving path:

    motorcycle_id + landmark_date
      -> V2.1 read-only source adapter (already audited and shipped for production)
      -> 54-column V2.1 base contract via v2_1.history_features.build_features
      -> V3 task-history, recency and policy-state blocks computed here
      -> the exact 277-column frozen V3 feature contract, in artifact order

Nothing is invented. A task never performed keeps the ``-1`` sentinel the
training builder used; a feature that cannot be reconstructed stays missing and
is counted against ``feature_coverage`` rather than being filled with a plausible
number or borrowed from a sample row.

Point-in-time rules, matching the research builder exactly:

* the task history is gated on the **service** the task belongs to having
  ``received_at <= landmark``, which is the same boundary V2.1 uses to decide
  what the *next* service is. A service received at or before the landmark is by
  definition not the target service. In v1.4 the median service turnaround is
  1.3 hours and 90.7% complete on the arrival day, so "arrived" and "known"
  coincide; that assumption is stated rather than hidden.
* occurrence counts are ordered by ``(task_code, received_at, service_id)`` so
  two task lines on the same day cannot swap and change ``hist_count`` -- the
  same-day shuffle-invariance property fixed during the research leakage audit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .features import policy_intervals

DAYS_PER_MONTH = 30.4375
NEVER_SENTINEL = -1.0
NO_POLICY_SENTINEL = -1.0


class V3HistoryError(ValueError):
    """History could not be reconstructed for this motorcycle/landmark."""


@dataclass
class V3FeatureVector:
    features: dict[str, float | str | None]
    coverage: float
    missing: list[str]
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_frame(self, order: list[str]) -> pd.DataFrame:
        return pd.DataFrame([{c: self.features.get(c) for c in order}], columns=order)


def _completed_task_events(adapter, motorcycle_id: str, landmark: date) -> pd.DataFrame:
    """PIT-safe (task_code, event_at, odometer_km) history, research-exact.

    Tasks are gated on their parent *service* being at or before the landmark, and
    carry the service's arrival date and odometer -- not the task row's own
    timestamps -- because that is what the training feature builder used.
    """
    services = adapter.get_services_before(motorcycle_id, landmark)
    if not services:
        return pd.DataFrame(columns=["task_code", "event_at", "odometer_km", "service_id"])
    svc = {}
    for row in services:
        sid = str(row.get("service_id"))
        received = pd.to_datetime(row.get("received_at"), errors="coerce")
        odo = pd.to_numeric(row.get("odometer_km"), errors="coerce")
        if pd.isna(received):
            continue
        svc[sid] = (received.normalize(), float(odo) if pd.notna(odo) else np.nan)

    rows = []
    for t in adapter.get_service_tasks_before(motorcycle_id, landmark):
        if str(t.get("status")) != "COMPLETED":
            continue                       # DECLINED did not reset any interval
        sid = str(t.get("service_id"))
        if sid not in svc:
            continue                       # parent service is after the landmark
        event_at, odo = svc[sid]
        rows.append({"task_code": str(t.get("task_code")), "event_at": event_at,
                     "odometer_km": odo, "service_id": sid})
    if not rows:
        return pd.DataFrame(columns=["task_code", "event_at", "odometer_km", "service_id"])
    df = pd.DataFrame(rows)
    # deterministic order: same key the training builder uses, so two task lines
    # on one day cannot swap and change the occurrence count
    return df.sort_values(["task_code", "event_at", "service_id"], kind="stable")


def build_v3_features(motorcycle_id: str, landmark_date: Any, adapter,
                      labels: list[str], feature_order: list[str],
                      base_features: dict[str, Any] | None = None) -> V3FeatureVector:
    """Reconstruct the frozen 277-column V3 feature vector at a landmark."""
    from ..v2_1.history_features import build_features as build_v2_1_features
    from ..v2_1.source_contract import HistoryFeatureRequest

    req = HistoryFeatureRequest.parse(motorcycle_id, landmark_date)
    landmark = req.landmark_date

    if base_features is None:
        payload = build_v2_1_features(req.motorcycle_id, landmark, adapter)
        base_features = payload.get("features", payload)
    base = dict(base_features)

    events = _completed_task_events(adapter, req.motorcycle_id, landmark)
    odo_now = pd.to_numeric(base.get("current_odometer_km_at_landmark"), errors="coerce")
    lm_ts = pd.Timestamp(landmark)

    hist: dict[str, float] = {}
    for code in labels:
        g = events.loc[events["task_code"] == code] if len(events) else events
        if len(g) == 0:
            hist[f"hist_count__{code}"] = 0.0
            hist[f"days_since__{code}"] = NEVER_SENTINEL
            hist[f"km_since__{code}"] = NEVER_SENTINEL
            continue
        last = g.iloc[-1]
        hist[f"hist_count__{code}"] = float(len(g))
        hist[f"days_since__{code}"] = float((lm_ts - last["event_at"]).days)
        hist[f"km_since__{code}"] = (
            float(odo_now - last["odometer_km"])
            if pd.notna(odo_now) and pd.notna(last["odometer_km"]) else np.nan)

    counts = np.array([hist[f"hist_count__{c}"] for c in labels], dtype="float64")
    days = np.array([hist[f"days_since__{c}"] for c in labels], dtype="float64")
    seen = days >= 0
    agg = {
        "prior_task_line_total": float(counts.sum()),
        "distinct_prior_tasks": float((counts > 0).sum()),
        "min_days_since_any_task": float(days[seen].min()) if seen.any() else NEVER_SENTINEL,
    }

    pol = _policy_state(base, labels, hist, odo_now)

    merged: dict[str, Any] = {**base, **hist, **agg, **pol}
    values = {c: merged.get(c) for c in feature_order}
    missing = [c for c, v in values.items()
               if v is None or (isinstance(v, float) and not np.isfinite(v))]
    coverage = 1.0 - len(missing) / max(len(feature_order), 1)

    warnings: list[str] = []
    if not len(events):
        warnings.append("no completed task history at or before the landmark")
    if pd.isna(odo_now):
        warnings.append("odometer at landmark unknown; km-since features unavailable")

    return V3FeatureVector(
        features=values, coverage=round(float(coverage), 4), missing=missing,
        warnings=warnings,
        provenance={
            "source": "v2_1_history_adapter",
            "landmark_date": landmark.isoformat(),
            "prior_services_used": int(events["service_id"].nunique()) if len(events) else 0,
            "prior_task_lines_used": int(len(events)),
            "task_history_boundary": "parent service received_at <= landmark",
            "declined_tasks_excluded": True,
        })


def _policy_state(base: dict[str, Any], labels: list[str], hist: dict[str, float],
                  odo_now: float) -> dict[str, float]:
    """F1 block: deterministic OEM due state per task, from the frozen interval table."""
    intervals = policy_intervals()
    group = base.get("policy_group")
    ownership_age = pd.to_numeric(base.get("ownership_age_days"), errors="coerce")
    out: dict[str, float] = {}
    for code in labels:
        km_int, mo_int = intervals.get((group, code), (np.nan, np.nan))
        never = hist[f"hist_count__{code}"] == 0
        km_since = odo_now if never else hist[f"km_since__{code}"]
        d_since = ownership_age if never else hist[f"days_since__{code}"]
        ratios = []
        if pd.notna(km_int) and km_int > 0 and pd.notna(km_since):
            ratios.append(km_since / km_int)
        if pd.notna(mo_int) and mo_int > 0 and pd.notna(d_since):
            ratios.append((d_since / DAYS_PER_MONTH) / mo_int)
        ratio = max(ratios) if ratios else NO_POLICY_SENTINEL
        out[f"policy_due_ratio__{code}"] = float(ratio)
        out[f"policy_overdue__{code}"] = float(ratio >= 1.0)
    return out
