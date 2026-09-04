"""Safety tests for Signal Ceiling Oracle Study.

Guarantees:
- V1.5 TEST remains completely unaccessed / sealed.
- No oracle_ fields ever appear in V2.1, V2.2, V2.3 feature contracts or production serving code.
- Oracle fields are strictly isolated to research-only artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
ORACLE_DATASET_PATH = ROOT / "ridebase-ml/derived_outputs/signal_ceiling/oracle_study_dataset.parquet"
AUDIT_JSON_PATH = ROOT / "ridebase-ml/reports/signal_ceiling_oracle_dataset_audit.json"


def test_oracle_dataset_seals_test_split():
    assert ORACLE_DATASET_PATH.exists(), "Oracle dataset must exist"
    roles = pd.read_parquet(ORACLE_DATASET_PATH, columns=["modeling_role"])["modeling_role"].unique()
    assert "TEST" not in roles, "TEST split must NEVER be present in oracle dataset"
    assert set(roles) == {"TRAIN", "VALIDATION"}


def test_oracle_dataset_contains_proper_prefixes():
    df = pd.read_parquet(ORACLE_DATASET_PATH, columns=["oracle_latent_profile", "oracle_true_hazard_instantaneous"])
    assert "oracle_latent_profile" in df.columns
    assert "oracle_true_hazard_instantaneous" in df.columns


def test_no_oracle_fields_in_production_or_research_contracts():
    v2_1_features = json.loads((ROOT / "ridebase-ml/models/v2_1_v1_4/feature_list.json").read_text())
    v2_2_features = json.loads((ROOT / "ridebase-ml/models/v2_2_v1_5/feature_list.json").read_text())
    v2_3_dict = pd.read_csv(ROOT / "ridebase-ml/derived_outputs/v2_3_v1_5/v2_3_feature_dictionary.csv")
    v2_3_features = list(v2_3_dict["name"])

    for f in v2_1_features:
        assert not f.startswith("oracle_"), f"Production V2.1 contaminated with oracle feature {f}"
    for f in v2_2_features:
        assert not f.startswith("oracle_"), f"V2.2 contaminated with oracle feature {f}"
    for f in v2_3_features:
        assert not f.startswith("oracle_"), f"V2.3 contaminated with oracle feature {f}"


def test_no_oracle_fields_in_backend_service_code():
    v2_1_service_code = (ROOT / "ridebase-v1-dashboard/backend/app/v2_1_service.py").read_text()
    assert "oracle_" not in v2_1_service_code, "Backend v2_1_service.py contaminated with oracle field"

    history_features_code = (ROOT / "ridebase-ml/ridebase_ml/v2_1/history_features.py").read_text()
    assert "oracle_" not in history_features_code, "history_features.py contaminated with oracle field"
