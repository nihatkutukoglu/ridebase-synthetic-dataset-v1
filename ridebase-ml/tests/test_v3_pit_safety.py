"""V3 Phase-29 gates: point-in-time safety, leakage screens and determinism.

These are the tests that must never be relaxed. A failure here means V3 can see
the future and every metric downstream is meaningless.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ridebase_ml.v3 import dataset as D
from ridebase_ml.v3 import features as F
from ridebase_ml.v3 import leakage as LK

ROOT = Path(__file__).resolve().parents[2]
LABELS = json.loads((ROOT / "config/v3_label_set.json").read_text())["labels"]


@pytest.fixture(scope="module")
def sample_landmarks():
    pool = D.assign_split(D.observed_landmarks(), purge=True)
    lm = D.select_landmarks(pool, "random_one")
    return LK.audit_sample(lm, sample=600, seed=7)


@pytest.fixture(scope="module")
def feature_cols():
    return D.build(LABELS, "random_one").features.columns.tolist()


def test_no_identifier_or_target_token_in_features(feature_cols):
    res = LK.name_screen(feature_cols)
    assert res["passed"], res["violations"]


def test_allowlisted_names_all_carry_a_justification(feature_cols):
    for entry in LK.name_screen(feature_cols)["allowlisted"]:
        assert len(entry["justification"]) > 40


def test_future_injection_leaves_features_byte_identical(sample_landmarks):
    res = LK.future_injection_invariance(sample_landmarks, LABELS)
    assert res["injected_events"] > 0
    assert res["passed"], res["changed_columns"]
    assert res["digest_before"] == res["digest_after"]


def test_boundary_t_minus_1_visible_t_visible_t_plus_1_invisible(sample_landmarks):
    res = LK.boundary_test(sample_landmarks, LABELS)
    n = len(sample_landmarks)
    assert res["results"]["T_minus_1"]["changed_rows"] == n
    assert res["results"]["T"]["changed_rows"] == n
    assert res["results"]["T_plus_1"]["changed_rows"] == 0


def test_history_features_are_deterministic_under_row_shuffling(sample_landmarks):
    """Regression for the same-day-duplicate bug the boundary test caught.

    Shuffling the event log must not change any feature: the occurrence index is
    a function of the data, not of row arrival order.
    """
    ev = F.task_event_log()
    a = F.task_history_features(sample_landmarks, LABELS, events=ev)
    b = F.task_history_features(
        sample_landmarks, LABELS,
        events=ev.sample(frac=1.0, random_state=3).reset_index(drop=True))
    pd.testing.assert_frame_equal(a, b)


def test_dataset_build_is_reproducible():
    a = D.build(LABELS, "random_one")
    b = D.build(LABELS, "random_one")
    assert a.manifest["feature_sha256"] == b.manifest["feature_sha256"]
    assert a.manifest["target_sha256"] == b.manifest["target_sha256"]
    assert a.manifest["rows"] == b.manifest["rows"]


def test_seed_change_moves_the_landmark_sample():
    a = D.build(LABELS, "random_one", seed=1)
    b = D.build(LABELS, "random_one", seed=2)
    assert a.manifest["feature_sha256"] != b.manifest["feature_sha256"]


def test_meta_holds_identifiers_and_features_never_do():
    ds = D.build(LABELS, "random_one")
    for col in ("motorcycle_id", "next_service_id", "landmark_id", "v3_split",
                "target_service_at", "lead_days"):
        assert col in ds.meta.columns
        assert col not in ds.features.columns


def test_split_is_temporal_and_non_overlapping():
    ds = D.build(LABELS, "random_one")
    m = ds.meta
    tr = m.loc[m.v3_split == "TRAIN", "landmark_at"]
    va = m.loc[m.v3_split == "VALIDATION", "landmark_at"]
    te = m.loc[m.v3_split == "TEST", "landmark_at"]
    assert tr.max() < va.min() < va.max() < te.min()


def test_no_target_service_bleeds_across_a_split_boundary():
    ds = D.build(LABELS, "random_one")
    m = ds.meta
    assert (m.loc[m.v3_split == "TRAIN", "target_service_at"] < D.VAL_START).all()
    assert (m.loc[m.v3_split == "VALIDATION", "target_service_at"] < D.TEST_START).all()


def test_each_target_service_appears_at_most_once():
    ds = D.build(LABELS, "random_one")
    assert not ds.meta.duplicated(["motorcycle_id", "next_service_id"]).any()


def test_multi_hot_targets_are_binary_and_aligned():
    ds = D.build(LABELS, "random_one")
    assert list(ds.targets.columns) == LABELS
    assert set(np.unique(ds.targets.to_numpy())) <= {0, 1}
    assert len(ds.targets) == len(ds.features) == len(ds.meta)


def test_no_oracle_or_latent_feature_reaches_the_dataset():
    ds = D.build(LABELS, "random_one")
    for col in ds.features.columns:
        assert not col.startswith("ORACLE_")
        assert not any(t in col.lower() for t in
                       ("adherence", "churn", "frailty", "latent", "hazard", "behavior_group"))
