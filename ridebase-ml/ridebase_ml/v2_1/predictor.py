"""RideBase V2.1 dynamic-landmark survival — read-only production inference.

Loads the frozen Phase-3 artifacts (``models/v2_1_v1_4/``) and serves deterministic
30/60/90/120-day *service-return* probabilities for a landmark date.

Pipeline (exact training order, reproduced against the frozen TEST predictions):

    raw feature row (54-col contract)
      -> leakage / unknown-key guard
      -> preprocessor.transform            (fit on TRAIN only; transform-only here)
      -> XGB survival:cox score            (champion = xgb_cox)
      -> S(t) via persisted Breslow baseline cumulative hazard
      -> per-horizon isotonic calibration + cross-horizon monotonicity
      -> risk_30/60/90/120, median_service_days (raw curve), warnings, provenance

Status: SYNTHETICALLY VALIDATED (RideBase Synthetic Dataset v1.4 / V2.1 landmarks).
Real-fleet validation PENDING — never presented as production-validated.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd

from .landmarks import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES
from .survival import HORIZONS, survival_from_score

# target / censoring / future-information tokens that must never appear in an input row
_LEAK_TOKENS = (
    "duration_days", "event_observed", "next_service", "administrative_cutoff",
    "event_within_", "censor", "future_", "primary_split", "modeling_role",
    "is_unseen_motorcycle_holdout", "snapshot_year", "days_observed",
)
_MEDIAN_GRID = np.arange(1, 366)


class PredictionError(ValueError):
    """Invalid inference input (leakage keys, unknown fields, non-numeric values)."""


@dataclass
class V21SurvivalPredictor:
    model_dir: Path
    preprocessor: Any
    champion: Any
    baseline: dict[str, np.ndarray]
    calibrator: Any
    feature_cols: list[str]
    manifest: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    # ---- construction --------------------------------------------------------
    @classmethod
    def load(cls, model_dir: str | Path = None) -> "V21SurvivalPredictor":
        model_dir = Path(model_dir or Path(__file__).resolve().parents[2] / "models" / "v2_1_v1_4")
        need = ["preprocessor.joblib", "champion_model.joblib", "baseline_hazard.joblib",
                "calibrator.joblib", "feature_list.json"]
        missing = [n for n in need if not (model_dir / n).exists()]
        if missing:
            raise FileNotFoundError(f"V2.1 artifacts missing in {model_dir}: {missing}")
        feature_cols = json.loads((model_dir / "feature_list.json").read_text())
        if feature_cols != FEATURE_COLUMNS:
            raise RuntimeError("frozen feature_list.json does not match landmarks.FEATURE_COLUMNS")
        manifest = _maybe_json(model_dir / "artifact_manifest.json")
        metrics = _maybe_json(model_dir / "metrics.json")
        return cls(
            model_dir=model_dir,
            preprocessor=joblib.load(model_dir / "preprocessor.joblib"),
            champion=joblib.load(model_dir / "champion_model.joblib"),
            baseline=joblib.load(model_dir / "baseline_hazard.joblib"),
            calibrator=joblib.load(model_dir / "calibrator.joblib"),
            feature_cols=feature_cols,
            manifest=manifest,
            metrics=metrics,
        )

    # ---- core inference -----------------------------------------------------
    def _score(self, frame: pd.DataFrame) -> np.ndarray:
        matrix = self.preprocessor.transform(frame[self.feature_cols]).astype(np.float32)
        return np.asarray(self.champion.predict(matrix), dtype=float)

    def _calibrated_risk(self, score: np.ndarray) -> np.ndarray:
        raw = 1.0 - survival_from_score(score, self.baseline)
        return self.calibrator.transform(raw)

    def _median_days(self, score: np.ndarray) -> list[float | None]:
        # first day the *raw* survival curve crosses 0.5 (consistent with the shown curve)
        surv = survival_from_score(score, self.baseline, _MEDIAN_GRID.astype(float))
        out: list[float | None] = []
        for row in surv:
            hit = np.argmax(row < 0.5)
            out.append(float(_MEDIAN_GRID[hit]) if row[hit] < 0.5 else None)
        return out

    def predict(self, rows: Iterable[dict], strict: bool = False) -> dict[str, Any]:
        started = time.perf_counter()
        rows = list(rows)
        if not rows:
            raise PredictionError("no input rows")
        frame = pd.DataFrame([self._canonical_row(r, strict) for r in rows])
        score = self._score(frame)
        risk = self._calibrated_risk(score)
        median = self._median_days(score)
        preds = []
        for i, raw_row in enumerate(rows):
            r = {f"risk_{int(h)}d": round(float(risk[i, j]), 6) for j, h in enumerate(HORIZONS)}
            r["median_service_days"] = median[i]
            r["risk_score"] = round(float(score[i]), 6)
            r["warnings"] = self._warnings(frame.iloc[i])
            preds.append(r)
        return {
            "n": len(preds),
            "predictions": preds,
            "horizons_days": [int(h) for h in HORIZONS],
            "model": self.model_info(),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    # ---- input handling ---------------------------------------------------
    def _canonical_row(self, raw: dict, strict: bool) -> dict:
        for key in raw:
            lk = str(key).lower()
            if any(tok in lk for tok in _LEAK_TOKENS):
                raise PredictionError(f"leakage/target field not allowed in input: {key!r}")
        unknown = [k for k in raw if k not in self.feature_cols]
        if unknown and strict:
            raise PredictionError(f"unknown feature(s): {unknown[:8]}")
        row: dict[str, Any] = {}
        for col in self.feature_cols:
            v = raw.get(col, None)
            if col in NUMERIC_FEATURES and v is not None:
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    raise PredictionError(f"feature {col!r} must be numeric, got {v!r}")
                if not np.isfinite(v):
                    v = np.nan
            row[col] = v if v is not None else (np.nan if col in NUMERIC_FEATURES else None)
        return row

    def _warnings(self, row: pd.Series) -> list[str]:
        w: list[str] = []
        missing = [c for c in self.feature_cols
                   if (c in NUMERIC_FEATURES and pd.isna(row[c])) or (c in CATEGORICAL_FEATURES and row[c] in (None, "", np.nan))]
        if missing:
            w.append(f"{len(missing)}/{len(self.feature_cols)} features missing — imputed by the frozen preprocessor: {missing[:6]}")
        odo = row.get("current_odometer_km_at_landmark")
        if pd.notna(odo) and (odo < 0 or odo > 400_000):
            w.append(f"current_odometer_km_at_landmark={odo:.0f} is outside the training range")
        ratio = row.get("max_due_ratio")
        if pd.notna(ratio) and ratio > 6:
            w.append(f"max_due_ratio={ratio:.1f} is far past any training example — extrapolation")
        ann = row.get("annual_km_baseline")
        if pd.notna(ann) and (ann < 200 or ann > 60_000):
            w.append(f"annual_km_baseline={ann:.0f} km/yr is outside the training range")
        return w

    # ---- metadata --------------------------------------------------------
    def model_info(self) -> dict[str, Any]:
        sel = self.metrics.get("selected", {})
        return {
            "family": "V2.1 dynamic-landmark survival",
            "champion": sel.get("champion", "xgb_cox"),
            "calibration_method": sel.get("calibration_method", "isotonic"),
            "dataset_version": self.metrics.get("data_freeze", {}).get("dataset_version", "1.4.0-v2.1-dynamic-landmark"),
            "target": "probability the next eligible DELIVERED service occurs within the horizon, measured from the landmark date",
            "not_target": "this is NOT maintenance-due probability",
            "feature_count": len(self.feature_cols),
            "model_validation": "SYNTHETICALLY_VALIDATED",
            "real_fleet_validation": "PENDING",
            "artifact_manifest": self.manifest,
        }

    def features(self) -> dict[str, Any]:
        return {
            "feature_count": len(self.feature_cols),
            "categorical": CATEGORICAL_FEATURES,
            "numeric": NUMERIC_FEATURES,
            "contract": self.feature_cols,
            "forbidden_input_tokens": list(_LEAK_TOKENS),
        }


def _maybe_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


if __name__ == "__main__":
    # smoke: reload and reproduce the frozen TEST predictions (golden parity)
    from .golden_parity import run

    run()
