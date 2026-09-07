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
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .features import policy_intervals

DAYS_PER_MONTH = 30.4375

#: Lookahead used only to FETCH candidate task rows, never to widen the
#: point-in-time boundary.
#:
#: The V2.1 adapter's ``get_service_tasks_before`` filters task lines by the task's
#: own completion timestamp, but the training feature builder keys history on the
#: parent *service's* arrival date. Those disagree whenever a service straddles
#: midnight -- and that is not rare: 8.6% of v1.4 task lines complete on a later
#: calendar day than their service arrived, across 5,085 of 52,700 services, with a
#: maximum observed gap of 5 days.
#:
#: So candidate rows are fetched with a bounded lookahead and the real gate --
#: parent service ``received_at <= landmark`` -- is applied here. The lookahead
#: cannot admit a task whose service arrived after the landmark, because that
#: service is absent from ``get_services_before`` and the task is dropped.
TASK_FETCH_LOOKAHEAD_DAYS = 7
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


def straddling_history_service(adapter, motorcycle_id: str, landmark: date) -> bool:
    """True when a service that arrived on/before the landmark is still finishing.

    The V2.1 history builder keys its own task-derived features
    (``due_task_count``, ``critical_due_task_count``, ``last_service_task_count``)
    on each task line's completion timestamp, while the V3 training feature builder
    keys history on the parent service's arrival date. When a service arrives late
    in the day and finishes after midnight, the two disagree for that landmark.

    V3 matches the training semantics for every feature it owns, but it cannot
    change the three V2.1-owned columns without mutating a frozen production
    contract. So the condition is detected and reported instead of hidden. It
    affects **48 of 39,451 landmarks (0.12%)**; on those, the served probabilities
    can differ from the research pipeline by up to 0.30 for a single task.
    """
    services = adapter.get_services_before(motorcycle_id, landmark)
    if not services:
        return False
    history = {str(r.get("service_id")) for r in services}
    horizon = landmark + timedelta(days=TASK_FETCH_LOOKAHEAD_DAYS)
    for t in adapter.get_service_tasks_before(motorcycle_id, horizon):
        if str(t.get("service_id")) not in history:
            continue
        effective = t.get("_effective_at")
        if effective and date.fromisoformat(str(effective)[:10]) > landmark:
            return True
    return False


def _completed_task_events(adapter, motorcycle_id: str, landmark: date) -> pd.DataFrame:
    """PIT-safe (task_code, event_at, odometer_km) history, research-exact.

    Tasks are gated on their parent *service* being at or before the landmark, and
    carry the service's arrival date and odometer -- not the task row's own
    timestamps -- because that is what the training feature builder used.
    """
    services = adapter.get_services_before(motorcycle_id, landmark)
    if not services:
        return pd.DataFrame(columns=["task_code", "event_at", "odometer_km", "service_id"])
    # the set of services that are history; this is the binding PIT gate
    
    svc = {}
    for row in services:
        sid = str(row.get("service_id"))
        received = pd.to_datetime(row.get("received_at"), errors="coerce")
        odo = pd.to_numeric(row.get("odometer_km"), errors="coerce")
        if pd.isna(received):
            continue
        svc[sid] = (received.normalize(), float(odo) if pd.notna(odo) else np.nan)

    rows = []
    fetch_until = landmark + timedelta(days=TASK_FETCH_LOOKAHEAD_DAYS)
    for t in adapter.get_service_tasks_before(motorcycle_id, fetch_until):
        if str(t.get("status")) != "COMPLETED":
            continue                       # DECLINED did not reset any interval
        sid = str(t.get("service_id"))
        if sid not in svc:
            # parent service arrived after the landmark (or is unknown) -- this is
            # the point-in-time gate, and it is what the lookahead cannot bypass
            continue
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
    modelled_events = float(counts.sum())
    if not len(events):
        warnings.append("no completed task history at or before the landmark")
    elif modelled_events == 0:
        # the bike has service history, but none of it involves a modelled task, so
        # every history and recency feature sits on its "never performed" sentinel
        warnings.append(
            "bu motosikletin geçmişinde modellenen 44 işlemden hiçbiri yok; "
            "görev geçmişi özellikleri boş kabul edildi")
    if pd.isna(odo_now):
        warnings.append("odometer at landmark unknown; km-since features unavailable")
    straddling = straddling_history_service(adapter, req.motorcycle_id, landmark)
    if straddling:
        warnings.append(
            "Bu landmark, gece yarısını aşan bir servisin içine denk geliyor; "
            "V2.1 kaynaklı üç görev sayacı araştırma hattından farklı olabilir "
            "(landmark'ların %0,12'si).")

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
            "straddling_history_service": bool(straddling),
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
