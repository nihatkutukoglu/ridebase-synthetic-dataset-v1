"""V3 productization gates: label policy, confidence tiers, top-K, product copy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ridebase_ml.v3 import product as PP

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config/v3_product_label_policy.json"
RAW = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
FROZEN_LABELS = json.loads(
    (ROOT / "ridebase-ml/models/v3_research/label_list.json").read_text())["labels"]


@pytest.fixture(scope="module")
def policy():
    return PP.load_label_policy(str(POLICY_PATH))


# --------------------------------------------------------------- label policy
def test_policy_covers_exactly_the_frozen_label_set(policy):
    assert set(policy) == set(FROZEN_LABELS)
    assert len(policy) == 44


def test_policy_is_presentation_only_and_removes_no_label():
    assert RAW["presentation_only"] is True
    assert len(RAW["labels"]) == len(FROZEN_LABELS)


def test_every_label_has_turkish_and_english_display_names(policy):
    for code, pol in policy.items():
        assert pol.display_name_tr.strip(), code
        assert pol.display_name_en.strip(), code
        assert pol.display_name_tr != code


def test_every_label_has_a_recorded_reason(policy):
    for code, pol in policy.items():
        assert len(pol.note) > 20, code


def test_random_event_labels_are_hidden_by_default(policy):
    for code, pol in policy.items():
        if pol.generating_process.startswith("E_"):
            assert pol.product_status == PP.HIDDEN, code


def test_high_prevalence_reliable_label_is_primary(policy):
    """Regression: the first policy draft judged on lift alone and buried this label.

    ENGINE_OIL_CHANGE has the highest TEST PR-AUC in the set (0.854 on 4,626
    positives) but only 1.09x lift, because at 78% prevalence there is no headroom.
    """
    assert policy["ENGINE_OIL_CHANGE"].product_status == PP.PRIMARY


def test_status_counts_match_the_recorded_summary(policy):
    counts = {}
    for pol in policy.values():
        counts[pol.product_status] = counts.get(pol.product_status, 0) + 1
    assert counts == RAW["counts"]


# ----------------------------------------------------------- confidence tiers
def test_high_probability_on_a_hidden_label_is_never_high_confidence(policy):
    for code, pol in policy.items():
        if not pol.hidden_by_default:
            continue
        for p in (0.5, 0.9, 0.99, 1.0):
            tier, reason = PP.confidence_tier(p, pol)
            assert tier == PP.TIER_LOW, (code, p, tier)
            assert reason


def test_low_confidence_label_caps_below_high(policy):
    low = [p for p in policy.values() if p.product_status == PP.LOW_CONFIDENCE]
    assert low, "fixture should contain LOW_CONFIDENCE labels"
    for pol in low:
        assert PP.confidence_tier(0.99, pol)[0] != PP.TIER_HIGH


def test_only_primary_labels_can_reach_high_confidence(policy):
    for pol in policy.values():
        if PP.confidence_tier(0.95, pol)[0] == PP.TIER_HIGH:
            assert pol.product_status == PP.PRIMARY


def test_thin_feature_coverage_forces_limited_data(policy):
    tier, _ = PP.confidence_tier(0.95, policy["ENGINE_OIL_CHANGE"], feature_coverage=0.4)
    assert tier == PP.TIER_LIMITED_DATA


def test_confidence_tier_is_deterministic(policy):
    pol = policy["CHAIN_CLEAN"]
    assert PP.confidence_tier(0.42, pol) == PP.confidence_tier(0.42, pol)


def test_every_tier_has_a_turkish_display_string():
    for tier in (PP.TIER_HIGH, PP.TIER_MEDIUM, PP.TIER_LOW, PP.TIER_LIMITED_DATA):
        assert PP.TIER_DISPLAY_TR[tier]


# -------------------------------------------------------------------- top-K
def _probs(policy, value=0.5):
    return {c: value for c in policy}


def test_hidden_labels_are_excluded_from_the_product_list(policy):
    probs = {c: (0.99 if policy[c].hidden_by_default else 0.10) for c in policy}
    ranked = PP.rank_tasks(probs, {c: True for c in policy}, policy, top_k=5)
    assert ranked
    assert all(not policy[r["task_code"]].hidden_by_default for r in ranked)


def test_hidden_labels_can_be_requested_explicitly(policy):
    probs = {c: (0.99 if policy[c].hidden_by_default else 0.10) for c in policy}
    ranked = PP.rank_tasks(probs, {c: True for c in policy}, policy, top_k=5,
                           include_hidden=True)
    assert any(policy[r["task_code"]].hidden_by_default for r in ranked)


def test_inapplicable_tasks_are_never_ranked(policy):
    applicable = {c: (c != "CHAIN_CLEAN") for c in policy}
    ranked = PP.rank_tasks(_probs(policy, 0.9), applicable, policy, top_k=10)
    assert all(r["task_code"] != "CHAIN_CLEAN" for r in ranked)


def test_top_k_is_bounded_and_ranks_are_dense(policy):
    ranked = PP.rank_tasks(_probs(policy), {c: True for c in policy}, policy, top_k=999)
    assert len(ranked) <= PP.MAX_TOP_K
    assert [r["rank"] for r in ranked] == list(range(1, len(ranked) + 1))


def test_ranking_ties_break_deterministically(policy):
    probs = _probs(policy, 0.5)
    a = PP.rank_tasks(probs, {c: True for c in policy}, policy, top_k=5)
    b = PP.rank_tasks(dict(reversed(list(probs.items()))), {c: True for c in policy},
                      policy, top_k=5)
    assert [r["task_code"] for r in a] == [r["task_code"] for r in b]


def test_ranked_probabilities_are_descending(policy):
    import random
    rng = random.Random(3)
    probs = {c: rng.random() for c in policy}
    ranked = PP.rank_tasks(probs, {c: True for c in policy}, policy, top_k=5)
    assert [r["probability"] for r in ranked] == sorted(
        [r["probability"] for r in ranked], reverse=True)


# ------------------------------------------------------------------ copy
def test_forbidden_product_wording_is_rejected():
    for bad in ("Bu işlem kesin yapılacak", "arıza riski %40",
                "gerçek veride doğruluk", "80% accurate", "ARIZA RİSKİ"):
        with pytest.raises(ValueError):
            PP.assert_copy_is_safe(bad)


def test_shipped_product_copy_passes_the_guard():
    for text in (PP.HEADING_TR, PP.SUBHEADING_TR, PP.DISCLAIMER_SYNTHETIC_TR,
                 PP.DISCLAIMER_NOT_FAILURE_TR, PP.DISCLAIMER_SEPARATE_TR,
                 PP.LOW_CONFIDENCE_HEADER_TR):
        PP.assert_copy_is_safe(text)


def test_warnings_always_carry_the_three_disclaimers(policy):
    w = PP.product_warnings([], 1.0, 0, 44)
    assert any(PP.DISCLAIMER_SYNTHETIC_TR in x for x in w)
    assert any(PP.DISCLAIMER_NOT_FAILURE_TR in x for x in w)
    assert any(PP.DISCLAIMER_SEPARATE_TR in x for x in w)


def test_low_coverage_produces_a_data_warning(policy):
    w = PP.product_warnings([], 0.5, 0, 44)
    assert any("kapsam" in x.lower() for x in w)
