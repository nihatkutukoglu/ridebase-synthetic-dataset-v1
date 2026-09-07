"""Read-only access to the v1.4 source world and the frozen V2.1 landmark grid.

Everything in here loads; nothing writes. The V2.1 modeling table is opened
read-only and never re-derived -- its landmark placement, point-in-time feature
semantics and temporal split were audited and frozen for production, and V3
inherits them rather than inventing a parallel (and separately buggy) copy.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

WORLD = "ridebase_v1_4"

#: v1.4 tables V3 reads. service_parts / mileage_timeline are intentionally not
#: loaded -- V3 needs neither, and mileage_timeline is 38 MB.
_TABLES = (
    "services",
    "service_tasks",
    "maintenance_tasks",
    "maintenance_policies",
    "motorcycles",
    "ridebase_motorcycle_models_v1",
    "appointments",
    "usage_profiles",
    "customers",
    "workshops",
)


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        if (parent / "ridebase_v1_4").is_dir() and (parent / ".git").is_dir():
            return parent
    raise FileNotFoundError("repo root with ridebase_v1_4/ not found")


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    # the generator writes a UTF-8 BOM on the first header cell
    df.columns = [str(c).strip().lstrip("﻿") for c in df.columns]
    return df


@functools.lru_cache(maxsize=1)
def load_sources(root: str | None = None) -> dict[str, pd.DataFrame]:
    """Load the v1.4 source tables V3 uses. Cached -- callers must not mutate."""
    base = Path(root) if root else repo_root()
    src = base / WORLD / "source_tables"
    return {name: _read(src / f"{name}.csv") for name in _TABLES}


@functools.lru_cache(maxsize=1)
def load_v2_1_landmarks(root: str | None = None) -> pd.DataFrame:
    """The frozen V2.1 modeling table: 256,841 monthly landmarks x 74 columns.

    Read-only. V3 uses it for the landmark grid, the 54-column PIT-safe base
    feature contract, the ``next_service_id`` pointer and the temporal split.
    """
    base = Path(root) if root else repo_root()
    path = base / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet"
    return pd.read_parquet(path)


def motorcycle_specs(root: str | None = None) -> pd.DataFrame:
    """Per-motorcycle hardware spec used for task applicability.

    Joins each motorcycle to its model row so the taxonomy's powertrain /
    final-drive / cooling / transmission requirements can be evaluated.
    """
    src = load_sources(root)
    cols = [
        "model_id", "powertrain_type", "cooling_type", "final_drive_type",
        "transmission_type", "policy_group",
    ]
    models = src["ridebase_motorcycle_models_v1"][cols]
    moto = src["motorcycles"][["motorcycle_id", "model_id", "brand", "category", "powertrain_type"]]
    spec = moto.merge(models, on="model_id", how="left", suffixes=("", "_model"))
    # motorcycles.powertrain_type is authoritative; the model table agrees but may be null
    spec["powertrain_type"] = spec["powertrain_type"].fillna(spec["powertrain_type_model"])
    return spec.drop(columns=["powertrain_type_model"])
