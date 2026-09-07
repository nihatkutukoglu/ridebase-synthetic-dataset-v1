"""Read-only access to the v1.4 source world and the frozen V2.1 landmark grid.

Everything in here loads; nothing writes. The V2.1 modeling table is opened
read-only and never re-derived -- its landmark placement, point-in-time feature
semantics and temporal split were audited and frozen for production, and V3
inherits them rather than inventing a parallel (and separately buggy) copy.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Mapping
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


#: Container deployments have no repository checkout. RIDEBASE_V3_SOURCE_DIR points
#: straight at a directory holding the four small reference tables V3 needs at
#: serving time (maintenance_tasks, maintenance_policies, motorcycles and the model
#: master -- about 3.4 MB). Per-motorcycle history never comes from here; it comes
#: from the V2.1 SQLite adapter.
SOURCE_DIR_ENV = "RIDEBASE_V3_SOURCE_DIR"


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        if (parent / "ridebase_v1_4").is_dir() and (parent / ".git").is_dir():
            return parent
    raise FileNotFoundError("repo root with ridebase_v1_4/ not found")


def source_dir(root: str | None = None) -> Path:
    """Where the v1.4 reference tables live: explicit root, else env, else repo."""
    if root:
        return Path(root) / WORLD / "source_tables"
    env = os.environ.get(SOURCE_DIR_ENV)
    if env:
        return Path(env).expanduser().resolve()
    return repo_root() / WORLD / "source_tables"


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    # the generator writes a UTF-8 BOM on the first header cell
    df.columns = [str(c).strip().lstrip("﻿") for c in df.columns]
    return df


@functools.lru_cache(maxsize=32)
def load_table(name: str, root: str | None = None) -> pd.DataFrame:
    """Load one v1.4 source table. Cached per table -- callers must not mutate."""
    if name not in _TABLES:
        raise KeyError(f"unknown v1.4 table {name!r}")
    return _read(source_dir(root) / f"{name}.csv")


class _LazyTables(Mapping):
    """Mapping over the v1.4 tables that reads each file only when it is touched.

    Serving needs four small reference tables (maintenance_tasks 98 rows,
    maintenance_policies 621, motorcycles 10k, the 39-row model master) and gets
    its per-motorcycle history from the SQLite adapter instead. Eagerly loading
    all ten tables cost **385 MB RSS** -- on a 512 MB host that is the difference
    between running and being OOM-killed, and services.csv / service_tasks.csv
    were never read on that path at all.

    Training still touches every table and behaves exactly as before; it just
    pays for each one at first use.
    """

    __slots__ = ("_root",)

    def __init__(self, root: str | None = None):
        self._root = root

    def __getitem__(self, name: str) -> pd.DataFrame:
        try:
            return load_table(name, self._root)
        except KeyError:
            raise KeyError(name) from None

    def __iter__(self):
        return iter(_TABLES)

    def __len__(self) -> int:
        return len(_TABLES)


def load_sources(root: str | None = None) -> Mapping[str, pd.DataFrame]:
    """The v1.4 source tables V3 uses, read lazily per table."""
    return _LazyTables(root)


@functools.lru_cache(maxsize=1)
def load_v2_1_landmarks(root: str | None = None) -> pd.DataFrame:
    """The frozen V2.1 modeling table: 256,841 monthly landmarks x 74 columns.

    Read-only. V3 uses it for the landmark grid, the 54-column PIT-safe base
    feature contract, the ``next_service_id`` pointer and the temporal split.
    """
    base = Path(root) if root else repo_root()
    return pd.read_parquet(base / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet")


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
