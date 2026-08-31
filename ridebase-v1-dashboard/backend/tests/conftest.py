import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.artifacts import get_store

_STORE = get_store(reload=True)
MODELS_PRESENT = bool(_STORE.bundles.get("days") and _STORE.bundles["days"].ok
                      and _STORE.bundles.get("km") and _STORE.bundles["km"].ok)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def store():
    return _STORE


@pytest.fixture(autouse=True)
def _require_models(request):
    """Tests marked `needs_models` are skipped on a bare checkout without the
    notebook artifacts (CI without Git-LFS / an artifact-download step)."""
    if request.node.get_closest_marker("needs_models") and not MODELS_PRESENT:
        pytest.skip("model artifacts not present (ridebase-ml/models/v1_final_*)")


@pytest.fixture(scope="session")
def sample_payload(client):
    r = client.get("/api/v1/sample")
    if r.status_code != 200:
        pytest.skip("no sample artifact available")
    body = r.json()
    return {"features": body["features"], "snapshot_date": body["snapshot_date"]}
