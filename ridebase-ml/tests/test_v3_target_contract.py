"""V3 Phase-29 gates: target contract, label taxonomy and rare-label policy."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ridebase_ml.v3 import labels as L
from ridebase_ml.v3 import target as T

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "config/v3_target_contract.json").read_text())
LABEL_SET = json.loads((ROOT / "config/v3_label_set.json").read_text())


def test_target_contract_is_not_another_product_surface():
    for forbidden in ("maintenance_due", "maintenance_urgency",
                      "v2_1_service_return_probability", "mechanical_failure_probability"):
        assert forbidden in CONTRACT["not_this"]


def test_declined_tasks_are_negative():
    assert T.PERFORMED_STATUS == "COMPLETED"
    assert "NEGATIVE" in CONTRACT["target_label"]["declined_tasks"]


def test_cancellations_and_no_shows_cannot_be_target_services():
    for k in ("cancellation", "no_show", "appointment_without_completion"):
        assert CONTRACT["event_type_decisions"][k].startswith("CANNOT be a target")


def test_performed_matrix_is_multi_hot_and_excludes_declined():
    src = T.load_sources()
    mat = T.performed_task_matrix()
    assert set(pd.unique(mat.to_numpy().ravel())) <= {0, 1}
    st = src["service_tasks"]
    declined_only = st[st["status"] == "DECLINED"].groupby(["service_id", "task_code"]).size()
    completed = set(map(tuple, st.loc[st["status"] == "COMPLETED",
                                      ["service_id", "task_code"]].to_numpy()))
    # a pair that was ONLY ever declined must be 0 in the target matrix
    checked = 0
    for (svc, code) in list(declined_only.index)[:200]:
        if (svc, code) in completed or code not in mat.columns or svc not in mat.index:
            continue
        assert mat.loc[svc, code] == 0
        checked += 1
    assert checked > 0, "no declined-only pair available to check"


def test_next_service_is_strictly_after_landmark():
    from ridebase_ml.v3 import dataset as D
    lm = D.observed_landmarks()
    assert (lm["lead_days"] > 0).all()
    assert (lm["target_service_at"] > lm["landmark_at"]).all()


def test_censored_landmarks_are_excluded_not_labelled_empty():
    from ridebase_ml.v3 import dataset as D
    from ridebase_ml.v3.sources import load_v2_1_landmarks
    grid = load_v2_1_landmarks()
    assert (grid["event_observed"] == 0).sum() > 0, "fixture should contain censored rows"
    assert not D.observed_landmarks()["next_service_id"].isna().any()


def test_applicability_respects_taxonomy_requirements():
    mat = T.performed_task_matrix()
    codes = list(mat.columns)
    app = T.applicability_matrix(pd.Index(["MC000001", "MC000003"]), codes)
    # MC000001 is a V_BELT/CVT scooter, MC000003 is chain/manual
    assert not app.loc["MC000001", "CHAIN_LUBRICATE"]
    assert app.loc["MC000003", "CHAIN_LUBRICATE"]


def test_label_set_frozen_before_test_and_uses_dev_support_only():
    assert LABEL_SET["frozen_before_test_evaluation"] is True
    assert "never used to select" in LABEL_SET["selection_basis"]
    assert LABEL_SET["merges_applied"].startswith("NONE")


def test_every_modelled_label_clears_every_gate():
    inv = pd.read_csv(ROOT / "reports/v3/03_label_inventory.csv").set_index("task_code")
    for code in LABEL_SET["labels"]:
        r = inv.loc[code]
        assert r["applicable_rows"] >= L.POLICY["min_applicable_rows"]
        assert r["pos_dev"] >= L.POLICY["min_positives_dev"]
        assert r["pos_val"] >= L.POLICY["min_positives_validation"]
        assert r["motorcycles"] >= L.POLICY["min_motorcycles"]
        assert r["years_covered"] >= L.POLICY["min_years_covered"]


def test_excluded_labels_each_carry_a_reason():
    for code, reason in LABEL_SET["excluded"].items():
        assert reason.strip(), f"{code} excluded without a recorded reason"
        assert code not in LABEL_SET["labels"]


def test_rare_label_policy_is_deterministic():
    inv = pd.read_csv(ROOT / "reports/v3/03_label_inventory.csv")
    a = L.classify(inv)["label_class"].tolist()
    b = L.classify(inv)["label_class"].tolist()
    assert a == b
