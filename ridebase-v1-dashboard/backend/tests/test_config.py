"""config.py path resolution must work in both local dev and the Render/Docker
container, where config.py sits at /app/app/config.py (fewer than 3 parents,
which used to raise IndexError on parents[3])."""
from pathlib import Path

import app.config as cfg


def test_find_repo_root_never_raises():
    root = cfg._find_repo_root()
    assert isinstance(root, Path)  # no IndexError in any layout, always a Path


def test_explicit_env_path_is_authoritative(monkeypatch):
    """Container case: an explicit *_DIR env var wins outright — repo-root
    discovery is never consulted."""
    monkeypatch.setenv("MODEL_DIR", "/artifacts/models")
    assert cfg._path("MODEL_DIR", Path("/anything/else")) == Path("/artifacts/models")


def test_local_default_used_when_env_absent(monkeypatch):
    monkeypatch.delenv("MODEL_DIR", raising=False)
    assert cfg._path("MODEL_DIR", Path("/repo/ridebase-ml/models")) == Path("/repo/ridebase-ml/models")


def test_settings_dev_defaults_resolve():
    # loaded with no *_DIR env in the normal test run
    assert cfg.settings.MODEL_DIR.name == "models"
    assert cfg.settings.MODEL_DIR.parent.name == "ridebase-ml"


def test_prod_image_ships_every_artifact_a_route_reads_from_disk():
    """FAZ2/K2 regression guard: GET /api/v2_1/sample 404'lüyordu because
    Dockerfile.prod never COPY'd v2_1_modeling_table.parquet into the image
    that MODEL_DIR=/artifacts/models points routes.py/v2_1_routes.py at.
    Every *_DIR-relative artifact a live route touches must have a COPY line."""
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile.prod").read_text()
    for artifact in (
        "ridebase-ml/models/v2_1_v1_4",  # MODEL_DIR/v2_1_v1_4 -- predictor + calibrator
        "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_modeling_table.parquet",  # GET /api/v2_1/sample
        "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite",  # /predict/by-motorcycle
    ):
        assert f"COPY {artifact} " in dockerfile, f"{artifact} has no COPY line in Dockerfile.prod"
