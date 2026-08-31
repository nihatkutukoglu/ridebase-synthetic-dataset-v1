"""Runtime configuration. All paths / origins come from the environment with
repo-relative defaults so `uvicorn app.main:app` works with zero setup."""
from __future__ import annotations

import os
from pathlib import Path

# backend/app/config.py -> repo root is 3 parents up from this file
_REPO_ROOT = Path(__file__).resolve().parents[3]
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

    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in os.environ.get(
            "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if o.strip()
    ]

    MAX_REQUEST_BYTES: int = int(os.environ.get("MAX_REQUEST_BYTES", 1_000_000))
    SCATTER_SAMPLE: int = int(os.environ.get("SCATTER_SAMPLE", 1500))


settings = Settings()
