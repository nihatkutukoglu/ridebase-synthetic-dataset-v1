import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.artifacts import get_store

_STORE = get_store(reload=True)
MODELS_PRESENT = bool(_STORE.bundles.get("days") and _STORE.bundles["days"].ok
                      and _STORE.bundles.get("km") and _STORE.bundles["km"].ok)


def _await_warmup(timeout: float = 120.0) -> None:
    """Block until the background warmup thread has finished loading.

    Startup now warms models off the request path so the socket binds
    immediately, which means a test can otherwise race the warmup and see
    ``v3_status: loading``. Tests assert the warmed state, so wait for it
    explicitly instead of depending on who wins the race.
    """
    import time

    from app import v2_1_service, v2_service, v3_service

    deadline = time.monotonic() + timeout
    checks = (
        lambda: v2_service._STATE["error"] is not None or v2_service.v2_loaded(),
        lambda: v2_1_service._STATE["predictor"] is not None
        or v2_1_service._STATE["error"] is not None,
        lambda: v3_service._STATE["predictor"] is not None
        or v3_service._STATE["error"] is not None,
    )
    while time.monotonic() < deadline:
        if all(check() for check in checks):
            return
        time.sleep(0.05)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        _await_warmup()
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
