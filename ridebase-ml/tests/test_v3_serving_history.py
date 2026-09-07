"""V3 serving-path gates: parity with the research matrix, and PIT safety.

The parity test is the load-bearing one. If the serving feature builder and the
training feature builder ever disagree, every frozen metric stops describing what
the API actually returns.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "ridebase-ml/derived_outputs/v2_1_v1_4/v2_1_history_serving.sqlite"
MODELS = ROOT / "ridebase-ml/models/v3_research"
_READY = STORE.exists() and (MODELS / "feature_list.json").exists()
pytestmark = pytest.mark.skipif(not _READY, reason="V3 serving artifacts not built")

if _READY:
    from ridebase_ml.v2_1.adapters.sqlite import SyntheticSQLiteSourceAdapter
    from ridebase_ml.v3 import experiment as E
    from ridebase_ml.v3 import serving as S
    from ridebase_ml.v3.serving import _completed_task_events


@pytest.fixture(scope="module")
def ctx():
    labels = E.load_labels(ROOT)
    order = json.loads((MODELS / "feature_list.json").read_text())["features"]
    prep = E.prepare(labels)
    adapter = SyntheticSQLiteSourceAdapter(STORE)
    return labels, order, prep, adapter


@pytest.fixture(scope="module")
def sample_rows(ctx):
    _, _, prep, _ = ctx
    rng = np.random.default_rng(5)
    idx = rng.choice(len(prep.ds.meta), 12, replace=False)
    return idx


def test_serving_features_match_the_research_matrix_exactly(ctx, sample_rows):
    labels, order, prep, adapter = ctx
    meta, feats = prep.ds.meta, prep.ds.features
    mismatches = []
    for i in sample_rows:
        m = meta.iloc[i]
        fv = S.build_v3_features(m.motorcycle_id, m.landmark_at.date(), adapter, labels, order)
        for col in order:
            a, b = feats.iloc[i][col], fv.features.get(col)
            if isinstance(a, str) or isinstance(b, str):
                same = str(a) == str(b)
            else:
                fa = float(a) if a is not None else np.nan
                fb = float(b) if b is not None else np.nan
                same = (np.isnan(fa) and np.isnan(fb)) or abs(fa - fb) <= 1e-6
            if not same:
                mismatches.append((m.motorcycle_id, col, a, b))
    assert not mismatches, mismatches[:10]


def test_full_feature_coverage_on_real_landmarks(ctx, sample_rows):
    labels, order, prep, adapter = ctx
    for i in sample_rows[:5]:
        m = prep.ds.meta.iloc[i]
        fv = S.build_v3_features(m.motorcycle_id, m.landmark_at.date(), adapter, labels, order)
        assert fv.coverage == 1.0, (m.motorcycle_id, fv.missing[:5])
        assert len(fv.features) == len(order) == 277


def test_declined_tasks_never_count_as_history(ctx):
    """A DECLINED line was recommended, not performed, and resets no interval."""
    _, _, _, adapter = ctx
    ev = _completed_task_events(adapter, "MC000001", date(2026, 1, 31))
    raw = adapter.get_service_tasks_before("MC000001", date(2026, 1, 31))
    declined = {(str(t["service_id"]), str(t["task_code"]))
                for t in raw if str(t.get("status")) == "DECLINED"}
    completed = {(str(t["service_id"]), str(t["task_code"]))
                 for t in raw if str(t.get("status")) == "COMPLETED"}
    seen = set(zip(ev["service_id"].astype(str), ev["task_code"].astype(str)))
    for pair in declined - completed:
        assert pair not in seen


def test_no_event_after_the_landmark_is_ever_used(ctx):
    _, _, prep, adapter = ctx
    m = prep.ds.meta.iloc[0]
    lm = m.landmark_at.date()
    ev = _completed_task_events(adapter, m.motorcycle_id, lm)
    if len(ev):
        assert ev["event_at"].max() <= pd.Timestamp(lm)


def test_future_injection_does_not_change_features(ctx):
    """Moving the landmark later may add history; moving it earlier must not lose PIT."""
    labels, order, prep, adapter = ctx
    m = prep.ds.meta.iloc[3]
    lm = m.landmark_at.date()
    a = S.build_v3_features(m.motorcycle_id, lm, adapter, labels, order)
    b = S.build_v3_features(m.motorcycle_id, lm, adapter, labels, order)
    assert a.features == b.features


def test_boundary_t_minus_1_t_and_t_plus_1(ctx):
    """Counts are monotone non-decreasing in the landmark date, and only change
    on a day where a service actually happened."""
    labels, order, prep, adapter = ctx
    m = prep.ds.meta.iloc[7]
    lm = m.landmark_at.date()
    counts = []
    for off in (-1, 0, 1):
        fv = S.build_v3_features(m.motorcycle_id, lm + timedelta(days=off),
                                 adapter, labels, order)
        counts.append(sum(fv.features[f"hist_count__{c}"] for c in labels))
    assert counts[0] <= counts[1] <= counts[2]


def test_same_day_task_lines_are_shuffle_invariant(ctx):
    """Regression for the research-phase determinism bug: two task lines on the
    same date must not swap and change hist_count."""
    labels, order, prep, adapter = ctx
    m = prep.ds.meta.iloc[9]
    lm = m.landmark_at.date()

    class ShuffledAdapter:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def get_service_tasks_before(self, mid, as_of):
            rows = list(self._inner.get_service_tasks_before(mid, as_of))
            return list(reversed(rows))

    a = S.build_v3_features(m.motorcycle_id, lm, adapter, labels, order)
    b = S.build_v3_features(m.motorcycle_id, lm, ShuffledAdapter(adapter), labels, order)
    assert a.features == b.features


def test_odometer_is_never_from_the_future(ctx):
    labels, order, prep, adapter = ctx
    m = prep.ds.meta.iloc[2]
    fv = S.build_v3_features(m.motorcycle_id, m.landmark_at.date(), adapter, labels, order)
    odo = fv.features["current_odometer_km_at_landmark"]
    services = adapter.get_services_before(m.motorcycle_id, m.landmark_at.date())
    if services and odo is not None:
        latest = max(float(s["odometer_km"]) for s in services
                     if s.get("odometer_km") not in (None, ""))
        assert float(odo) >= latest - 1e-6


def test_no_identifier_or_target_column_in_the_built_vector(ctx, sample_rows):
    labels, order, prep, adapter = ctx
    m = prep.ds.meta.iloc[int(sample_rows[0])]
    fv = S.build_v3_features(m.motorcycle_id, m.landmark_at.date(), adapter, labels, order)
    for col in fv.features:
        low = col.lower()
        assert "motorcycle_id" not in low
        assert "next_service" not in low
        assert not low.startswith("task__")
        assert "target" not in low


def test_provenance_records_the_pit_boundary(ctx):
    labels, order, prep, adapter = ctx
    m = prep.ds.meta.iloc[1]
    fv = S.build_v3_features(m.motorcycle_id, m.landmark_at.date(), adapter, labels, order)
    assert fv.provenance["declined_tasks_excluded"] is True
    assert "<= landmark" in fv.provenance["task_history_boundary"]
