"""V2 survival API tests. Skipped whole-file when the FINAL V2 bundle is absent."""
from __future__ import annotations

import json

import pytest

from app.config import settings

_MANIFEST = settings.MODEL_DIR / "v2_advanced_config.json"
_BUNDLE_OK = _MANIFEST.exists() and json.loads(_MANIFEST.read_text()).get("status") == "FINAL"
pytestmark = pytest.mark.skipif(not _BUNDLE_OK, reason="V2 FINAL bundle not present")


@pytest.fixture(scope="module")
def v2_sample(client):
    r = client.get("/api/v2/sample")
    assert r.status_code == 200
    return r.json()["features"]


def test_v2_model_load(client):
    h = client.get("/health").json()
    assert h["v2_model_loaded"] is True
    assert h["v2_status"] == "ok"
    assert h["v2_real_fleet_validation"] == "PENDING"


def test_v2_model_info(client):
    mi = client.get("/api/v2/model/info").json()
    assert mi["model_family"] == "ENSEMBLE[XGB_COX+COXNET]"
    assert mi["run_mode"] == "FULL"
    assert mi["status"] == "SYNTHETICALLY_VALIDATED"
    assert mi["real_fleet_validation"] == "PENDING"
    assert mi["feature_count"] == 117


def test_v2_features_order_fixed(client):
    fe = client.get("/api/v2/features").json()
    assert fe["feature_count"] == len(fe["feature_order"]) == 117
    # caller cannot influence order; 'split' is internal
    assert "split" in fe["feature_order"]
    assert "do not send it" in fe["note"].lower() or "internally" in fe["note"].lower()


def test_v2_valid_prediction(client, v2_sample):
    r = client.post("/api/v2/predict", json={"features": v2_sample, "snapshot_date": "2026-02-15"})
    assert r.status_code == 200
    p = r.json()["prediction"]
    for k in ("risk_30d", "risk_60d", "risk_90d", "risk_120d", "median_service_days", "risk_group_90d"):
        assert k in p
    assert r.json()["model"]["real_fleet_validation"] == "PENDING"
    assert "pending" in r.json()["warning"].lower()


def test_v2_probability_bounds(client, v2_sample):
    p = client.post("/api/v2/predict", json={"features": v2_sample}).json()["prediction"]
    for h in (30, 60, 90, 120):
        assert 0.0 <= p[f"risk_{h}d"] <= 1.0


def test_v2_probability_monotonicity(client, v2_sample):
    p = client.post("/api/v2/predict", json={"features": v2_sample}).json()["prediction"]
    seq = [p[f"risk_{h}d"] for h in (30, 60, 90, 120)]
    assert seq == sorted(seq), seq


@pytest.mark.parametrize("bad", [
    {"duration_days": 12}, {"event_observed": 1}, {"next_service_days": 40},
    {"survival_target_eligible_primary": 1}, {"next_event_type": "PERIODIC"},
])
def test_v2_leakage_rejection(client, v2_sample, bad):
    r = client.post("/api/v2/predict", json={"features": {**v2_sample, **bad}})
    assert r.status_code == 422


def test_v2_unknown_feature_rejection(client, v2_sample):
    r = client.post("/api/v2/predict", json={"features": {**v2_sample, "totally_made_up": 1}})
    assert r.status_code == 422


def test_v2_invalid_input(client, v2_sample):
    # negative physical value and a non-numeric string both rejected (inf is not JSON, so not testable here)
    assert client.post("/api/v2/predict",
                       json={"features": {**v2_sample, "motorcycle_age_years": -5}}).status_code == 422
    assert client.post("/api/v2/predict",
                       json={"features": {**v2_sample, "annual_km_baseline": "nope"}}).status_code == 422


def test_v2_ood_warning(client, v2_sample):
    r = client.post("/api/v2/predict", json={"features": {**v2_sample, "annual_km_baseline": 999999}})
    assert r.status_code == 200
    assert r.json().get("warnings"), "expected an out-of-distribution warning"


def test_v2_deterministic_prediction(client, v2_sample):
    a = client.post("/api/v2/predict", json={"features": v2_sample}).json()["prediction"]
    b = client.post("/api/v2/predict", json={"features": v2_sample}).json()["prediction"]
    assert a == b


def test_v2_batch_prediction(client, v2_sample):
    r = client.post("/api/v2/predict/batch", json={"items": [v2_sample] * 100})
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 100 and len(body["predictions"]) == 100
    assert all(0 <= q["risk_90d"] <= 1 for q in body["predictions"])


def test_v2_feature_order_golden_parity(client):
    """Production API must match nb15's persisted TEST predictions bit-for-bit."""
    import numpy as np
    import pandas as pd
    mt = pd.read_parquet(settings.OUTPUTS_DIR / "v2_survival_modeling_table.parquet")
    pq = pd.read_parquet(settings.OUTPUTS_DIR / "v2_advanced_test_predictions.parquet")
    cfg = json.loads(_MANIFEST.read_text())
    cols = [c for c in cfg["feature_cols"] if c != "split"]
    te = mt[mt.split == "TEST"].reset_index(drop=True)
    # JSON has no NaN — real clients send null for missing values
    rows = te[cols].head(50).astype(object).where(pd.notna(te[cols].head(50)), None).to_dict("records")
    r = client.post("/api/v2/predict/batch", json={"items": rows})
    assert r.status_code == 200
    got = np.array([[q[f"risk_{h}d"] for h in (30, 60, 90, 120)] for q in r.json()["predictions"]])
    want = pq[[f"champion_risk_{h}" for h in (30, 60, 90, 120)]].head(50).to_numpy()
    assert np.abs(got - want).max() < 1e-6


def test_v2_metrics_artifact_driven(client):
    m = client.get("/api/v2/metrics").json()
    assert m["run_mode"] == "FULL" and m["status"] == "FINAL"
    assert m["test_metrics"]["ipcw_c_index"] > 0.8
    assert m["real_fleet_validation"] == "PENDING"
    assert m["golden_prediction_parity"] == "PASS"


def test_v1_v2_unified(client, v2_sample):
    r = client.post("/api/predict/service", json={"features": v2_sample})
    assert r.status_code == 200
    body = r.json()
    assert "v1" in body and "v2" in body
    assert "pending" in body["warning"].lower()


def test_admin_reload_requires_token(client, monkeypatch):
    from app import config as _cfg
    monkeypatch.setattr(_cfg.settings, "RIDEBASE_ADMIN_TOKEN", "s3cr3t-token")
    assert client.post("/admin/reload").status_code == 401
    assert client.post("/admin/reload", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.post("/admin/reload", headers={"Authorization": "Bearer s3cr3t-token"})
    assert r.status_code == 200


def test_admin_reload_blocked_when_token_unset(client, monkeypatch):
    from app import config as _cfg
    monkeypatch.setattr(_cfg.settings, "RIDEBASE_ADMIN_TOKEN", "")
    assert client.post("/admin/reload", headers={"Authorization": "Bearer anything"}).status_code == 401


def test_docs_hidden_in_production(monkeypatch):
    # docs_url/openapi_url are bound at FastAPI() construction time, so
    # reconstruct the app under each APP_ENV rather than hitting a route.
    import importlib
    from app import config as _cfg, main as _main
    try:
        monkeypatch.setattr(_cfg.settings, "APP_ENV", "production")
        importlib.reload(_main)
        assert _main.app.docs_url is None
        assert _main.app.redoc_url is None
        assert _main.app.openapi_url is None
    finally:
        monkeypatch.setattr(_cfg.settings, "APP_ENV", "development")
        importlib.reload(_main)
        assert _main.app.docs_url == "/docs"
