"""V3 dataset construction: landmark selection, PIT features, multi-hot targets.

One row = one landmark for one motorcycle. The target is the multi-hot vector of
tasks performed at that motorcycle's next service.

Landmark strategies (Phase 6). All of them draw from the same frozen V2.1
monthly landmark grid; they differ only in which of those landmarks are kept:

``all``        every observed landmark. 5.0 landmarks share each target service
               on average (max 31), so metrics are inflated by near-duplicate
               rows. Kept as the anti-baseline that shows the inflation.
``random_one`` exactly one landmark per (motorcycle, target service), drawn with
               a fixed seed. Removes duplication while leaving the lead-time
               distribution spread across the whole inter-service interval.
``earliest``   the first landmark after the previous service -- longest lead.
``latest``     the last landmark before the target service -- shortest lead.
               This is the "trivially placed immediately before a known service"
               design the V3 brief warns about; kept to quantify that optimism.
``annual``     one landmark per motorcycle-year, fixed cadence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import SEED, SOURCE_WORLD, V3_VERSION
from .features import (
    BASE_CATEGORICAL, BASE_NUMERIC, BEHAVIOURAL_NUMERIC, aggregate_task_features,
    policy_state_features, task_history_features,
)
from .sources import load_v2_1_landmarks
from .target import performed_task_matrix, service_index

STRATEGIES = ("all", "random_one", "earliest", "latest", "annual")
BUILDER_VERSION = "v3-dataset-builder-1.0.0"

#: split boundaries inherited from the frozen V2.1 temporal split
VAL_START = pd.Timestamp("2025-07-01")
TEST_START = pd.Timestamp("2026-01-01")


def observed_landmarks(root: str | None = None) -> pd.DataFrame:
    """V2.1 landmarks that actually have a next service, with target metadata.

    Right-censored landmarks are dropped: their target is *unknown*, not empty.
    Treating a censored landmark as an all-zero label vector would teach the
    model that "no service happened yet" means "no tasks", which is false.
    """
    lm = load_v2_1_landmarks(root)
    lm = lm.loc[lm["event_observed"] == 1].copy()
    svc = service_index(root).rename(columns={
        "service_id": "next_service_id", "received_at": "target_service_at",
        "motorcycle_id": "_target_moto", "odometer_km": "target_odometer_km",
        "service_type_code": "target_service_type",
    })
    lm = lm.merge(
        svc[["next_service_id", "target_service_at", "target_service_type",
             "eligible_target", "_target_moto"]],
        on="next_service_id", how="left",
    )
    assert (lm["_target_moto"] == lm["motorcycle_id"]).all(), "target service belongs to another motorcycle"
    lm = lm.loc[lm["eligible_target"]].drop(columns=["_target_moto", "eligible_target"])
    lm["lead_days"] = (lm["target_service_at"] - lm["landmark_at"]).dt.days
    assert (lm["lead_days"] > 0).all(), "target service must be strictly after the landmark"
    return lm.reset_index(drop=True)


def select_landmarks(lm: pd.DataFrame, strategy: str, seed: int = SEED) -> pd.DataFrame:
    """Apply a Phase-6 landmark strategy to the observed landmark pool."""
    if strategy == "all":
        return lm.copy()
    key = ["motorcycle_id", "next_service_id"]
    if strategy == "random_one":
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(lm))
        shuffled = lm.iloc[order]
        return shuffled.groupby(key, sort=False).head(1).sort_index().copy()
    if strategy == "earliest":
        return lm.sort_values("lead_days", ascending=False).groupby(key, sort=False).head(1).sort_index().copy()
    if strategy == "latest":
        return lm.sort_values("lead_days").groupby(key, sort=False).head(1).sort_index().copy()
    if strategy == "annual":
        rng = np.random.default_rng(seed)
        tmp = lm.assign(_y=lm["landmark_at"].dt.year)
        order = rng.permutation(len(tmp))
        return tmp.iloc[order].groupby(["motorcycle_id", "_y"], sort=False).head(1).sort_index().drop(columns="_y").copy()
    raise ValueError(f"unknown landmark strategy: {strategy}")


def assign_split(lm: pd.DataFrame, purge: bool = True) -> pd.DataFrame:
    """Inherit the V2.1 temporal split, then purge target bleed across boundaries.

    A TRAIN landmark whose *target service* falls inside the VALIDATION period
    would let TRAIN see task outcomes from the validation era. V2.1 tolerated
    this because its target is a duration; V3's target is the content of a
    specific future service, so the bleed is removed rather than reported away.
    """
    out = lm.copy()
    out["v3_split"] = out["primary_split"]
    if not purge:
        out["purged"] = False
        return out
    bleed = (
        ((out["v3_split"] == "TRAIN") & (out["target_service_at"] >= VAL_START))
        | ((out["v3_split"] == "VALIDATION") & (out["target_service_at"] >= TEST_START))
    )
    out["purged"] = bleed
    return out.loc[~bleed].copy()


@dataclass
class V3Dataset:
    features: pd.DataFrame          # PIT-safe predictors only
    targets: pd.DataFrame           # multi-hot, one column per label
    meta: pd.DataFrame              # identifiers/split/dates -- never features
    labels: list[str]
    feature_blocks: dict[str, list[str]]
    manifest: dict

    def block(self, *names: str) -> list[str]:
        cols: list[str] = []
        for n in names:
            cols.extend(self.feature_blocks[n])
        return cols


def build(labels: list[str], strategy: str = "random_one", root: str | None = None,
          purge: bool = True, seed: int = SEED) -> V3Dataset:
    """Build the V3 dataset for a given label set and landmark strategy."""
    # purge before sampling: a target service that still has a non-bleeding
    # landmark keeps one, instead of being lost because the sampler happened to
    # draw the landmark that bleeds across the split boundary
    pool = assign_split(observed_landmarks(root), purge=purge)
    lm = select_landmarks(pool, strategy, seed=seed).reset_index(drop=True)
    lm["_row"] = np.arange(len(lm))

    hist = task_history_features(lm, labels, root)
    pol = policy_state_features(lm, labels, hist, root)
    agg = aggregate_task_features(hist, labels)

    blocks = {
        "F0_base": BASE_CATEGORICAL + BASE_NUMERIC,
        "F1_policy": list(pol.columns),
        "F2_hist": [c for c in hist.columns if c.startswith("hist_count__")] + list(agg.columns),
        "F3_recency": [c for c in hist.columns if c.startswith(("days_since__", "km_since__"))],
        "F4_behaviour": BEHAVIOURAL_NUMERIC,
    }
    feats = pd.concat(
        [lm[BASE_CATEGORICAL + BASE_NUMERIC + BEHAVIOURAL_NUMERIC].reset_index(drop=True),
         pol.reset_index(drop=True), hist.reset_index(drop=True), agg.reset_index(drop=True)],
        axis=1,
    )
    feats = feats[[c for b in blocks.values() for c in b]]

    tmat = performed_task_matrix(root)
    y = tmat.reindex(lm["next_service_id"].to_numpy()).fillna(0).astype("int8")
    y = y.reindex(columns=labels, fill_value=0)
    y.index = lm.index

    meta = lm[["landmark_id", "motorcycle_id", "model_id", "policy_group", "landmark_at",
               "next_service_id", "target_service_at", "target_service_type", "lead_days",
               "v3_split", "is_unseen_motorcycle_holdout", "modeling_role"]].copy()

    manifest = {
        "dataset_version": f"{V3_VERSION}-{strategy}",
        "builder_version": BUILDER_VERSION,
        "source_world": SOURCE_WORLD,
        "landmark_strategy": strategy,
        "seed": seed,
        "purged_split_bleed": purge,
        "rows": int(len(lm)),
        "motorcycles": int(lm["motorcycle_id"].nunique()),
        "target_services": int(lm["next_service_id"].nunique()),
        "label_count": len(labels),
        "feature_count": int(feats.shape[1]),
        "date_range": [str(lm["landmark_at"].min().date()), str(lm["landmark_at"].max().date())],
        "target_date_range": [str(lm["target_service_at"].min().date()),
                              str(lm["target_service_at"].max().date())],
        "split_rows": {k: int(v) for k, v in lm["v3_split"].value_counts().items()},
        "target_service_type_mix": {k: int(v) for k, v in lm["target_service_type"].value_counts().items()},
        "lead_days": {
            "min": int(lm["lead_days"].min()), "median": float(lm["lead_days"].median()),
            "mean": float(lm["lead_days"].mean()), "max": int(lm["lead_days"].max()),
        },
        "feature_blocks": {k: len(v) for k, v in blocks.items()},
        "feature_sha256": hashlib.sha256(
            pd.util.hash_pandas_object(feats, index=False).values.tobytes()).hexdigest(),
        "target_sha256": hashlib.sha256(
            pd.util.hash_pandas_object(y, index=False).values.tobytes()).hexdigest(),
    }
    return V3Dataset(feats, y, meta, list(labels), blocks, manifest)
