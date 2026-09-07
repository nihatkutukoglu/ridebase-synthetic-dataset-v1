"""V3 label taxonomy discovery and the frozen rare-label policy (Phases 3-4).

The policy is decided on **pre-TEST support only** (TRAIN + VALIDATION). TEST
positive counts are reported as a limitation in the split audit, never used to
choose the label set -- that would be threshold selection against TEST.

Support is always measured over *applicable* rows. A chain task is not "rare"
because most of the fleet is scooters; it is simply inapplicable there, and
mixing the two would exclude labels that are common on the bikes that have the
part. Applicability comes from the taxonomy's own requirement columns.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

#: Frozen Phase-4 gate. Chosen before any TEST evaluation, from the Phase-3
#: inventory. A label must clear every one of these to be modelled in V3.0.
POLICY = {
    "min_applicable_rows": 1000,     # the part must exist on a real slice of the fleet
    "min_positives_dev": 200,        # TRAIN + VALIDATION positives
    "min_positives_validation": 25,  # enough to tune a threshold on at all
    "min_motorcycles": 100,          # not driven by a handful of bikes
    "min_years_covered": 4,          # present across the panel, not a one-year artifact
}
#: Within the modelled set, CORE vs LOW_FREQUENCY is a reporting distinction only
#: -- both are modelled, but LOW_FREQUENCY labels carry a low-support warning.
CORE_MIN_POSITIVES_DEV = 1000
CORE_MIN_PREVALENCE_APPLICABLE = 0.02

#: Labels whose *semantics* in this synthetic world do not match their canonical
#: meaning. Flagged for review; they are not silently merged or renamed.
AMBIGUOUS_NOTES = {
    "OIL_FILTER_CHANGE": (
        "Canonically an oil-change companion task, and the V3 brief's example "
        "output shows it at 0.84. In v1.4 it has 40 positives against 34,762 "
        "ENGINE_OIL_CHANGE positives, i.e. the generator does not couple them. "
        "Excluded on support; the mismatch is a data-semantics finding, not a "
        "modelling choice."
    ),
    "DRIVE_BELT_INSPECTION": (
        "Eligible in the taxonomy but zero observed positives -- only 21 rows "
        "have a BELT (non-V_BELT) final drive. Unobservable, not rare."
    ),
    "EV_DRIVE_MOTOR_DIAGNOSTIC": (
        "Zero observed positives across 37 applicable rows. EV coverage in v1.4 "
        "is too thin to model any EV-specific task."
    ),
    "FINAL_DRIVE_FAULT_INSPECTION": (
        "A single positive in the entire dataset, in TEST only. Excluded."
    ),
}


def classify(inventory: pd.DataFrame) -> pd.DataFrame:
    """Apply the frozen gate to a Phase-3 inventory frame."""
    inv = inventory.copy()
    gate = (
        (inv["applicable_rows"] >= POLICY["min_applicable_rows"])
        & (inv["pos_dev"] >= POLICY["min_positives_dev"])
        & (inv["pos_val"] >= POLICY["min_positives_validation"])
        & (inv["motorcycles"] >= POLICY["min_motorcycles"])
        & (inv["years_covered"] >= POLICY["min_years_covered"])
    )
    core = gate & (inv["pos_dev"] >= CORE_MIN_POSITIVES_DEV) & (
        inv["prevalence_applicable"] >= CORE_MIN_PREVALENCE_APPLICABLE)
    inv["label_class"] = "C_TOO_RARE_FOR_MODELING"
    inv.loc[gate, "label_class"] = "B_LOW_FREQUENCY"
    inv.loc[core, "label_class"] = "A_CORE"
    inv["needs_review"] = inv["task_code"].isin(AMBIGUOUS_NOTES)
    inv["modeled"] = gate
    checks = [
        ("applicable_rows", "min_applicable_rows"),
        ("pos_dev", "min_positives_dev"),
        ("pos_val", "min_positives_validation"),
        ("motorcycles", "min_motorcycles"),
        ("years_covered", "min_years_covered"),
    ]
    inv["exclusion_reason"] = [
        "" if ok else "; ".join(
            f"{col}={row[col]} < {POLICY[key]}" for col, key in checks
            if row[col] < POLICY[key])
        for ok, (_, row) in zip(gate, inv.iterrows())
    ]
    return inv


def load_label_set(path: str | Path) -> list[str]:
    return json.loads(Path(path).read_text())["labels"]
