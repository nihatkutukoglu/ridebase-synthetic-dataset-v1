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
