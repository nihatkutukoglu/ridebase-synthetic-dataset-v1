"""V3 target contract: what counts as the target service, and what counts as a label.

Contract (frozen in ``config/v3_target_contract.json``):

LANDMARK      an end-of-month observation point for one motorcycle, inherited
              unchanged from the V2.1 dynamic-landmark grid.

TARGET SERVICE  the first service the motorcycle arrives at strictly after the
              landmark, within the motorcycle's administrative observation
              window. In the v1.4 world every service row has
              ``status = DELIVERED``, so every service is a completed service:
              arrival implies completion (median 1.3 h, 90.7% same calendar day).
              A landmark with no such service is right-censored and is NOT a
              training row -- the target would be unknown, not negative.

TARGET LABEL  a task code recorded on the target service with
              ``status = COMPLETED`` (equivalently ``completed = 1``).
              DECLINED task lines are recommended-but-not-performed and are
              explicitly NEGATIVE, because the V3 product question is which
              tasks *will be performed*.

Event types that never produce a service row in v1.4 -- CANCELLED (2,552),
NO_SHOW (2,052) and RESCHEDULED (844) appointments -- therefore cannot be a
target service. An appointment only becomes a target when it is
``CONVERTED_TO_SERVICE``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .sources import load_sources, motorcycle_specs

#: service_type_code values that are eligible target services. All four are
#: real completed visits where work was performed; the product question is
#: "at the customer's next visit, what gets done", not "at the next *periodic*
#: visit". Restricting to PERIODIC would make the label conditional on an
#: event type that is itself unknown at landmark.
ELIGIBLE_SERVICE_TYPES = ("PERIODIC", "REPAIR", "TIRE", "BREAKDOWN")

#: task-line statuses that count as "performed"
PERFORMED_STATUS = "COMPLETED"


def eligible_taxonomy(root: str | None = None) -> pd.DataFrame:
    """Task codes the taxonomy itself declares can be a next-service target."""
    mt = load_sources(root)["maintenance_tasks"]
    return mt.loc[mt["can_be_next_service_target"] == 1].reset_index(drop=True)


def applicability_matrix(motorcycle_ids: pd.Index, task_codes: list[str],
                         root: str | None = None) -> pd.DataFrame:
    """Boolean (motorcycle x task) matrix: is this task physically applicable?

    A chain task on a CVT scooter, or an EV battery check on an ICE bike, is not
    a miss the model should be scored on. Applicability is decided purely from
    the taxonomy's own requirement columns joined to the motorcycle's hardware
    spec -- no learned or generator-internal information.
    """
    tax = eligible_taxonomy(root).set_index("task_code")
    tax = tax.loc[[c for c in task_codes if c in tax.index]]
    spec = motorcycle_specs(root).set_index("motorcycle_id")
    spec = spec.reindex(motorcycle_ids)

    out = pd.DataFrame(True, index=spec.index, columns=list(tax.index))
    checks = (
        ("applicable_powertrain", "powertrain_type", ("BOTH",)),
        ("required_final_drive", "final_drive_type", ()),
        ("required_cooling_type", "cooling_type", ()),
        ("required_transmission_type", "transmission_type", ()),
    )
    for tax_col, spec_col, wildcard in checks:
        req = tax[tax_col]
        for code, need in req.items():
            if pd.isna(need) or need in wildcard:
                continue  # no requirement on this axis
            out[code] &= spec[spec_col].eq(need).to_numpy()
    return out


def performed_task_matrix(root: str | None = None) -> pd.DataFrame:
    """Multi-hot (service_id x task_code) of tasks PERFORMED on each service."""
    src = load_sources(root)
    st = src["service_tasks"]
    codes = set(eligible_taxonomy(root)["task_code"])
    done = st.loc[(st["status"] == PERFORMED_STATUS) & st["task_code"].isin(codes),
                  ["service_id", "task_code"]]
    mat = pd.crosstab(done["service_id"], done["task_code"]).astype("int8")
    return mat.clip(upper=1)


def service_index(root: str | None = None) -> pd.DataFrame:
    """Per-service facts V3 needs about a *target* service (never used as a feature)."""
    sv = load_sources(root)["services"]
    out = sv[["service_id", "motorcycle_id", "service_type_code", "is_breakdown",
              "is_warranty", "odometer_km"]].copy()
    out["received_at"] = pd.to_datetime(sv["received_at"], format="mixed").dt.normalize()
    out["completed_at"] = pd.to_datetime(sv["completed_at"], format="mixed")
    out["eligible_target"] = out["service_type_code"].isin(ELIGIBLE_SERVICE_TYPES)
    return out
