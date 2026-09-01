"""Runtime configuration. All paths / origins come from the environment with
repo-relative defaults so `uvicorn app.main:app` works with zero setup."""
from __future__ import annotations

import os
from pathlib import Path

def _find_repo_root() -> Path:
    """Local-dev fallback only. Production sets MODEL_DIR/... explicitly, so this
    never needs to be correct there — it just must not raise (the container has
    config.py at /app/app/config.py, i.e. fewer than 3 parents)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "ridebase-ml").is_dir() or (parent / ".git").exists():
            return parent
    return Path.cwd()


_REPO_ROOT = _find_repo_root()
_ML_ROOT = _REPO_ROOT / "ridebase-ml"


def _path(env: str, default: Path) -> Path:
    return Path(os.environ.get(env, str(default))).expanduser().resolve()


class Settings:
    APP_ENV: str = os.environ.get("APP_ENV", "development")
    MODEL_DIR: Path = _path("MODEL_DIR", _ML_ROOT / "models")
    REPORTS_DIR: Path = _path("REPORTS_DIR", _ML_ROOT / "reports")
    OUTPUTS_DIR: Path = _path("OUTPUTS_DIR", _ML_ROOT / "outputs")
    # snapshot table is only used to build the input-feature catalog (types / ranges / options)
    DATASET_DIR: Path = _path("DATASET_DIR", _REPO_ROOT / "ridebase_v1_3" / "derived_outputs")
    MODEL_CATALOG_PATH: Path = _path(
        "MODEL_CATALOG_PATH",
        _REPO_ROOT / "ridebase_v1_3" / "source_tables" / "ridebase_motorcycle_models_v1.csv",
    )
    MAINTENANCE_POLICY_PATH: Path = _path(
        "MAINTENANCE_POLICY_PATH",
        _REPO_ROOT / "ridebase_v1_3" / "source_tables" / "maintenance_policies.csv",
    )

    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in os.environ.get(
            "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if o.strip()
    ]

    # optional regex for CORS origins (e.g. published Claude artifacts on *.claudeusercontent.com)
    ALLOWED_ORIGIN_REGEX: str = os.environ.get("ALLOWED_ORIGIN_REGEX", "")

    MAX_REQUEST_BYTES: int = int(os.environ.get("MAX_REQUEST_BYTES", 1_000_000))
    SCATTER_SAMPLE: int = int(os.environ.get("SCATTER_SAMPLE", 1500))


settings = Settings()
