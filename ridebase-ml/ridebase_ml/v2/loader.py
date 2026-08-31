"""Load + verify the frozen FULL/FINAL V2 survival ensemble artifacts. No training here."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib

# artifacts that make up the production bundle (relative to the models dir)
CHAMPION = "v2_advanced_champion.joblib"
PREPROCESSOR = "v2_advanced_preprocessor.joblib"
CALIBRATOR_FULL = "v2_advanced_calibrator_full.joblib"   # {"XGB_COX": {h: iso}, "COXNET": {h: iso}}
CALIBRATOR_LEGACY = "v2_advanced_calibrator.joblib"       # champion-only {h: iso} (nb15 output)
CONFIG = "v2_advanced_config.json"
FEATURE_CATALOG = "v2_feature_catalog.json"
BUNDLE_MANIFEST = "v2_production_bundle_manifest.json"

REQUIRED = [CHAMPION, PREPROCESSOR, CONFIG]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class V2Bundle:
    models_dir: Path
    config: dict[str, Any]
    champion: dict[str, Any]
    preprocessor: Any
    calibrator: dict[str, dict[int, Any]]      # {"XGB_COX": {30: iso, ...}, "COXNET": {...}}
    feature_catalog: dict[str, Any]
    checksums: dict[str, str] = field(default_factory=dict)
    checksum_status: str = "UNVERIFIED"

    # --- convenience accessors, all config-driven ---
    @property
    def dataset_version(self) -> str:
        return self.config.get("dataset_version", "unknown")

    @property
    def run_mode(self) -> str:
        return self.config.get("run_mode", "unknown")

    @property
    def status(self) -> str:
        return self.config.get("status", "unknown")

    @property
    def model_name(self) -> str:
        return self.config.get("model_name", "unknown")

    @property
    def horizons(self) -> list[int]:
        return list(self.config.get("horizons", [30, 60, 90, 120]))

    @property
    def ensemble_weights(self) -> dict[str, float]:
        return dict(self.config.get("ensemble_weights") or {})

    @property
    def feature_cols(self) -> list[str]:
        return list(self.config.get("feature_cols", []))

    @property
    def risk_group_thresholds(self) -> dict[str, float]:
        t = self.config.get("risk_group_thresholds") or {}
        return {"low_max": float(t.get("low_max", 0.0)), "medium_max": float(t.get("medium_max", 0.5))}


def _guard(config: dict[str, Any]) -> None:
    problems = []
    if not str(config.get("dataset_version", "")).startswith("1.3"):
        problems.append(f"dataset_version={config.get('dataset_version')!r} (expected 1.3.x)")
    if config.get("run_mode") != "FULL":
        problems.append(f"run_mode={config.get('run_mode')!r} (expected FULL)")
    if config.get("status") != "FINAL":
        problems.append(f"status={config.get('status')!r} (expected FINAL)")
    if config.get("model_name") != "ENSEMBLE[XGB_COX+COXNET]":
        problems.append(f"model_name={config.get('model_name')!r} (expected ENSEMBLE[XGB_COX+COXNET])")
    if config.get("calibration_method") != "isotonic_ipcw":
        problems.append(f"calibration_method={config.get('calibration_method')!r}")
    w = config.get("ensemble_weights") or {}
    if not (abs(sum(w.values()) - 1.0) < 1e-6 and {"XGB_COX", "COXNET"} <= set(w)):
        problems.append(f"ensemble_weights={w!r}")
    if len(config.get("feature_cols", [])) < 10:
        problems.append("feature_cols missing / too short")
    if problems:
        raise RuntimeError("V2 final-model guard FAILED:\n  - " + "\n  - ".join(problems))


def load_bundle(models_dir: str | Path, verify_checksums: bool = True) -> V2Bundle:
    md = Path(models_dir).expanduser().resolve()
    missing = [f for f in REQUIRED if not (md / f).exists()]
    if missing:
        raise FileNotFoundError(f"V2 artifacts missing in {md}: {missing}")

    config = json.loads((md / CONFIG).read_text())
    _guard(config)

    champion = joblib.load(md / CHAMPION)
    preprocessor = joblib.load(md / PREPROCESSOR)

    # calibrator: prefer the full per-model dict; fall back to reconstructing the
    # COXNET maps is NOT done here (that's a packaging step) — the full artifact must exist.
    if (md / CALIBRATOR_FULL).exists():
        calibrator = joblib.load(md / CALIBRATOR_FULL)
    elif (md / CALIBRATOR_LEGACY).exists():
        legacy = joblib.load(md / CALIBRATOR_LEGACY)
        # legacy artifact only carries the champion (XGB_COX) maps — usable only if the
        # ensemble is disabled; flag it so the predictor can refuse ensemble mode.
        calibrator = {"XGB_COX": legacy}
    else:
        raise FileNotFoundError(
            f"no calibrator artifact ({CALIBRATOR_FULL} or {CALIBRATOR_LEGACY}) in {md}")
    # normalise horizon keys to int
    calibrator = {k: {int(h): iso for h, iso in v.items()} for k, v in calibrator.items()}

    feature_catalog = {}
    if (md / FEATURE_CATALOG).exists():
        feature_catalog = json.loads((md / FEATURE_CATALOG).read_text())

    checksums, cstatus = {}, "SKIPPED"
    if verify_checksums:
        for f in [CHAMPION, PREPROCESSOR, CONFIG] + (
            [CALIBRATOR_FULL] if (md / CALIBRATOR_FULL).exists() else [CALIBRATOR_LEGACY]
        ) + ([FEATURE_CATALOG] if (md / FEATURE_CATALOG).exists() else []):
            checksums[f] = sha256(md / f)
        cstatus = "COMPUTED"
        bm = md / BUNDLE_MANIFEST
        if bm.exists():
            recorded = (json.loads(bm.read_text()).get("checksums") or {})
            mism = {f: (recorded.get(f), checksums[f]) for f in checksums
                    if f in recorded and recorded[f] != checksums[f]}
            cstatus = "VERIFIED_OK" if not mism else f"MISMATCH:{list(mism)}"

    return V2Bundle(
        models_dir=md, config=config, champion=champion, preprocessor=preprocessor,
        calibrator=calibrator, feature_catalog=feature_catalog,
        checksums=checksums, checksum_status=cstatus,
    )


def model_metadata(bundle: V2Bundle) -> dict[str, Any]:
    c = bundle.config
    return {
        "model_version": c.get("training_timestamp", "v2-full-final"),
        "model_family": c.get("model_name"),
        "dataset_version": c.get("dataset_version"),
        "run_mode": c.get("run_mode"),
        "status": "SYNTHETICALLY_VALIDATED",
        "real_fleet_validation": "PENDING",
        "ensemble_weights": c.get("ensemble_weights"),
        "calibration_method": c.get("calibration_method"),
        "feature_count": len(c.get("feature_cols", [])),
        "feature_set": c.get("feature_set"),
        "horizons": c.get("horizons"),
        "risk_group_thresholds": c.get("risk_group_thresholds"),
        "training_timestamp": c.get("training_timestamp"),
        "optuna_trials": c.get("optuna_trials"),
        "temporal_folds": c.get("temporal_folds"),
        "grouped_bootstrap_reps": c.get("grouped_bootstrap_reps"),
        "validation_metrics": c.get("validation_metrics"),
        "test_metrics": c.get("test_metrics"),
        "note": "Synthetically validated on RideBase Synthetic Dataset v1.3. NOT production-validated. "
                "Real-fleet validation pending.",
    }
