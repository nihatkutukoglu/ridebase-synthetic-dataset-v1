"""V3 Phase-29 gates: frozen artifacts, thresholds, calibration and the predictor.

Skipped cleanly when the research artifacts have not been built yet, so the suite
stays green on a fresh checkout.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "ridebase-ml/models/v3_research"
_READY = (MODELS / "champion_model.joblib").exists()
pytestmark = pytest.mark.skipif(not _READY, reason="V3 research artifacts not built")

if _READY:
    from ridebase_ml.v3.predictor import V3PredictionError, V3TaskPredictor


@pytest.fixture(scope="module")
def predictor():
    return V3TaskPredictor.load(MODELS)


@pytest.fixture(scope="module")
def sample():
    from ridebase_ml.v3 import experiment as E
    labels = json.loads((ROOT / "config/v3_label_set.json").read_text())["labels"]
    prep = E.prepare(labels)
    idx = prep.idx["VALIDATION"][:64]
    return prep.ds.features.iloc[idx], prep.ds.meta.iloc[idx]


# ------------------------------------------------------------- artifacts
def test_artifacts_load_and_agree_on_the_label_set(predictor):
    labels = json.loads((ROOT / "config/v3_label_set.json").read_text())["labels"]
    assert predictor.labels == labels
    assert len(predictor.thresholds) == len(labels)


def test_thresholds_were_frozen_before_test_and_are_not_all_half():
    thr = json.loads((MODELS / "thresholds.json").read_text())
    assert thr["tuned_on"] == "VALIDATION"
    vals = np.asarray(thr["thresholds"])
    assert not np.allclose(vals, 0.5), "0.5 for every label means no tuning happened"
    assert ((vals > 0) & (vals <= 1.01)).all()


def test_champion_was_selected_before_test():
    sel = json.loads((MODELS / "selection_before_test.json").read_text())
    assert sel["selected_at"] == "before any TEST evaluation"
    assert sel["champion_family"] in sel["eligible_families"]
    assert sel["validation_metrics"]["mean_average_precision"] > sel["rule_baseline_mAP"]


def test_manifest_never_claims_production_or_real_fleet(predictor):
    man = predictor.manifest
    assert man["deployed"] is False
    assert man["status"] == "RESEARCH_OFFLINE_SYNTHETIC_ONLY"
    assert man["real_fleet_validation"] == "PENDING"
    assert man["model_version"].endswith("-research")


def test_calibration_skips_labels_with_too_few_positives():
    from ridebase_ml.v3 import calibration as C
    rep = json.loads((MODELS / "calibration_report.json").read_text())
    for row in rep["per_label"]:
        if row["calibration_positives"] < C.MIN_POSITIVES_FOR_CALIBRATION:
            assert row["chosen"] == "none", row["label"]


# -------------------------------------------------------------- predictor
def test_probabilities_are_bounded_and_finite(predictor, sample):
    X, meta = sample
    p = predictor.predict_proba(X, predictor.applicability(X, meta["motorcycle_id"]))
    assert np.isfinite(p).all()
    assert (p >= 0).all() and (p <= 1).all()


def test_prediction_is_deterministic(predictor, sample):
    X, meta = sample
    app = predictor.applicability(X, meta["motorcycle_id"])
    assert np.array_equal(predictor.predict_proba(X, app), predictor.predict_proba(X, app))


def test_inapplicable_tasks_are_forced_to_zero(predictor, sample):
    X, meta = sample
    app = predictor.applicability(X, meta["motorcycle_id"])
    p = predictor.predict_proba(X, app)
    assert (p[~app] == 0.0).all()


def test_response_contract(predictor, sample):
    X, meta = sample
    res = predictor.predict_batch(X, meta["motorcycle_id"], top_k=5,
                                  landmark_dates=meta["landmark_at"])[0].to_dict()
    assert res["model_version"].endswith("-research")
    assert res["status"] == "RESEARCH_OFFLINE_SYNTHETIC_ONLY"
    assert res["landmark_date"]
    assert res["provenance"]["deployed"] is False
    assert res["provenance"]["real_fleet_validation"].startswith("PENDING")
    assert len(res["top_k"]) <= 5
    for t in res["predicted_tasks"]:
        assert 0.0 <= t["probability"] <= 1.0
        assert t["applicable"] is True
        assert t["support_class"] in ("A_CORE", "B_LOW_FREQUENCY")


def test_response_carries_no_urgency_and_no_v2_1_score(predictor, sample):
    """No urgency score and no V2.1 horizon probability may appear as data.

    ``warnings`` is excluded from the scan on purpose: the mandatory disclaimer
    names both surfaces in order to disclaim them, and that text is required.
    """
    X, meta = sample
    res = predictor.predict_batch(X.head(4), meta["motorcycle_id"].head(4))[0].to_dict()
    res.pop("warnings")
    blob = json.dumps(res).lower()
    for forbidden in ("urgency", "risk_30", "risk_60", "risk_90", "risk_120",
                      "median_service_days", "service_return", "maintenance_due"):
        assert forbidden not in blob
    assert any("urgency" in w.lower() for w in
               predictor.predict_batch(X.head(1), meta["motorcycle_id"].head(1))[0].warnings)


def test_semantics_disclaimer_is_always_present(predictor, sample):
    X, meta = sample
    for res in predictor.predict_batch(X.head(5), meta["motorcycle_id"].head(5)):
        assert any("not mechanical failure probabilities" in w.lower() for w in res.warnings)


def test_ranks_are_dense_and_ordered(predictor, sample):
    X, meta = sample
    res = predictor.predict_batch(X.head(3), meta["motorcycle_id"].head(3))[0]
    ranks = [t["rank"] for t in res.top_k]
    assert ranks == sorted(ranks)
    probs = [t["probability"] for t in res.top_k]
    assert probs == sorted(probs, reverse=True)


def test_target_or_identifier_columns_are_rejected(predictor, sample):
    X, meta = sample
    bad = X.copy()
    bad["next_service_id"] = "SVC000001"
    with pytest.raises(V3PredictionError):
        predictor.predict_proba(bad)


def test_missing_features_are_rejected(predictor, sample):
    X, _ = sample
    with pytest.raises(V3PredictionError):
        predictor.predict_proba(X.drop(columns=X.columns[:3]))


def test_model_info_is_serialisable(predictor):
    json.dumps(predictor.model_info(), default=str)
