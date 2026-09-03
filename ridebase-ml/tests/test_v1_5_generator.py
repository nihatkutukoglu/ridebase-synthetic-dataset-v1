from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import build_ridebase_v1_5 as generator


def behavior(**overrides):
    value = {
        "adherence": 0.65,
        "no_show_tendency": 0.15,
        "churn_tendency": 0.10,
        "frailty": 1.0,
        "loyalty": 0.65,
    }
    value.update(overrides)
    return value


def context(annual_km=12000):
    usage = pd.Series({"annual_km_baseline": annual_km, "load_severity_factor": 1.0})
    motorcycle = pd.Series({"first_registration_date": "2021-01-01"})
    workshop = pd.Series({"service_bay_count": 8})
    return usage, motorcycle, workshop


def hazard(days_ratio, km_ratio, state=None, annual_km=12000, missed=0):
    usage, motorcycle, workshop = context(annual_km)
    return generator.step_hazards(
        pd.Timestamp("2026-05-15"), days_ratio, km_ratio, state or behavior(),
        usage, motorcycle, workshop, False, missed,
    )["PERIODIC"]


def test_due_pressure_is_smooth_increasing_and_saturating():
    values = [hazard(x, x) for x in (0.25, 0.75, 1.0, 1.5, 2.5, 3.5)]
    assert all(right > left for left, right in zip(values, values[1:]))
    assert values[-1] - values[-2] < values[3] - values[2]
    assert values[-1] <= 0.32


def test_high_usage_interacts_positively_with_overdue():
    low_delta = hazard(1.6, 1.6, annual_km=30000) - hazard(1.6, 1.6, annual_km=3000)
    not_due_delta = hazard(0.3, 0.3, annual_km=30000) - hazard(0.3, 0.3, annual_km=3000)
    assert low_delta > 0
    assert low_delta > not_due_delta


def test_adherence_raises_and_no_show_churn_lower_return_hazard():
    adherent = hazard(1.5, 1.5, behavior(adherence=.85, no_show_tendency=.05, churn_tendency=.05))
    friction = hazard(1.5, 1.5, behavior(adherence=.25, no_show_tendency=.85, churn_tendency=.75), missed=3)
    assert adherent > friction
    assert friction > 0


def test_generator_refuses_frozen_output_paths():
    assert generator.DEFAULT_OUTPUT.name == "ridebase_v1_5"
    assert generator.DEFAULT_OUTPUT.resolve() not in {generator.PARENT.resolve(), generator.REFERENCE.resolve()}


def test_generated_source_gate_when_v1_5_exists():
    metadata = generator.DEFAULT_OUTPUT / "dataset_metadata.json"
    if not metadata.exists():
        return
    import json
    value = json.loads(metadata.read_text())
    assert value["qa"]["status"] == "PASS"
    assert value["source_schema_changed"] is False
    assert value.get("reproducibility_verified") is True
    assert all(value["qa"]["checks"].values())
