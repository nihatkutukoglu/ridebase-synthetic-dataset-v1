"""API gates for /api/v3/* — the V3 next-service-task product surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings

_READY = (settings.MODEL_DIR / "v3_research/champion_model.joblib").exists()
pytestmark = pytest.mark.skipif(not _READY, reason="V3 frozen artifacts not present")

FORBIDDEN_FIELDS = ("urgency", "risk_30d", "risk_60d", "risk_90d", "risk_120d",
                    "median_service_days", "maintenance_due")


@pytest.fixture(scope="module")
def sample(client):
    r = client.get("/api/v3/sample")
    assert r.status_code == 200
    return r.json()


# ------------------------------------------------------------------- info
def test_health_reports_v3(client):
    h = client.get("/health").json()
    assert h["v3_status"] == "ok"
    assert h["v3_model_loaded"] is True
    assert h["v3_label_count"] == 44
    assert h["v3_feature_count"] == 277
    assert h["v3_real_fleet_validation"] == "PENDING"


def test_model_info(client):
    d = client.get("/api/v3/model/info").json()
    assert d["status"] == "V3_SYNTHETIC_PRODUCT_CANDIDATE"
    assert d["validation_scope"] == "SYNTHETIC_ONLY"
    assert d["real_fleet_validation"] == "PENDING"
    assert d["deployed_as_production_model"] is False
    assert d["label_count"] == 44 and d["feature_count"] == 277
    assert d["scenario_route_implemented"] is False
    assert "next completed service" in d["question"]


def test_model_info_states_what_v3_does_not_predict(client):
    d = client.get("/api/v3/model/info").json()
    joined = " ".join(d["does_not_predict"]).lower()
    for topic in ("v2.1", "urgency", "failure", "required"):
        assert topic in joined


def test_labels_route(client):
    d = client.get("/api/v3/labels").json()
    assert d["label_count"] == 44
    assert d["presentation_only"] is True
    assert set(d["product_status_counts"]) <= {
        "PRIMARY", "SECONDARY", "LOW_CONFIDENCE", "HIDDEN_BY_DEFAULT"}
    for row in d["labels"]:
        assert row["display_name"] and row["display_name"] != row["task_code"]
        assert row["note"]
        assert 0.0 <= row["test_pr_auc"] <= 1.0


def test_metrics_are_artifact_driven_and_never_call_p_at_1_accuracy(client):
    d = client.get("/api/v3/metrics").json()
    assert d["validation_scope"] == "SYNTHETIC_ONLY"
    assert d["real_fleet_validation"] == "PENDING"
    assert 0.0 <= d["test"]["precision_at_1"] <= 1.0
    note = d["metric_notes"]["precision_at_1"].lower()
    assert "ranking metric" in note and "not an accuracy" in note
    # No metric may be *named* accuracy except subset_accuracy, which is the real
    # name of a real multi-label metric and is reported as a secondary figure.
    for block in (d["test"], d["unseen_motorcycle_test"]):
        assert not any("accuracy" in k for k in block)
    for group in (d.get("subgroups") or {}).values():
        assert not any("accuracy" in k and k != "subset_accuracy" for k in group)


def test_metrics_match_the_frozen_artifact(client):
    d = client.get("/api/v3/metrics").json()
    frozen = json.loads(
        (settings.MODEL_DIR / "v3_research/test_evaluation.json").read_text())
    assert d["test"]["micro_f1"] == frozen["TEST"]["micro_f1"]
    assert d["test"]["precision_at_1"] == frozen["TEST"]["precision_at_1"]


# ----------------------------------------------------------------- sample
def test_sample_is_input_only_and_leaks_no_target(sample):
    assert sample["motorcycle_id"].startswith("MC")
    assert len(sample["landmark_date"]) == 10
    # the explanatory note legitimately contains the word "target" in order to say
    # no target is exposed, so check the data fields rather than the whole blob
    data = {k: v for k, v in sample.items() if k not in ("note", "warning",
                                                         "probability_meaning")}
    blob = json.dumps(data).lower()
    for leak in ("task__", "next_service", "target", "probability", "engine_oil"):
        assert leak not in blob
    assert set(data) == {
        "motorcycle_id", "landmark_date", "split", "friendly_motorcycle_label",
        "motorcycle_context", "motorcycle_context_provenance",
        "motorcycle_context_warnings",
    }
    assert sample["motorcycle_id"] in sample["friendly_motorcycle_label"]
    assert sample["motorcycle_context"]["motorcycle_id"] == sample["motorcycle_id"]


# ------------------------------------------------------- predict/by-motorcycle
def test_by_motorcycle_returns_the_product_contract(client, sample):
    r = client.post("/api/v3/predict/by-motorcycle",
                    json={"motorcycle_id": sample["motorcycle_id"],
                          "landmark_date": sample["landmark_date"], "top_k": 3})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "V3_SYNTHETIC_PRODUCT_CANDIDATE"
    assert d["validation_scope"] == "SYNTHETIC_ONLY"
    assert d["real_fleet_validation"] == "PENDING"
    assert d["landmark_date"] == sample["landmark_date"]
    assert d["input_source"] == "SYNTHETIC_HISTORY_V1_4"
    assert 0.0 <= d["feature_coverage"] <= 1.0
    assert len(d["all_task_probabilities"]) == 44
    assert len(d["top_tasks"]) <= 3
    assert d["provenance"]["deployed"] is False
    context = d["motorcycle_context"]
    assert context["motorcycle_id"] == sample["motorcycle_id"]
    assert context["landmark_date"] == sample["landmark_date"]
    assert context["source"] == "SYNTHETIC_HISTORY_V1_4"
    assert d["motorcycle_id"] in d["friendly_motorcycle_label"]
    assert d["motorcycle_context_provenance"]["future_records_used"] is False


def test_top_tasks_are_ranked_bounded_and_confident_only_when_earned(client, sample):
    d = client.post("/api/v3/predict/by-motorcycle",
                    json={"motorcycle_id": sample["motorcycle_id"],
                          "landmark_date": sample["landmark_date"], "top_k": 5}).json()
    tasks = d["top_tasks"]
    assert [t["rank"] for t in tasks] == list(range(1, len(tasks) + 1))
    probs = [t["probability"] for t in tasks]
    assert probs == sorted(probs, reverse=True)
    codes = [t["task_code"] for t in tasks]
    assert len(codes) == len(set(codes))
    for t in tasks:
        assert 0.0 <= t["probability"] <= 1.0
        assert t["confidence"] in ("YUKSEK", "ORTA", "DUSUK", "SINIRLI_VERI")
        assert t["display_name"] and t["display_name"] != t["task_code"]
        if t["confidence"] == "YUKSEK":
            assert t["product_status"] == "PRIMARY"


def test_hidden_labels_are_not_shown_but_are_still_returned(client, sample):
    body = {"motorcycle_id": sample["motorcycle_id"],
            "landmark_date": sample["landmark_date"], "top_k": 5}
    d = client.post("/api/v3/predict/by-motorcycle", json=body).json()
    hidden = {r["task_code"] for r in client.get("/api/v3/labels").json()["labels"]
              if r["product_status"] == "HIDDEN_BY_DEFAULT"}
    assert hidden
    assert all(t["task_code"] not in hidden for t in d["top_tasks"])
    assert hidden <= set(d["all_task_probabilities"])  # still returned technically


def test_response_carries_the_disclaimers(client, sample):
    d = client.post("/api/v3/predict/by-motorcycle",
                    json={"motorcycle_id": sample["motorcycle_id"],
                          "landmark_date": sample["landmark_date"]}).json()
    joined = " ".join(d["warnings"])
    assert "sentetik veri" in joined.lower()
    assert "mekanik arıza olasılığı değildir" in joined.lower()


def test_response_never_carries_urgency_or_v2_1_scores(client, sample):
    d = client.post("/api/v3/predict/by-motorcycle",
                    json={"motorcycle_id": sample["motorcycle_id"],
                          "landmark_date": sample["landmark_date"]}).json()
    # `warnings`, `probability_meaning` and `provenance.does_not_predict` name the
    # other surfaces precisely in order to disclaim them; that text is required.
    d.pop("warnings", None)
    d.pop("probability_meaning", None)
    d.pop("warning", None)
    # The newly added deterministic plan intentionally contains the canonical
    # maintenance-urgency state, but remains isolated under its own source-tagged
    # field and carries no V3 probability.
    plan = d.pop("maintenance_plan")
    assert plan["source"] == "DETERMINISTIC_POLICY"
    assert all("probability" not in key.lower() for item in plan["items"] for key in item)
    d.get("provenance", {}).pop("does_not_predict", None)
    blob = json.dumps(d).lower()
    for field in FORBIDDEN_FIELDS:
        assert field not in blob


def test_prediction_is_deterministic(client, sample):
    body = {"motorcycle_id": sample["motorcycle_id"],
            "landmark_date": sample["landmark_date"], "top_k": 3}
    a = client.post("/api/v3/predict/by-motorcycle", json=body).json()
    b = client.post("/api/v3/predict/by-motorcycle", json=body).json()
    assert a["all_task_probabilities"] == b["all_task_probabilities"]
    assert a["top_tasks"] == b["top_tasks"]


def test_unknown_motorcycle_is_a_clean_404(client):
    r = client.post("/api/v3/predict/by-motorcycle",
                    json={"motorcycle_id": "MC999999", "landmark_date": "2026-03-31"})
    assert r.status_code == 404
    assert "unknown motorcycle_id" in r.json()["detail"]


def test_pre_observation_landmark_is_a_clean_422(client, sample):
    r = client.post("/api/v3/predict/by-motorcycle",
                    json={"motorcycle_id": sample["motorcycle_id"],
                          "landmark_date": "2005-01-01"})
    assert r.status_code == 422
    assert "prediction" not in r.json()


def test_malformed_date_is_a_clean_422(client, sample):
    r = client.post("/api/v3/predict/by-motorcycle",
                    json={"motorcycle_id": sample["motorcycle_id"],
                          "landmark_date": "31-03-2026"})
    assert r.status_code == 422


def test_top_k_is_bounded_by_schema(client, sample):
    r = client.post("/api/v3/predict/by-motorcycle",
                    json={"motorcycle_id": sample["motorcycle_id"],
                          "landmark_date": sample["landmark_date"], "top_k": 99})
    assert r.status_code == 422


# ------------------------------------------------------------- predict / batch
def test_predict_from_a_full_feature_row(client, sample):
    built = client.post("/api/v3/predict/by-motorcycle",
                        json={"motorcycle_id": sample["motorcycle_id"],
                              "landmark_date": sample["landmark_date"]}).json()
    assert built["feature_coverage"] == 1.0  # by-motorcycle path is complete
    r = client.post("/api/v3/predict", json={"features": {}, "top_k": 3})
    assert r.status_code == 422  # empty row must be rejected, not filled in


def test_batch_is_bounded(client):
    from app.v3_service import MAX_BATCH
    r = client.post("/api/v3/predict/batch",
                    json={"rows": [{} for _ in range(MAX_BATCH + 5)]})
    assert r.status_code == 422  # schema max_length rejects before the handler


def test_batch_rejects_mismatched_id_length(client):
    r = client.post("/api/v3/predict/batch",
                    json={"rows": [{}, {}], "motorcycle_ids": ["MC000001"]})
    assert r.status_code == 422


# --------------------------------------------------------------- separation
def test_v2_1_routes_are_untouched(client):
    r = client.get("/api/v2_1/model/info")
    assert r.status_code == 200
    assert "v3" not in json.dumps(r.json()).lower()


def test_scenario_route_is_not_registered(client):
    r = client.post("/api/v3/predict/scenario", json={})
    assert r.status_code == 404


# ------------------------------------------------------------- kill switch
def test_v3_can_be_disabled_without_affecting_other_surfaces(client, monkeypatch):
    """V3 is the largest artifact in the process; a deploy must be able to shed it.

    The full stack peaks near 452 MB against Render free's 512 MB, so V3_ENABLED
    is a no-code-change escape hatch. Disabling it must degrade /api/v3/* to 503
    and leave V1 / V2.0 / V2.1 untouched.
    """
    from app import v3_service

    monkeypatch.setattr(v3_service.settings, "V3_ENABLED", False)
    with pytest.raises(v3_service.V3Unavailable):
        v3_service.get_predictor()
    assert v3_service.v3_loaded() is False
    fields = v3_service.health_fields()
    assert fields["v3_status"] == "disabled"
    assert fields["v3_enabled"] is False
    # other surfaces are unaffected
    assert client.get("/api/v2_1/model/info").status_code == 200
    assert client.get("/health").json()["v1"] == "ok"


def test_v3_enabled_parses_falsey_values():
    import importlib
    import os

    from app import config as cfg

    for raw, expected in (("false", False), ("0", False), ("no", False), ("off", False),
                          ("true", True), ("1", True), ("", True)):
        os.environ["V3_ENABLED"] = raw
        importlib.reload(cfg)
        assert cfg.settings.V3_ENABLED is expected, raw
    os.environ.pop("V3_ENABLED", None)
    importlib.reload(cfg)
