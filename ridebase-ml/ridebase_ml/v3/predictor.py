"""V3 offline multi-label task predictor (Phases 25-26).

RESEARCH ONLY. This class is never mounted on a production route and is not
imported by the RideBase backend. It exists so the frozen V3 champion can be
exercised reproducibly offline and so the response contract can be tested.

    from ridebase_ml.v3.predictor import V3TaskPredictor
    p = V3TaskPredictor.load("ridebase-ml/models/v3_research")
    p.predict(feature_row)          # one landmark -> V3Prediction
    p.predict_batch(feature_frame)  # many landmarks

A V3 response never contains a Maintenance Urgency score or a V2.1
service-return probability. Those are separate product surfaces with separate
semantics, and mixing them into one payload is how a task probability gets
misread as a failure probability.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from . import V3_VERSION

#: probability below which a task is not worth showing at all
DISPLAY_FLOOR = 0.01


class V3PredictionError(ValueError):
    """Invalid inference input (missing features, leakage keys, non-finite values)."""


#: input keys that must never be supplied -- they describe the target service or
#: identify the row, and their presence means the caller built the row wrong
_LEAK_TOKENS = (
    "target", "next_service", "future_", "duration_days", "event_observed",
    "censor", "administrative_cutoff", "split", "modeling_role", "lead_days",
    "motorcycle_id", "customer_id", "service_id", "landmark_id",
)


@dataclass
class TaskPrediction:
    task: str
    probability: float
    predicted: bool
    rank: int
    applicable: bool
    support_class: str


@dataclass
class V3Prediction:
    model_version: str
    status: str
    landmark_date: str | None
    predicted_tasks: list[dict]
    top_k: list[dict]
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class V3TaskPredictor:
    model: Any
    calibrator: Any
    labels: list[str]
    thresholds: np.ndarray
    feature_cols: list[str]
    manifest: dict
    label_classes: dict[str, str]
    taxonomy: pd.DataFrame

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, model_dir: str | Path, root: str | None = None) -> "V3TaskPredictor":
        from .sources import load_sources
        d = Path(model_dir)
        manifest = json.loads((d / "artifact_manifest.json").read_text())
        labels = json.loads((d / "label_list.json").read_text())["labels"]
        thr = np.asarray(json.loads((d / "thresholds.json").read_text())["thresholds"],
                         dtype="float64")
        feats = json.loads((d / "feature_list.json").read_text())["features"]
        classes = json.loads((d / "label_list.json").read_text())["label_classes"]
        return cls(
            model=joblib.load(d / "champion_model.joblib"),
            calibrator=joblib.load(d / "calibrator.joblib"),
            labels=labels, thresholds=thr, feature_cols=feats, manifest=manifest,
            label_classes=classes,
            taxonomy=load_sources(root)["maintenance_tasks"].set_index("task_code"),
        )

    # --------------------------------------------------------------- guards
    def _validate(self, X: pd.DataFrame) -> None:
        contract = set(self.feature_cols)
        for col in X.columns:
            if col in contract:
                continue  # already cleared by the Phase-8 name screen
            low = str(col).lower()
            hit = next((t for t in _LEAK_TOKENS if t in low), None)
            if hit:
                raise V3PredictionError(
                    f"input column {col!r} looks like target or identifier "
                    f"information (matched {hit!r}) and is not part of the V3 "
                    f"feature contract")
        missing = [c for c in self.feature_cols if c not in X.columns]
        if missing:
            raise V3PredictionError(
                f"{len(missing)} required feature(s) missing, e.g. {missing[:5]}")

    def applicability(self, X: pd.DataFrame, motorcycle_ids) -> np.ndarray:
        from .target import applicability_matrix
        m = applicability_matrix(pd.Index(pd.unique(motorcycle_ids)), self.labels)
        return m.reindex(np.asarray(motorcycle_ids))[self.labels].to_numpy(dtype=bool)

    # -------------------------------------------------------------- predict
    def predict_proba(self, X: pd.DataFrame, applicable: np.ndarray | None = None) -> np.ndarray:
        self._validate(X)
        raw = self.model.predict_proba(X[self.feature_cols])
        p = self.calibrator.transform(raw)
        if applicable is not None:
            p = np.where(applicable, p, 0.0)
        if not np.isfinite(p).all():
            raise V3PredictionError("model produced non-finite probabilities")
        return np.clip(p, 0.0, 1.0)

    def predict_batch(self, X: pd.DataFrame, motorcycle_ids=None, top_k: int = 5,
                      landmark_dates=None) -> list[V3Prediction]:
        app = self.applicability(X, motorcycle_ids) if motorcycle_ids is not None else None
        proba = self.predict_proba(X, app)
        dates = ([None] * len(X)) if landmark_dates is None else list(landmark_dates)
        out = []
        for i in range(len(X)):
            row_app = app[i] if app is not None else np.ones(len(self.labels), bool)
            out.append(self._response(proba[i], row_app, top_k, dates[i]))
        return out

    def predict(self, row, motorcycle_id: str | None = None, top_k: int = 5,
                landmark_date=None) -> V3Prediction:
        X = row.to_frame().T if isinstance(row, pd.Series) else pd.DataFrame(row)
        ids = [motorcycle_id] if motorcycle_id is not None else None
        return self.predict_batch(X, ids, top_k, [landmark_date])[0]

    # ------------------------------------------------------------- response
    def _response(self, p: np.ndarray, app: np.ndarray, top_k: int,
                  landmark_date) -> V3Prediction:
        order = np.argsort(-p, kind="stable")
        tasks = []
        for rank, j in enumerate(order, start=1):
            tasks.append(TaskPrediction(
                task=self.labels[j], probability=round(float(p[j]), 4),
                predicted=bool(p[j] >= self.thresholds[j]), rank=rank,
                applicable=bool(app[j]),
                support_class=self.label_classes.get(self.labels[j], "UNKNOWN"),
            ))
        shown = [asdict(t) for t in tasks if t.applicable and t.probability >= DISPLAY_FLOOR]

        warnings = []
        n_inapplicable = int((~app).sum())
        if n_inapplicable:
            warnings.append(
                f"{n_inapplicable} of {len(self.labels)} tasks are not applicable to this "
                f"motorcycle's powertrain/drivetrain and are forced to 0.0")
        low = [t.task for t in tasks[:top_k]
               if self.label_classes.get(t.task) == "B_LOW_FREQUENCY"]
        if low:
            warnings.append(
                f"low-support labels in the top {top_k}: {', '.join(low)} — these "
                f"clear the V3 modelling gate but have wide uncertainty")
        warnings.append(
            "V3 estimates which tasks may be performed at the next completed "
            "service. These are NOT mechanical failure probabilities, NOT a "
            "maintenance urgency score, and NOT a V2.1 service-return probability.")

        return V3Prediction(
            model_version=self.manifest.get("model_version", V3_VERSION),
            status="RESEARCH_OFFLINE_SYNTHETIC_ONLY",
            landmark_date=str(landmark_date) if landmark_date is not None else None,
            predicted_tasks=shown,
            top_k=[asdict(t) for t in tasks if t.applicable][:top_k],
            warnings=warnings,
            provenance={
                "source_world": self.manifest.get("source_world"),
                "champion_family": self.manifest.get("champion_family"),
                "label_count": len(self.labels),
                "labels_applicable": int(app.sum()),
                "threshold_policy": self.manifest.get("threshold_policy"),
                "calibration_policy": self.manifest.get("calibration_policy"),
                "target_semantics": (
                    "task recorded with status=COMPLETED on the first service "
                    "strictly after the landmark"),
                "real_fleet_validation": "PENDING — never claimed",
                "deployed": False,
            },
        )

    def model_info(self) -> dict:
        return {"model_version": self.manifest.get("model_version", V3_VERSION),
                "champion_family": self.manifest.get("champion_family"),
                "labels": self.labels, "label_count": len(self.labels),
                "feature_count": len(self.feature_cols),
                "thresholds": {l: float(t) for l, t in zip(self.labels, self.thresholds)},
                "manifest": self.manifest}
