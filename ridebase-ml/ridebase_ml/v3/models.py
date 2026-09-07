"""V3 baselines and the multi-label model tournament (Phases 11-13).

All candidates are Binary Relevance -- one independent classifier per label --
because label dependence in this dataset turns out to be dominated by shared
maintenance-interval state that every classifier already sees (Phase 17).
Classifier Chains are offered as a research challenger only.

Every baseline and model consumes exactly the same point-in-time feature matrix,
so a win is never a feature-access artifact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import SEED
from .features import BASE_CATEGORICAL

_CONSTANT_TOL = 1e-12


def make_preprocessor(feature_cols: list[str]) -> ColumnTransformer:
    """One-hot the 13 contract categoricals, pass numerics through unscaled."""
    cats = [c for c in feature_cols if c in BASE_CATEGORICAL]
    nums = [c for c in feature_cols if c not in cats]
    return ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20, sparse_output=False), cats),
         ("num", "passthrough", nums)],
        remainder="drop", verbose_feature_names_out=False,
    )


# --------------------------------------------------------------------------
# Baselines
# --------------------------------------------------------------------------

class PrevalenceBaseline:
    """BASELINE 0 -- per-label TRAIN prevalence, identical for every row."""

    name = "baseline0_prevalence"

    def fit(self, X, y, **_):
        self.p_ = y.mean(axis=0)
        return self

    def predict_proba(self, X):
        return np.tile(self.p_, (len(X), 1))


class RuleBaseline:
    """BASELINE 1 -- deterministic OEM maintenance policy, no learning at all.

    Score is the policy due ratio squashed into [0, 1]:
    ``min(due_ratio, 2) / 2``, so a task exactly at its interval scores 0.5 and
    anything at or past 2x interval saturates at 1.0. A label with no policy row
    (due_ratio == -1) scores 0. Nothing is fitted, so this is genuinely the rule
    layer and not a model of it.
    """

    name = "baseline1_rule"

    def __init__(self, labels: list[str], saturation: float = 2.0):
        self.labels, self.saturation = labels, saturation

    def fit(self, X, y=None, **_):
        self.cols_ = [f"policy_due_ratio__{c}" for c in self.labels]
        return self

    def predict_proba(self, X: pd.DataFrame):
        r = X[self.cols_].to_numpy(dtype="float64")
        r = np.where(r < 0, 0.0, r)
        # ratio / (1 + ratio): monotone in the due ratio, 0.5 exactly at the
        # interval, and -- unlike clipping -- it never ties every overdue task at
        # 1.0, which would destroy the ranking the top-K metrics measure.
        return r / (1.0 + r)


class RuleProjectedBaseline:
    """BASELINE 1b -- the OEM rule as a workshop would actually apply it.

    Baseline 1 answers "what is due *today*", but the target is what happens at
    the next visit, which is typically weeks away. Evaluated at the landmark the
    rule therefore under-fires systematically: only 22% of landmarks are overdue
    for an oil change, yet 88% of next services contain one.

    This baseline projects forward deterministically. ``t*`` is the number of
    days until the *first* task in the plan reaches its interval -- the workshop's
    natural next service date under pure OEM logic -- and every task is then
    scored by its due ratio at ``t*``. No fitting, no learned parameter: the
    intervals come from ``maintenance_policies.csv`` and the projection speed from
    the motorcycle's own observed km/day at the landmark.
    """

    name = "baseline1b_rule_projected"
    _DAYS_PER_MONTH = 30.4375

    def __init__(self, labels: list[str], intervals: dict, max_project_days: float = 365.0):
        self.labels, self.intervals = labels, intervals
        self.max_project_days = max_project_days

    def fit(self, X, y=None, **_):
        return self

    def _components(self, X: pd.DataFrame):
        n, L = len(X), len(self.labels)
        km_int = np.full((n, L), np.nan)
        mo_int = np.full((n, L), np.nan)
        groups = X["policy_group"].to_numpy() if "policy_group" in X else None
        for j, code in enumerate(self.labels):
            if groups is None:
                continue
            pair = [self.intervals.get((g, code), (np.nan, np.nan)) for g in groups]
            km_int[:, j] = [p[0] for p in pair]
            mo_int[:, j] = [p[1] for p in pair]
        km_since = X[[f"km_since__{c}" for c in self.labels]].to_numpy(dtype="float64")
        d_since = X[[f"days_since__{c}" for c in self.labels]].to_numpy(dtype="float64")
        never = X[[f"hist_count__{c}" for c in self.labels]].to_numpy(dtype="float64") == 0
        odo = X["current_odometer_km_at_landmark"].to_numpy(dtype="float64")[:, None]
        age = X["ownership_age_days"].to_numpy(dtype="float64")[:, None]
        km_since = np.where(never, np.repeat(odo, L, axis=1), km_since)
        d_since = np.where(never, np.repeat(age, L, axis=1), d_since)
        return km_int, mo_int, km_since, d_since

    def predict_proba(self, X: pd.DataFrame):
        km_int, mo_int, km_since, d_since = self._components(X)
        kmpd = X["avg_km_per_day_since_last_service"].to_numpy(dtype="float64")
        fallback = X["annual_km_baseline"].to_numpy(dtype="float64") / 365.25
        kmpd = np.where(np.isfinite(kmpd) & (kmpd > 0), kmpd, fallback)
        kmpd = np.where(np.isfinite(kmpd) & (kmpd > 0), kmpd, 1.0)[:, None]

        with np.errstate(invalid="ignore", divide="ignore"):
            days_to_km_due = (km_int - km_since) / kmpd
            days_to_mo_due = mo_int * self._DAYS_PER_MONTH - d_since
            days_to_due = np.fmin(days_to_km_due, days_to_mo_due)
        days_to_due = np.where(np.isfinite(days_to_due), days_to_due, np.inf)
        # t* = days until the NEXT task falls due. Tasks already overdue are
        # skipped rather than pinned to 0: on a fleet with ~30 policy tasks there
        # is nearly always something overdue, and treating that as "the service
        # is today" collapsed the projection to a no-op.
        future = np.where(days_to_due > 0, days_to_due, np.inf)
        t = future.min(axis=1)
        t = np.clip(np.where(np.isfinite(t), t, 0.0), 0.0, self.max_project_days)[:, None]
        self.last_projection_days_ = t.ravel()

        with np.errstate(invalid="ignore", divide="ignore"):
            km_ratio = (km_since + t * kmpd) / km_int
            mo_ratio = (d_since + t) / (mo_int * self._DAYS_PER_MONTH)
        ratio = np.fmax(np.nan_to_num(km_ratio, nan=-1.0), np.nan_to_num(mo_ratio, nan=-1.0))
        ratio = np.where(ratio < 0, 0.0, ratio)
        return ratio / (1.0 + ratio)


class RecurrenceBaseline:
    """BASELINE 2 -- personal task recurrence, smoothed toward global prevalence.

    ``p = (own occurrences of the task + a * global prevalence) / (own prior
    services + a)``, then boosted by whether the task is overdue on its own
    historical cadence. Uses only prior task history and the landmark's service
    count -- no policy table, no fitted coefficients beyond the TRAIN prevalence
    and the smoothing constant.
    """

    name = "baseline2_recurrence"

    def __init__(self, labels: list[str], smoothing: float = 5.0):
        self.labels, self.smoothing = labels, smoothing

    def fit(self, X, y, **_):
        self.prior_ = np.asarray(y).mean(axis=0)
        return self

    def predict_proba(self, X: pd.DataFrame):
        n_prior = X["prior_service_count"].to_numpy(dtype="float64")
        cnt = X[[f"hist_count__{c}" for c in self.labels]].to_numpy(dtype="float64")
        a = self.smoothing
        rate = (cnt + a * self.prior_[None, :]) / (n_prior[:, None] + a)
        # a task overdue relative to its own observed cadence is more likely now
        days = X[[f"days_since__{c}" for c in self.labels]].to_numpy(dtype="float64")
        seen = cnt > 0
        with np.errstate(invalid="ignore", divide="ignore"):
            cadence = np.where(seen & (cnt > 0), days / np.maximum(cnt, 1), np.nan)
        med = np.nanmedian(np.where(np.isfinite(cadence), cadence, np.nan), axis=0)
        med = np.where(np.isfinite(med) & (med > 0), med, 1.0)
        overdue = np.where(seen, np.clip(days / med[None, :], 0, 2) / 2, 0.5)
        return np.clip(rate * (0.5 + overdue), 0, 1)


# --------------------------------------------------------------------------
# Binary-relevance learners
# --------------------------------------------------------------------------

class BinaryRelevance:
    """One classifier per label, sharing a single fitted preprocessor.

    Labels with no positive (or no negative) in TRAIN fall back to the constant
    TRAIN prevalence instead of raising -- the tournament must not die because
    one low-frequency label happened to be empty in a fold.
    """

    def __init__(self, name: str, factory, feature_cols: list[str],
                 class_weight: bool = True):
        self.name, self.factory = name, factory
        self.feature_cols, self.class_weight = feature_cols, class_weight

    def fit(self, X: pd.DataFrame, y: np.ndarray, applicable: np.ndarray | None = None):
        self.pre_ = make_preprocessor(self.feature_cols)
        Xt = self.pre_.fit_transform(X[self.feature_cols])
        y = np.asarray(y)
        self.models_, self.const_ = [], np.zeros(y.shape[1])
        for j in range(y.shape[1]):
            yj = y[:, j]
            rows = applicable[:, j] if applicable is not None else np.ones(len(yj), bool)
            # a label is only trained on the bikes it can physically apply to
            Xj, yj_ = Xt[rows], yj[rows]
            if yj_.sum() < 5 or (len(yj_) - yj_.sum()) < 5:
                self.models_.append(None)
                self.const_[j] = yj.mean() if len(yj) else 0.0
                continue
            m = self.factory(j, yj_)
            m.fit(Xj, yj_)
            self.models_.append(m)
        return self

    def __getstate__(self):
        # ``factory`` is a closure and cannot be pickled, and inference never
        # needs it -- the fitted per-label models and the fitted preprocessor are
        # the whole artifact. Dropping it keeps the frozen champion loadable.
        return {k: v for k, v in self.__dict__.items() if k != "factory"}

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.factory = None

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        Xt = self.pre_.transform(X[self.feature_cols])
        out = np.empty((len(X), len(self.models_)))
        for j, m in enumerate(self.models_):
            if m is None:
                out[:, j] = self.const_[j]
            else:
                out[:, j] = m.predict_proba(Xt)[:, 1]
        return out


def _pos_weight(yj: np.ndarray) -> float:
    pos = max(int(yj.sum()), 1)
    return float((len(yj) - pos) / pos)


def candidate_models(feature_cols: list[str], seed: int = SEED) -> dict:
    """The Phase-12 tournament roster, restricted to already-installed libraries.

    Each gradient-boosted and linear family appears twice, class-rebalanced and
    not. That pairing *is* the Phase-13 imbalance experiment: rebalancing lifts
    per-label separation slightly but rescales every label's probability by its
    own positive rate, which destroys the cross-label comparability that top-K
    ranking and the displayed percentages both depend on.
    """
    reg: dict = {}

    def br(name, factory):
        reg[name] = lambda name=name, factory=factory: BinaryRelevance(name, factory, feature_cols)

    br("logreg_balanced", lambda j, yj: Pipeline([
        ("sc", StandardScaler()),
        ("lr", LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced",
                                  solver="lbfgs", random_state=seed))]))
    br("logreg", lambda j, yj: Pipeline([
        ("sc", StandardScaler()),
        ("lr", LogisticRegression(max_iter=2000, C=1.0, solver="lbfgs", random_state=seed))]))

    br("random_forest", lambda j, yj: RandomForestClassifier(
        n_estimators=200, min_samples_leaf=5, max_features="sqrt",
        n_jobs=-1, random_state=seed))
    br("extra_trees", lambda j, yj: ExtraTreesClassifier(
        n_estimators=200, min_samples_leaf=5, max_features="sqrt",
        n_jobs=-1, random_state=seed))

    try:
        from xgboost import XGBClassifier

        def _xgb(yj, balanced):
            return XGBClassifier(
                n_estimators=300, max_depth=5, learning_rate=0.08, subsample=0.9,
                colsample_bytree=0.7, min_child_weight=5, reg_lambda=1.0,
                scale_pos_weight=_pos_weight(yj) if balanced else 1.0,
                tree_method="hist", eval_metric="logloss", n_jobs=-1,
                random_state=seed, verbosity=0)

        br("xgboost", lambda j, yj: _xgb(yj, False))
        br("xgboost_balanced", lambda j, yj: _xgb(yj, True))
    except ImportError:
        pass

    try:
        from lightgbm import LGBMClassifier

        def _lgbm(balanced):
            return LGBMClassifier(
                n_estimators=300, num_leaves=31, learning_rate=0.08,
                min_child_samples=20, subsample=0.9, subsample_freq=1,
                colsample_bytree=0.7, class_weight="balanced" if balanced else None,
                n_jobs=-1, random_state=seed, verbose=-1)

        br("lightgbm", lambda j, yj: _lgbm(False))
        br("lightgbm_balanced", lambda j, yj: _lgbm(True))
    except ImportError:
        pass

    try:
        from catboost import CatBoostClassifier
        br("catboost", lambda j, yj: CatBoostClassifier(
            iterations=300, depth=6, learning_rate=0.08, l2_leaf_reg=3.0,
            verbose=0, allow_writing_files=False, thread_count=-1, random_seed=seed))
    except ImportError:
        pass

    return reg
