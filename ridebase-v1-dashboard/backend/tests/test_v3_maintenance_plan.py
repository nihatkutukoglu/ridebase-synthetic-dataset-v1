"""Contract, mapping, PIT, and separation gates for the V3 maintenance plan."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import pytest

from app.config import settings
from app.v3_maintenance_plan import (
    NOTE_TR,
    SOURCE,
    build_maintenance_plan,
    task_mapping,
)

_READY = (settings.MODEL_DIR / "v3_research/champion_model.joblib").exists()
pytestmark = pytest.mark.skipif(not _READY, reason="V3 frozen artifacts not present")


@pytest.fixture(scope="module")
def twelve_pairs():
    frame = pd.read_parquet(
        settings.MODEL_DIR.parent / "derived_outputs/v3/v3_sample_landmarks.parquet"
    ).sort_values(["motorcycle_id", "landmark_at"])
    frame = frame.drop_duplicates("motorcycle_id").head(12)
    assert len(frame) == 12
    return [
        (str(row.motorcycle_id), pd.Timestamp(row.landmark_at).date().isoformat())
        for row in frame.itertuples()
    ]


def test_mapping_is_exhaustive_and_audited_against_frozen_labels():
    labels_payload = json.loads((settings.MODEL_DIR / "v3_research/label_list.json").read_text())
    labels = labels_payload["labels"]
    mapping = task_mapping()
    assert set(mapping) == set(labels)
    assert len(mapping) == 44
    assert {row["status"] for row in mapping.values()} == {
        "EXACT", "RELATED_BUT_NOT_EQUIVALENT", "NO_MAPPING"
    }
    assert sum(row["status"] == "EXACT" for row in mapping.values()) == 27
    for code, row in mapping.items():
        if row["status"] == "EXACT":
            assert row["maintenance_task_code"] == code
        if row["status"] == "NO_MAPPING":
            assert row["maintenance_task_code"] is None


def test_twelve_motorcycle_matrix_has_complete_separate_contract(client, twelve_pairs):
    for motorcycle_id, landmark in twelve_pairs:
        response = client.post(
            "/api/v3/predict/by-motorcycle",
            json={"motorcycle_id": motorcycle_id, "landmark_date": landmark, "top_k": 3},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload["top_tasks"]) == 3
        assert len(payload["all_task_probabilities"]) == 44
        assert len(payload["all_tasks"]) == 44
        assert [row["rank"] for row in payload["all_tasks"]] == list(range(1, 45))
        probabilities = [row["probability"] for row in payload["all_tasks"]]
        assert probabilities == sorted(probabilities, reverse=True)
        assert {row["task_code"] for row in payload["all_tasks"]} == set(
            payload["all_task_probabilities"]
        )
        for row in payload["all_tasks"]:
            assert row["probability"] == payload["all_task_probabilities"][row["task_code"]]
            if row["product_status"] == "HIDDEN_BY_DEFAULT":
                assert row["confidence"] == "DUSUK"

        plan = payload["maintenance_plan"]
        assert plan["source"] == SOURCE
        assert plan["note"] == NOTE_TR
        assert plan["future_records_used"] is False
        assert all("probability" not in key.lower() for item in plan["items"] for key in item)
        codes = [item["task_code"] for item in plan["items"]]
        assert len(codes) == len(set(codes))
        assert all(item["source"] == SOURCE for item in plan["items"])
        assert all(item["status"] in {
            "NORMAL", "YAKLAŞIYOR", "GECİKMİŞ", "ÇOK GECİKMİŞ", "KRİTİK"
        } for item in plan["items"])


def test_plan_due_count_matches_existing_v2_1_due_semantics(client, twelve_pairs):
    from app.v3_service import get_history_adapter
    from ridebase_ml.v2_1.history_features import build_features

    adapter = get_history_adapter()
    for motorcycle_id, landmark in twelve_pairs:
        existing = build_features(motorcycle_id, landmark, adapter)["features"]
        plan = build_maintenance_plan(motorcycle_id, landmark, adapter)
        assert plan["due_item_count"] == int(existing["due_task_count"])
        assert bool(plan["due_item_count"]) == bool(existing["maintenance_due_now"])


def test_plan_sort_is_severity_then_progress_and_never_probability(client, twelve_pairs):
    order = {"KRİTİK": 0, "ÇOK GECİKMİŞ": 1, "GECİKMİŞ": 2, "YAKLAŞIYOR": 3, "NORMAL": 4}
    motorcycle_id, landmark = twelve_pairs[0]
    plan = client.post(
        "/api/v3/predict/by-motorcycle",
        json={"motorcycle_id": motorcycle_id, "landmark_date": landmark},
    ).json()["maintenance_plan"]
    keys = [(order[row["status"]], -row["progress_ratio"], row["task_code"]) for row in plan["items"]]
    assert keys == sorted(keys)
    assert "never V3 probability" in plan["sort_policy"]


def test_plan_and_all_task_metadata_are_deterministic(client, twelve_pairs):
    motorcycle_id, landmark = twelve_pairs[1]
    body = {"motorcycle_id": motorcycle_id, "landmark_date": landmark, "top_k": 3}
    first = client.post("/api/v3/predict/by-motorcycle", json=body).json()
    second = client.post("/api/v3/predict/by-motorcycle", json=body).json()
    assert first["maintenance_plan"] == second["maintenance_plan"]
    assert first["all_tasks"] == second["all_tasks"]
    assert first["all_task_probabilities"] == second["all_task_probabilities"]
    assert first["top_tasks"] == second["top_tasks"]


class FakeAdapter:
    def __init__(self, *, odometer=1250.0, policies=None, tasks=None, services=None):
        self.odometer = odometer
        self.policies = policies or []
        self.tasks = tasks or []
        self.services = services or []

    def get_motorcycle(self, *_):
        return {
            "motorcycle_id": "MCX", "model_id": "MODEL_X",
            "observation_start_date": "2026-01-01", "initial_mileage_km": 1000,
        }

    def get_model_master(self, *_):
        return {"model_id": "MODEL_X", "policy_group": "GROUP_X"}

    def get_maintenance_policy(self, *_):
        return list(self.policies)

    def get_mileage_before(self, *_):
        if self.odometer is None:
            return []
        return [{"timeline_id": "MTL1", "_effective_at": "2026-07-01", "closing_odometer_km": self.odometer}]

    def get_services_before(self, *_):
        return list(self.services)

    def get_service_tasks_before(self, *_):
        return list(self.tasks)

    def read_table(self, table):
        if table == "maintenance_tasks":
            return [
                {"task_code": "TASK_A", "canonical_name_tr": "Görev A"},
                {"task_code": "TASK_B", "canonical_name_tr": "Görev B"},
                {"task_code": "TASK_C", "canonical_name_tr": "Görev C"},
            ]
        return []


def policy(code, *, policy_id=None, scope="GROUP", km="", months="", mode="WHICHEVER_FIRST"):
    return {
        "policy_id": policy_id or f"POL_{code}", "scope_type": scope,
        "model_id": "MODEL_X" if scope == "MODEL" else "",
        "policy_group": "GROUP_X", "task_code": code, "policy_kind": "SCHEDULED",
        "initial_trigger_km": "", "recurring_km": km,
        "initial_trigger_months": "", "recurring_months": months,
        "trigger_mode": mode, "precedence": 10, "is_generator_active": 1,
        "evidence_level": "SIMULATION_PRIOR", "confidence": "LOW",
        "source_authority": "test fixture", "policy_version": "1.0.0",
        "is_manufacturer_exact_interval": 0,
    }


def test_model_policy_wins_and_duplicate_task_is_removed():
    adapter = FakeAdapter(policies=[
        policy("TASK_A", policy_id="GROUP", km=100),
        policy("TASK_A", policy_id="MODEL", scope="MODEL", km=500),
    ])
    plan = build_maintenance_plan("MCX", "2026-07-01", adapter)
    assert len(plan["items"]) == 1
    assert plan["items"][0]["policy_id"] == "MODEL"
    assert plan["items"][0]["progress_ratio"] == 0.5


def test_missing_odometer_keeps_time_policy_and_skips_km_only_policy():
    adapter = FakeAdapter(odometer=None, policies=[
        policy("TASK_B", months=6, mode="TIME_ONLY"),
        policy("TASK_C", km=100, mode="KM_ONLY"),
    ])
    plan = build_maintenance_plan("MCX", "2026-07-01", adapter)
    assert [item["task_code"] for item in plan["items"]] == ["TASK_B"]
    assert plan["skipped_policy_task_codes"] == ["TASK_C"]


def test_future_rows_cannot_change_plan():
    base = FakeAdapter(policies=[policy("TASK_A", km=100)])
    expected = build_maintenance_plan("MCX", "2026-07-01", base)
    injected = FakeAdapter(
        policies=base.policies,
        odometer=base.odometer,
        services=[{
            "service_id": "FUTURE", "status": "DELIVERED",
            "_effective_at": "2026-07-02", "odometer_km": 999999,
        }],
        tasks=[{
            "service_id": "FUTURE", "task_code": "TASK_A", "status": "COMPLETED",
            "_effective_at": "2026-07-02",
        }],
    )
    assert build_maintenance_plan("MCX", "2026-07-01", injected) == expected


def test_missing_policy_is_an_explicit_empty_state():
    plan = build_maintenance_plan("MCX", "2026-07-01", FakeAdapter())
    assert plan["items"] == []
    assert plan["source"] == SOURCE
    assert plan["empty_reason"] == "Bu motosiklet için bakım planı eşlemesi bulunamadı."


def test_t_minus_one_t_t_plus_one_is_monotonic_without_future_access():
    adapter = FakeAdapter(odometer=None, policies=[policy("TASK_B", months=6, mode="TIME_ONLY")])
    ratios = [
        build_maintenance_plan("MCX", (date(2026, 7, 1) + timedelta(days=offset)).isoformat(), adapter)["items"][0]["progress_ratio"]
        for offset in (-1, 0, 1)
    ]
    assert ratios[0] < ratios[1] < ratios[2]
