"""Deterministic, read-only production inference for the frozen FULL/FINAL V2 survival ensemble.

Pipeline (exact training-time order, reproduced bit-for-bit against nb15's TEST predictions):

    raw input dict
      -> leakage / schema validation
      -> canonical raw row (117 cols, training order; missing handled by the persisted preprocessor)
      -> preprocessor.transform  (fit on TRAIN only; transform-only here)
      -> XGB survival:cox  S(t)  via persisted Breslow baseline hazard H0
      -> CoxNet            S(t)
      -> per-model per-horizon IPCW-isotonic calibration + cross-horizon monotonicity
      -> ensemble blend  (weights from config: 0.6 XGB-Cox / 0.4 CoxNet)
      -> risk_30/60/90/120, median_service_days (raw XGB-Cox curve), risk_group_90d
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd
import xgboost as xgb

from .loader import V2Bundle, load_bundle, model_metadata

_TGRID = np.arange(1, 1001)                      # day grid for the median-service-day search
_LEAK_TOKENS = ("duration_days", "event_observed", "next_service", "next_event", "censor",
                "future_", "survival_target", "_audit", "target_event", "days_to_event",
                "time_to_event", "is_right_censored")
_SPLIT_SENTINEL = "__inference__"                # 'split' is an inert frozen-feature-set artifact


class PredictionError(ValueError):
    """Raised for invalid inference input (leakage keys, unknown fields, bad values)."""


def _model_times(model) -> np.ndarray:
    for a in ("event_times_", "unique_times_"):
        if hasattr(model, a):
            return np.asarray(getattr(model, a))
    raise AttributeError("survival model exposes no time attribute")


def _xgbcox_S(booster, H0_grid: np.ndarray, X: np.ndarray, times: Iterable[int]) -> np.ndarray:
    hr = booster.predict(xgb.DMatrix(X))
    S = np.exp(-np.outer(hr, H0_grid))           # (n, len(grid)); grid == _TGRID
    return np.clip(S[:, [t - 1 for t in times]], 0.0, 1.0)


def _coxnet_S(model, alpha: float, X: np.ndarray, times: Iterable[int]) -> np.ndarray:
    arr = model.predict_survival_function(X, alpha=alpha, return_array=True)
    mts = _model_times(model)
    cols = [max(0, int(np.searchsorted(mts, t, side="right") - 1)) for t in times]
    return np.clip(np.column_stack([arr[:, k] for k in cols]), 0.0, 1.0)


@dataclass
class V2SurvivalPredictor:
    bundle: V2Bundle

    # ---- construction -------------------------------------------------------
    @classmethod
    def load(cls, models_dir: str, verify_checksums: bool = True) -> "V2SurvivalPredictor":
        return cls(load_bundle(models_dir, verify_checksums=verify_checksums))

    def __post_init__(self) -> None:
        b = self.bundle
        self.cfg = b.config
        self.horizons: list[int] = [int(h) for h in b.horizons]
        self.all_h: list[int] = [int(h) for h in b.champion.get("all_h", self.horizons)]
        self.feature_cols: list[str] = b.feature_cols
        self.cat_cols = set(self.bundle.feature_catalog.get("categorical", []))
        self.num_cols = set(self.bundle.feature_catalog.get("numeric", []))
        self.stats: dict[str, dict] = self.bundle.feature_catalog.get("stats", {})
        self.options: dict[str, list] = self.bundle.feature_catalog.get("options", {})
        w = b.ensemble_weights
        self.w_xgb, self.w_coxnet = float(w["XGB_COX"]), float(w["COXNET"])
        self._xgb = b.champion["xgb_cox_model"]
        self._H0 = np.asarray(b.champion["xgb_cox_H0"], dtype=float)
        self._coxnet = b.champion["coxnet"]
        self._coxnet_alpha = float(b.champion["coxnet_alpha"])
        self._cal = b.calibrator                            # {"XGB_COX": {h: iso}, "COXNET": {h: iso}}
        self._ensemble_ok = {"XGB_COX", "COXNET"} <= set(self._cal)
        thr = b.risk_group_thresholds
        self._low_max, self._med_max = thr["low_max"], thr["medium_max"]
        # calibration-quality labels come from the report/config, never hard-coded here
        self.calibration_quality: dict[int, str] = {
            int(h): q for h, q in (self.bundle.feature_catalog.get("calibration_quality") or {}).items()
        } or {30: "GOOD", 60: "MODERATE", 90: "MODERATE", 120: "MODERATE"}

    # ---- feature building -------------------------------------------------------
    def _validate_keys(self, raw: dict[str, Any]) -> None:
        for k in raw:
            lk = str(k).lower()
            if any(tok in lk for tok in _LEAK_TOKENS):
                raise PredictionError(f"leakage/target field not allowed in inference input: {k!r}")
        unknown = [k for k in raw if k not in self.feature_cols and k not in ("snapshot_date",)]
        if unknown:
            raise PredictionError(f"unknown feature(s): {unknown[:8]}"
                                  + (" ..." if len(unknown) > 8 else ""))

    @staticmethod
    def _is_missing(v: Any) -> bool:
        return v is None or (isinstance(v, float) and v != v)   # None or NaN

    @staticmethod
    def _is_inf(v: Any) -> bool:
        return isinstance(v, float) and v in (float("inf"), float("-inf"))

    def _canonical_row(self, raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        row: dict[str, Any] = {}
        for c in self.feature_cols:
            if c == "split":
                row[c] = _SPLIT_SENTINEL
                continue
            v = raw.get(c, None)
            if c in self.cat_cols:
                if self._is_missing(v) or self._is_inf(v):
                    row[c] = "nan"          # matches training-time str(NaN) handling
                else:
                    sv = str(v)
                    opts = self.options.get(c)
                    if sv not in ("nan", "") and opts and sv not in opts:
                        warnings.append(f"{c}: unseen category {sv!r} (handled as UNKNOWN)")
                    row[c] = sv
            else:
                if self._is_missing(v):
                    row[c] = np.nan
                    continue
                if self._is_inf(v):
                    raise PredictionError(f"{c}: non-finite value (inf) — not allowed")
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    raise PredictionError(f"{c}: expected a number, got {v!r}")
                if not np.isfinite(fv):
                    raise PredictionError(f"{c}: non-finite value")
                if c in ("motorcycle_age_years", "ownership_months", "production_year",
                         "initial_mileage_km", "engine_displacement_cc", "days_since_previous_service",
                         "km_since_previous_service", "previous_service_count") and fv < 0:
                    raise PredictionError(f"{c}: negative value {fv} — not physically valid")
                st = self.stats.get(c)
                if st and st.get("p01") is not None and st.get("p99") is not None:
                    lo, hi = st["p01"], st["p99"]
                    if fv < lo - abs(lo) or fv > hi * 3 + abs(hi):
                        warnings.append(
                            f"{c}={fv:g} far outside training range [{lo:g}, {hi:g}] (out-of-distribution)")
                    elif fv < lo or fv > hi:
                        warnings.append(f"{c}={fv:g} outside training p01–p99 [{lo:g}, {hi:g}]")
                row[c] = fv
        return row, warnings

    def _encode(self, rows: list[dict[str, Any]]) -> np.ndarray:
        df = pd.DataFrame(rows, columns=self.feature_cols)
        cast = {c: str for c in self.feature_cols if c in self.cat_cols}
        X = self.bundle.preprocessor.transform(df.astype(cast))
        return np.asarray(X, dtype=np.float64)

    # ---- survival + calibration + blend --------------------------------------
    def _calibrate(self, model_key: str, S_allh: np.ndarray) -> np.ndarray:
        maps = self._cal[model_key]
        risk = 1.0 - S_allh
        out = risk.copy()
        for h in self.horizons:
            j = self.all_h.index(h)
            out[:, j] = maps[h].predict(risk[:, j])
        hc = [self.all_h.index(h) for h in self.horizons]
        out[:, hc] = np.maximum.accumulate(out[:, hc], axis=1)   # cross-horizon monotonicity
        return np.clip(1.0 - out, 0.0, 1.0)

    def _score(self, X: np.ndarray) -> dict[str, np.ndarray]:
        """One forward pass: raw per-model S(t), calibrated blend, and the median-days curve."""
        if not self._ensemble_ok:
            raise RuntimeError("calibrator artifact lacks COXNET maps — ensemble inference unavailable")
        hr_xgb = self._xgb.predict(xgb.DMatrix(X))
        s_xgb = np.clip(np.exp(-np.outer(hr_xgb, self._H0))[:, [t - 1 for t in self.all_h]], 0.0, 1.0)
        s_cox = _coxnet_S(self._coxnet, self._coxnet_alpha, X, self.all_h)
        blend = np.clip(self.w_xgb * self._calibrate("XGB_COX", s_xgb)
                        + self.w_coxnet * self._calibrate("COXNET", s_cox), 0.0, 1.0)
        Sg = np.exp(-np.outer(hr_xgb, self._H0))          # raw XGB-Cox curve for the median (nb15 contract)
        below = Sg <= 0.5
        med = np.full(Sg.shape[0], np.nan)
        has = below.any(axis=1)
        med[has] = _TGRID[below.argmax(axis=1)[has]]
        return {"blend": blend, "raw_xgb": s_xgb, "raw_cox": s_cox, "median": med}

    def _risk_group(self, r90: np.ndarray) -> np.ndarray:
        return np.where(r90 <= self._low_max, "LOW",
                        np.where(r90 <= self._med_max, "MEDIUM", "HIGH"))

    # ---- public API -------------------------------------------------------------
    def predict(self, snapshot: dict[str, Any], strict: bool = False) -> dict[str, Any]:
        out = self.predict_batch([snapshot], strict=strict)
        return out["predictions"][0]

    def predict_batch(self, snapshots: list[dict[str, Any]], strict: bool = False) -> dict[str, Any]:
        if not isinstance(snapshots, list) or not snapshots:
            raise PredictionError("expected a non-empty list of snapshot dicts")
        t0 = time.perf_counter()
        rows, warns, snap_dates = [], [], []
        for i, raw in enumerate(snapshots):
            if not isinstance(raw, dict):
                raise PredictionError(f"row {i}: expected an object, got {type(raw).__name__}")
            self._validate_keys(raw)
            row, w = self._canonical_row(raw)
            if strict and w:
                raise PredictionError(f"row {i}: {w[0]}")
            rows.append(row)
            warns.append(w)
            snap_dates.append(raw.get("snapshot_date"))
        X = self._encode(rows)

        sc = self._score(X)
        raw_S_xgb, raw_S_cox, med = sc["raw_xgb"], sc["raw_cox"], sc["median"]
        risk = 1.0 - sc["blend"][:, [self.all_h.index(h) for h in self.horizons]]
        grp = self._risk_group(risk[:, self.horizons.index(90)])

        # hard probability contract
        bad_bounds = int(((risk < -1e-9) | (risk > 1 + 1e-9)).any(axis=1).sum())
        bad_mono = int((np.diff(risk, axis=1) < -1e-9).any(axis=1).sum())
        if bad_bounds or bad_mono:
            raise RuntimeError(
                f"probability contract violated (bounds={bad_bounds}, monotonicity={bad_mono}) — refusing output")

        preds = []
        for i in range(len(snapshots)):
            p = {f"risk_{h}d": round(float(risk[i, k]), 8) for k, h in enumerate(self.horizons)}
            m = med[i]
            p["median_service_days"] = None if not np.isfinite(m) else int(m)
            p["risk_group_90d"] = str(grp[i])
            sd = snap_dates[i]
            if sd and p["median_service_days"] is not None:
                try:
                    p["estimated_median_service_date"] = (
                        pd.Timestamp(sd).normalize() + pd.Timedelta(days=p["median_service_days"])
                    ).date().isoformat()
                except Exception:
                    pass
            p["raw_ensemble_risk"] = {
                f"{h}d": round(float(self.w_xgb * (1 - raw_S_xgb[i, self.all_h.index(h)])
                                    + self.w_coxnet * (1 - raw_S_cox[i, self.all_h.index(h)])), 6)
                for h in self.horizons}
            if warns[i]:
                p["warnings"] = warns[i]
            preds.append(p)

        return {
            "predictions": preds,
            "model": self.model_summary(),
            "calibration": {f"{h}d": self.calibration_quality.get(h, "UNKNOWN") for h in self.horizons},
            "warning": "Real-fleet validation pending. Model is SYNTHETICALLY VALIDATED on RideBase "
                       "Synthetic Dataset v1.3 only.",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "n": len(snapshots),
        }

    # ---- metadata -------------------------------------------------------------
    def model_summary(self) -> dict[str, Any]:
        c = self.cfg
        return {
            "version": c.get("training_timestamp", "v2-full-final"),
            "family": c.get("model_name"),
            "dataset_version": c.get("dataset_version"),
            "run_mode": c.get("run_mode"),
            "status": "SYNTHETICALLY_VALIDATED",
            "real_fleet_validation": "PENDING",
        }

    def model_info(self) -> dict[str, Any]:
        return model_metadata(self.bundle)

    def features(self) -> dict[str, Any]:
        return {
            "feature_count": len(self.feature_cols),
            "feature_order": self.feature_cols,
            "categorical": sorted(self.cat_cols),
            "numeric": sorted(self.num_cols),
            "options": self.options,
            "stats": self.stats,
            "note": "The API never lets the caller choose the raw feature order — it is fixed by the "
                    "frozen preprocessor. 'split' is an inert frozen-feature-set artifact and is set "
                    "internally; do not send it.",
        }

    def sample_snapshot(self) -> dict[str, Any]:
        """A production-safe example request built from training medians / modes."""
        s: dict[str, Any] = {}
        for c in self.feature_cols:
            if c == "split":
                continue
            if c in self.cat_cols:
                opts = self.options.get(c)
                if opts:
                    s[c] = opts[0]
            else:
                st = self.stats.get(c)
                if st and st.get("p50") is not None:
                    s[c] = st["p50"]
        return s
