"""V3 Phase-8 leakage audit.

Three independent checks, any of which failing blocks training:

1. **Name and identity screen** -- no target-derived token, no identifier, and no
   generator latent variable may appear as a feature column.
2. **Future-injection invariance** -- fabricated services and task lines dated
   *after* each landmark are appended to the event log, the whole feature matrix
   is rebuilt, and it must come back byte-identical. This is the check that
   actually proves point-in-time safety, because it does not depend on anyone
   having named the leaking column correctly.
3. **T-1 / T / T+1 boundary** -- an event one day before the landmark must be
   visible, an event on the landmark day must be visible (the target service is
   defined as strictly *after* the landmark, so a same-day service is history),
   and an event one day after must be invisible.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .features import (
    aggregate_task_features, policy_state_features, task_event_log,
    task_history_features,
)

#: tokens that must never appear in a V3 feature name
FORBIDDEN_TOKENS = (
    "target", "next_", "future_", "service_after", "task_after", "duration_days",
    "event_observed", "censor", "administrative_cutoff", "split", "modeling_role",
    "landmark_id", "motorcycle_id", "customer_id", "workshop_id", "model_id",
    "service_id", "snapshot_year", "landmark_year", "days_observed", "_row",
    "event_within_", "is_unseen", "lead_days", "adherence", "churn", "frailty",
    "latent", "tendency", "propensity_true",
)

#: Names that trip the substring screen but are provably safe. Each entry states
#: why. The screen is deliberately blunt -- it is cheaper to justify three names
#: here than to narrow the tokens and let a real leak through later.
ALLOWLIST = {
    "days_until_next_scheduled_due":
        "V2.1 contract feature: days until the next OEM *scheduled maintenance due "
        "date*, computed at the landmark from maintenance_policies intervals. It "
        "refers to a policy deadline, not to the next service event, and is "
        "unchanged by anything that happens after the landmark.",
    "km_until_next_scheduled_due":
        "V2.1 contract feature: kilometres until the next OEM scheduled maintenance "
        "due point, computed at the landmark from maintenance_policies intervals. "
        "Like its days counterpart it refers to a policy deadline, not to the next "
        "service event, and no post-landmark event can change it.",
    "avg_parts_lead_days":
        "Workshop-level average parts procurement lead time. Trips the screen only "
        "because V3's landmark-to-target gap is also called lead_days; the two are "
        "unrelated and this one is a workshop attribute known at the landmark.",
}
#: identifier columns that must never be handed to a model even by accident
FORBIDDEN_EXACT = {
    "landmark_id", "motorcycle_id", "customer_id", "workshop_id", "model_id",
    "next_service_id", "source_last_service_id", "v3_split", "purged",
}


def _digest(df: pd.DataFrame) -> str:
    return hashlib.sha256(
        pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()


def name_screen(feature_cols: list[str]) -> dict:
    """Check 1 -- feature names against the forbidden token and identifier lists."""
    hits, allowed = [], []
    for col in feature_cols:
        low = col.lower()
        if col in FORBIDDEN_EXACT:
            hits.append({"column": col, "reason": "identifier"})
            continue
        for tok in FORBIDDEN_TOKENS:
            if tok in low:
                entry = {"column": col, "reason": f"forbidden token '{tok}'"}
                if col in ALLOWLIST:
                    allowed.append({**entry, "justification": ALLOWLIST[col]})
                else:
                    hits.append(entry)
                break
    return {"check": "name_screen", "columns_checked": len(feature_cols),
            "violations": hits, "allowlisted": allowed, "passed": not hits}


def inject_future_events(events: pd.DataFrame, landmarks: pd.DataFrame,
                         labels: list[str], offsets_days=(1, 7, 30, 120),
                         seed: int = 0) -> pd.DataFrame:
    """Fabricate task events strictly after each landmark, for each label.

    Every injected row is a plausible service line -- same motorcycle, a real
    task code, a higher odometer -- so a leaking feature builder would happily
    pick it up. Nothing distinguishes it from a genuine future event except its
    date.
    """
    rng = np.random.default_rng(seed)
    lm = landmarks[["motorcycle_id", "landmark_at", "current_odometer_km_at_landmark"]]
    frames = []
    for off in offsets_days:
        f = lm.copy()
        f["event_at"] = f["landmark_at"] + pd.Timedelta(days=off)
        f["odometer_km"] = f["current_odometer_km_at_landmark"] + 50 * off
        f["task_code"] = rng.choice(labels, size=len(f))
        f["service_id"] = [f"INJECTED_{off}_{i}" for i in range(len(f))]
        frames.append(f[["service_id", "motorcycle_id", "task_code", "event_at", "odometer_km"]])
    return pd.concat([events, *frames], ignore_index=True).sort_values("event_at").reset_index(drop=True)


def future_injection_invariance(landmarks: pd.DataFrame, labels: list[str],
                                root: str | None = None) -> dict:
    """Check 2 -- rebuild the full feature matrix with injected future events."""
    real = task_event_log(root)
    lm = landmarks.copy()

    def build(events):
        h = task_history_features(lm, labels, root, events=events)
        p = policy_state_features(lm, labels, h, root)
        a = aggregate_task_features(h, labels)
        return pd.concat([h, p, a], axis=1)

    before = build(real)
    after = build(inject_future_events(real, lm, labels))
    # compare on the pre-injection column order: injecting a task code that never
    # occurs in the real log adds its columns in a different position, which is a
    # cosmetic difference, not leakage
    after = after[before.columns]
    same = before.equals(after)
    diff_cols = []
    if not same:
        for c in before.columns:
            if not before[c].equals(after[c]):
                diff_cols.append(c)
    return {
        "check": "future_injection_invariance",
        "landmarks_tested": int(len(lm)),
        "injected_events": int(len(inject_future_events(real, lm, labels)) - len(real)),
        "digest_before": _digest(before), "digest_after": _digest(after),
        "changed_columns": diff_cols[:20], "changed_column_count": len(diff_cols),
        "passed": bool(same),
    }


def boundary_test(landmarks: pd.DataFrame, labels: list[str],
                  root: str | None = None) -> dict:
    """Check 3 -- T-1 visible, T visible, T+1 invisible."""
    real = task_event_log(root)
    lm = landmarks.copy()
    code = labels[0]
    base = task_history_features(lm, labels, root, events=real)[f"hist_count__{code}"]

    results = {}
    for name, off in (("T_minus_1", -1), ("T", 0), ("T_plus_1", 1)):
        extra = lm[["motorcycle_id", "landmark_at", "current_odometer_km_at_landmark"]].copy()
        extra["event_at"] = extra["landmark_at"] + pd.Timedelta(days=off)
        extra["odometer_km"] = extra["current_odometer_km_at_landmark"]
        extra["task_code"] = code
        extra["service_id"] = [f"BOUNDARY_{name}_{i}" for i in range(len(extra))]
        ev = pd.concat([real, extra[real.columns]], ignore_index=True).sort_values("event_at")
        got = task_history_features(lm, labels, root, events=ev)[f"hist_count__{code}"]
        results[name] = {"changed_rows": int((got.to_numpy() != base.to_numpy()).sum()),
                         "total_rows": int(len(lm))}
    passed = (
        results["T_minus_1"]["changed_rows"] == len(lm)
        and results["T"]["changed_rows"] == len(lm)
        and results["T_plus_1"]["changed_rows"] == 0
    )
    return {"check": "boundary_T_minus_1_T_T_plus_1", "task_code": code,
            "expected": "T-1 and T visible (all rows change); T+1 invisible (no row changes)",
            "results": results, "passed": bool(passed)}


def audit_sample(landmarks: pd.DataFrame, sample: int = 4000, seed: int = 0) -> pd.DataFrame:
    """One landmark per motorcycle -- required for the injection tests to be valid.

    If two landmarks of the same motorcycle are in the tested set, an event
    injected after the earlier one is legitimately in the *past* of the later one,
    and the feature matrix is supposed to change. Keeping one landmark per
    motorcycle removes that confound, so any observed change is real leakage.
    """
    lm = landmarks.sample(frac=1.0, random_state=seed).groupby("motorcycle_id", sort=False).head(1)
    if sample and len(lm) > sample:
        lm = lm.sample(sample, random_state=seed)
    lm = lm.sort_values("landmark_at").reset_index(drop=True)
    lm["_row"] = np.arange(len(lm))
    return lm


def run_all(landmarks: pd.DataFrame, feature_cols: list[str], labels: list[str],
            root: str | None = None, sample: int = 4000, seed: int = 0) -> dict:
    lm = audit_sample(landmarks, sample, seed)
    checks = [
        name_screen(feature_cols),
        future_injection_invariance(lm, labels, root),
        boundary_test(lm, labels, root),
    ]
    return {"passed": all(c["passed"] for c in checks), "checks": checks}
