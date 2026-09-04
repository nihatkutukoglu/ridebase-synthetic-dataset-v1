"""Unit tests for deterministic Maintenance Urgency Score."""
import math
import pytest
from ridebase_ml.policy.urgency import calculate_maintenance_urgency


def test_missing_data_returns_unknown():
    res = calculate_maintenance_urgency(None)
    assert res["maintenance_urgency_score"] is None
    assert res["maintenance_urgency_level"] == "HESAPLANAMADI"
    assert "eksik" in res["maintenance_urgency_reason"]


def test_due_threshold_alignment():
    # Exactly at threshold R = 1.0, score must be 50 and level must be GECİKMİŞ
    res = calculate_maintenance_urgency(1.0, km_ratio=1.0, day_ratio=0.5, overdue_km=0.0)
    assert res["maintenance_urgency_score"] == 50
    assert res["maintenance_urgency_level"] == "GECİKMİŞ"

    # Just below threshold R = 0.99, level must be YAKLAŞIYOR
    res_below = calculate_maintenance_urgency(0.99, km_ratio=0.99, day_ratio=0.5)
    assert res_below["maintenance_urgency_score"] < 50
    assert res_below["maintenance_urgency_level"] == "YAKLAŞIYOR"

    # Due threshold invariance: R >= 1.0 can NEVER be NORMAL or YAKLAŞIYOR
    for r in [1.0, 1.01, 1.1, 1.5, 2.0, 5.0, 10.0]:
        r_res = calculate_maintenance_urgency(r)
        assert r_res["maintenance_urgency_level"] not in ("NORMAL", "YAKLAŞIYOR")
        assert r_res["maintenance_urgency_score"] >= 50


def test_monotonicity_and_bounds():
    ratios = [0.0, 0.1, 0.25, 0.5, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0]
    scores = []
    for r in ratios:
        res = calculate_maintenance_urgency(r)
        score = res["maintenance_urgency_score"]
        assert 0 <= score <= 100
        assert math.isfinite(score)
        scores.append(score)

    # Monotonic non-decreasing
    for i in range(1, len(scores)):
        assert scores[i] >= scores[i - 1], f"Monotonicity failed at step {i}: {scores[i]} < {scores[i-1]}"


def test_saturation_at_extreme_overdue():
    res_5x = calculate_maintenance_urgency(5.0)
    assert res_5x["maintenance_urgency_score"] == 100
    assert res_5x["maintenance_urgency_level"] == "KRİTİK"

    res_10x = calculate_maintenance_urgency(10.0, km_ratio=10.0, day_ratio=0.2, overdue_km=27000)
    assert res_10x["maintenance_urgency_score"] == 100
    assert res_10x["maintenance_urgency_level"] == "KRİTİK"
    assert "27.000 km gecikmiş" in res_10x["maintenance_urgency_reason"]


def test_determining_dimensions():
    # KM driven
    res_km = calculate_maintenance_urgency(1.2, km_ratio=1.2, day_ratio=0.4)
    assert res_km["determining_dimension"] == "KM"

    # TIME driven
    res_time = calculate_maintenance_urgency(1.2, km_ratio=0.4, day_ratio=1.2)
    assert res_time["determining_dimension"] == "TIME"

    # BOTH (balanced)
    res_both = calculate_maintenance_urgency(1.2, km_ratio=1.205, day_ratio=1.200)
    assert res_both["determining_dimension"] == "BOTH"


def test_determinism():
    res1 = calculate_maintenance_urgency(1.5, km_ratio=1.5, day_ratio=0.8, overdue_km=1500)
    res2 = calculate_maintenance_urgency(1.5, km_ratio=1.5, day_ratio=0.8, overdue_km=1500)
    assert res1 == res2
