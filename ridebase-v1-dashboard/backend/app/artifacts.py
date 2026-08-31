"""Artifact discovery + loading.

Strategy = LATEST VALID MODEL: prefer the notebook-12 final-tuning artifacts
(`v1_final_*`); if they are absent fall back to the notebook-10 v1.3 final
regression artifacts (`v1_3_final_*`). Nothing here fabricates a number - if a
table is missing the reader returns ``None`` and the API surfaces
"artifact not available".
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .config import settings

# ---------------------------------------------------------------- leakage guard
# no request field / model input may reference the target or any post-snapshot fact
LEAK_TOKENS = (
    "next_service_days",
    "days_to_next_service",
    "next_service_km",
    "km_to_next_service",
    "next_service_km_delta",
    "next_service_at",
    "next_service_date",
    "future_service",
    "actual_next",
    "target_",
    "is_right_censored",
    "target_event_observed",
    "survival_",
)


def contains_leak(name: str) -> str | None:
    low = name.lower()
    for tok in LEAK_TOKENS:
        if tok in low:
            return tok
    return None


# ---------------------------------------------------------------- feature meta
# user-facing label + explanation for the features that actually show up in the
# frozen models. Anything not listed falls back to a prettified name.
FEATURE_META: dict[str, dict[str, str]] = {
    "brand": {"label": "Marka", "explain": "Motosiklet markası.", "group": "Motorcycle"},
    "category": {"label": "Segment", "explain": "Motosiklet sınıfı (naked, scooter, adventure...).", "group": "Motorcycle"},
    "engine_displacement_cc": {"label": "Motor hacmi (cc)", "explain": "Motor silindir hacmi.", "group": "Motorcycle"},
    "cylinder_count": {"label": "Silindir sayısı", "explain": "Motordaki silindir adedi.", "group": "Motorcycle"},
    "powertrain_type": {"label": "Güç aktarımı", "explain": "İçten yanmalı (ICE) veya elektrikli (EV).", "group": "Motorcycle"},
    "fuel_type": {"label": "Yakıt tipi", "explain": "Benzin veya elektrik.", "group": "Motorcycle"},
    "cooling_type": {"label": "Soğutma", "explain": "Hava / sıvı / yağ soğutmalı.", "group": "Motorcycle"},
    "final_drive_type": {"label": "Nihai tahrik", "explain": "Zincir, kayış veya direkt.", "group": "Motorcycle"},
    "transmission_type": {"label": "Şanzıman", "explain": "Manuel, otomatik, CVT...", "group": "Motorcycle"},
    "production_year": {"label": "Üretim yılı", "explain": "Aracın model yılı.", "group": "Motorcycle"},
    "price_level": {"label": "Fiyat segmenti", "explain": "Düşük / orta / yüksek / premium.", "group": "Motorcycle"},
    "spark_plug_count": {"label": "Buji sayısı", "explain": "Bakım kapsamını etkiler.", "group": "Motorcycle"},
    "engine_oil_service_qty_l": {"label": "Motor yağı miktarı (L)", "explain": "Servis başına gereken yağ.", "group": "Motorcycle"},
    "motorcycle_age_years": {"label": "Araç yaşı (yıl)", "explain": "Snapshot tarihindeki araç yaşı.", "group": "Motorcycle"},
    "ownership_months": {"label": "Sahiplik süresi (ay)", "explain": "Mevcut sahibin araca sahip olduğu süre.", "group": "Motorcycle"},

    "usage_type": {"label": "Kullanım tipi", "explain": "Commuter, kurye, hafta sonu, offroad...", "group": "Usage"},
    "riding_intensity": {"label": "Kullanım yoğunluğu", "explain": "Düşük / orta / yüksek sürüş yoğunluğu.", "group": "Usage"},
    "annual_km_baseline": {"label": "Yıllık km beklentisi", "explain": "Profile göre beklenen yıllık kilometre.", "group": "Usage"},
    "recent_30d_km": {"label": "Son 30 gün km", "explain": "Son 30 gündeki tahmini kullanım.", "group": "Usage"},
    "recent_60d_km": {"label": "Son 60 gün km", "explain": "Son 60 gündeki tahmini kullanım.", "group": "Usage"},
    "recent_90d_km": {"label": "Son 90 gün km", "explain": "Son 90 gündeki tahmini kullanım.", "group": "Usage"},
    "recent_180d_km": {"label": "Son 180 gün km", "explain": "Son 180 gündeki tahmini kullanım.", "group": "Usage"},
    "recent_km_per_day": {"label": "Günlük km (son dönem)", "explain": "Son dönem ortalama günlük kilometre.", "group": "Usage"},
    "long_term_km_per_day": {"label": "Günlük km (uzun dönem)", "explain": "Tüm geçmişteki ortalama günlük kilometre.", "group": "Usage"},
    "recent_vs_long_term_usage_ratio": {"label": "Son / uzun dönem kullanım oranı", "explain": ">1 ise araç son dönemde daha çok kullanılıyor.", "group": "Usage"},
    "avg_km_per_active_day": {"label": "Aktif gün başına km", "explain": "Sadece kullanılan günlerde ortalama km.", "group": "Usage"},
    "avg_ride_days_per_week": {"label": "Haftalık sürüş günü", "explain": "Haftada ortalama kaç gün kullanılıyor.", "group": "Usage"},
    "daily_active_probability": {"label": "Günlük kullanım olasılığı", "explain": "Herhangi bir günde kullanılma olasılığı.", "group": "Usage"},
    "city_ratio": {"label": "Şehir içi oranı", "explain": "Sürüşün şehir içi payı.", "group": "Usage"},
    "highway_ratio": {"label": "Otoyol oranı", "explain": "Sürüşün otoyol payı.", "group": "Usage"},
    "offroad_ratio": {"label": "Arazi oranı", "explain": "Sürüşün arazi payı.", "group": "Usage"},
    "track_ratio": {"label": "Pist oranı", "explain": "Sürüşün pist payı.", "group": "Usage"},
    "load_severity_factor": {"label": "Yük ağırlığı faktörü", "explain": "Taşınan yük / kullanım sertliği.", "group": "Usage"},
    "winter_usage_factor": {"label": "Kış kullanım faktörü", "explain": "Kış aylarındaki kullanım düzeyi.", "group": "Usage"},
    "seasonality_strength": {"label": "Mevsimsellik gücü", "explain": "Kullanımın mevsime bağlılığı.", "group": "Usage"},
    "weather_sensitivity": {"label": "Hava duyarlılığı", "explain": "Kötü havada kullanımın düşme eğilimi.", "group": "Usage"},
    "storage_condition": {"label": "Saklama koşulu", "explain": "Garaj, kapalı otopark, sokak...", "group": "Usage"},
    "climate_zone": {"label": "İklim bölgesi", "explain": "Aracın bulunduğu iklim bölgesi.", "group": "Usage"},

    "snapshot_odometer_km": {"label": "Güncel kilometre", "explain": "Snapshot anındaki kilometre sayacı.", "group": "Mileage"},
    "initial_mileage_km": {"label": "İlk kilometre", "explain": "Kayda alındığındaki kilometre.", "group": "Mileage"},
    "current_mileage_estimated": {"label": "Kilometre tahmini mi?", "explain": "Kilometre ölçülen mi tahmin mi.", "group": "Mileage"},
    "current_mileage_quality_flag": {"label": "Kilometre kalitesi", "explain": "VALID veya ESTIMATED.", "group": "Mileage"},
    "current_mileage_source": {"label": "Kilometre kaynağı", "explain": "Müşteri beyanı / manuel / tahmin.", "group": "Mileage"},
    "is_left_truncated": {"label": "Geçmişi eksik mi?", "explain": "Aracın erken servis geçmişi veri setinde yok.", "group": "Mileage"},

    "previous_service_count": {"label": "Önceki servis sayısı", "explain": "Bugüne kadarki servis adedi (geçmiş derinliği).", "group": "Service history"},
    "service_sequence": {"label": "Servis sırası", "explain": "Bu servisin kaçıncı servis olduğu.", "group": "Service history"},
    "days_since_previous_service": {"label": "Son servisten bu yana gün", "explain": "En son servisin üzerinden geçen gün.", "group": "Service history"},
    "km_since_previous_service": {"label": "Son servisten bu yana km", "explain": "En son servisten sonra yapılan km.", "group": "Service history"},
    "previous_interval_days": {"label": "Önceki iki servis arası gün", "explain": "Bir önceki servis aralığı (gün).", "group": "Service history"},
    "previous_interval_km": {"label": "Önceki iki servis arası km", "explain": "Bir önceki servis aralığı (km).", "group": "Service history"},
    "historical_interval_days_median": {"label": "Tipik servis aralığı (gün)", "explain": "Geçmiş servisler arasındaki tipik gün sayısı.", "group": "Service history"},
    "historical_interval_days_std": {"label": "Servis aralığı sapması (gün)", "explain": "Servis aralığının değişkenliği (gün).", "group": "Service history"},
    "historical_interval_km_median": {"label": "Tipik servis aralığı (km)", "explain": "Geçmiş servisler arasındaki tipik km.", "group": "Service history"},
    "historical_interval_km_std": {"label": "Servis aralığı sapması (km)", "explain": "Servis aralığının değişkenliği (km).", "group": "Service history"},
    "avg_service_interval_days": {"label": "Ortalama servis aralığı (gün)", "explain": "Tüm geçmişin ortalama gün aralığı.", "group": "Service history"},
    "avg_service_interval_km": {"label": "Ortalama servis aralığı (km)", "explain": "Tüm geçmişin ortalama km aralığı.", "group": "Service history"},
    "rolling3_interval_days": {"label": "Son 3 servis ort. aralığı (gün)", "explain": "Son üç servisin ortalama gün aralığı.", "group": "Service history"},
    "rolling3_interval_km": {"label": "Son 3 servis ort. aralığı (km)", "explain": "Son üç servisin ortalama km aralığı.", "group": "Service history"},
    "avg_km_per_day_since_previous_service": {"label": "Son servisten bu yana günlük km", "explain": "Son servisten beri günlük ortalama km.", "group": "Service history"},
    "periodic_service_count": {"label": "Periyodik servis sayısı", "explain": "Geçmişteki planlı bakım adedi.", "group": "Service history"},
    "services_last_365d": {"label": "Son 1 yıldaki servis", "explain": "Son 365 gündeki servis adedi.", "group": "Service history"},
    "previous_failure_count": {"label": "Geçmiş arıza sayısı", "explain": "Daha önce görülen arıza adedi.", "group": "Service history"},
    "cumulative_service_spend": {"label": "Toplam servis harcaması", "explain": "Bugüne kadarki toplam servis tutarı.", "group": "Service history"},
    "historical_on_time_rate": {"label": "Zamanında servis oranı", "explain": "Geçmişte bakımların zamanında yapılma oranı.", "group": "Service history"},
    "historical_policy_delay_median_days": {"label": "Tipik bakım gecikmesi (gün)", "explain": "Bakım takviminden ortalama sapma.", "group": "Service history"},
    "previous_policy_delay_days": {"label": "Önceki bakım gecikmesi (gün)", "explain": "Son bakımın takvimden sapması.", "group": "Service history"},

    "policy_group": {"label": "Bakım politikası grubu", "explain": "Dataset içindeki bakım politikası sınıfı.", "group": "Maintenance"},
    "policy_interval_km": {"label": "Bakım km politikası", "explain": "Dataset bakım takviminin km aralığı.", "group": "Maintenance"},
    "policy_interval_days": {"label": "Bakım gün politikası", "explain": "Dataset bakım takviminin gün aralığı.", "group": "Maintenance"},
    "policy_ready": {"label": "Politika tanımlı mı?", "explain": "Bu araç için bakım politikası mevcut mu.", "group": "Maintenance"},
    "maintenance_overdue_days_pre_service": {"label": "Bakım gecikmesi (gün)", "explain": "Snapshot anında planlı bakıma göre gecikme (gün).", "group": "Maintenance"},
    "maintenance_overdue_km_pre_service": {"label": "Bakım gecikmesi (km)", "explain": "Snapshot anında planlı bakıma göre gecikme (km).", "group": "Maintenance"},
    "current_policy_due_task_count": {"label": "Şu an gereken bakım işi", "explain": "Politikaya göre bu servis için düşen iş sayısı.", "group": "Maintenance"},
    "total_policy_due_task_count": {"label": "Toplam gereken bakım işi", "explain": "Politikaya göre biriken toplam iş sayısı.", "group": "Maintenance"},
    "days_since_engine_task": {"label": "Motor işleminden bu yana gün", "explain": "Son motor bakımının üzerinden geçen gün.", "group": "Maintenance"},
    "km_since_engine_task": {"label": "Motor işleminden bu yana km", "explain": "Son motor bakımından sonra yapılan km.", "group": "Maintenance"},
    "km_since_brakes_task": {"label": "Fren işleminden bu yana km", "explain": "Son fren bakımından sonra yapılan km.", "group": "Maintenance"},
    "km_since_final_drive_task": {"label": "Zincir/kayış işleminden bu yana km", "explain": "Son nihai tahrik bakımından sonra yapılan km.", "group": "Maintenance"},

    "snapshot_year": {"label": "Snapshot yılı", "explain": "Tahmin anının yılı (tarihten türetilir).", "group": "Other"},
    "snapshot_month": {"label": "Snapshot ayı", "explain": "Tahmin anının ayı (tarihten türetilir).", "group": "Other"},
    "snapshot_quarter": {"label": "Snapshot çeyreği", "explain": "Tahmin anının çeyreği (tarihten türetilir).", "group": "Other"},
    "snapshot_day_of_year": {"label": "Yılın günü", "explain": "Tahmin anının yıl içindeki günü (tarihten türetilir).", "group": "Other"},
    "days_observed": {"label": "Gözlem penceresi (gün)", "explain": "Bu snapshot için mevcut gözlem süresi.", "group": "Other"},
}

DERIVED_FROM_DATE = {
    "snapshot_year", "snapshot_month", "snapshot_quarter",
    "snapshot_day_of_year", "snapshot_month_sin", "snapshot_month_cos",
}

# a compact "simple mode" field set - the signal-carrying inputs, everything
# else is imputed by the trained preprocessor.
SIMPLE_FIELDS = [
    "brand", "category", "engine_displacement_cc", "motorcycle_age_years",
    "usage_type", "riding_intensity", "snapshot_odometer_km",
    "recent_30d_km", "recent_90d_km", "previous_service_count",
    "days_since_previous_service", "km_since_previous_service",
    "historical_interval_days_median", "historical_interval_km_median",
    "previous_interval_days", "previous_interval_km",
    "policy_interval_km", "policy_interval_days",
]


def prettify(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


@dataclass
class ModelBundle:
    target: str                 # "days" | "km"
    model: Any
    mode: str                   # "encoded" | "native_cat"
    feature_cols: list[str]
    cat_cols: list[str]
    transform: str              # "raw" | "log1p"
    preprocessor: Any           # ColumnTransformer for encoded mode, else None
    model_class: str
    source_file: str
    ok: bool = True
    error: str | None = None


@dataclass
class ArtifactStore:
    generation: str = "unknown"          # "v1_final_tuning" | "v1_3_final"
    config: dict = field(default_factory=dict)
    bundles: dict[str, ModelBundle] = field(default_factory=dict)
    feature_catalog: list[dict] = field(default_factory=list)
    leakage_report: dict = field(default_factory=dict)
    load_errors: list[str] = field(default_factory=list)
    loaded_at: str = ""

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls) -> "ArtifactStore":
        import datetime as _dt

        store = cls(loaded_at=_dt.datetime.utcnow().isoformat() + "Z")
        md = settings.MODEL_DIR

        final_ok = (md / "v1_final_days_model.joblib").exists() and (md / "v1_final_km_model.joblib").exists()
        if final_ok:
            store.generation = "v1_final_tuning"
            cfg_p = md / "v1_final_tuning_config.json"
            store.config = json.loads(cfg_p.read_text()) if cfg_p.exists() else {}
            for t in ("days", "km"):
                store.bundles[t] = store._load_final_bundle(t)
        else:
            store.generation = "v1_3_final"
            store.load_errors.append("v1_final_* artifacts missing - falling back to v1_3_final_*")
            card = md / "v1_3_final_model_card.json"
            store.config = json.loads(card.read_text()) if card.exists() else {}
            for t in ("days", "km"):
                store.bundles[t] = store._load_v13_bundle(t)

        store._run_leakage_guard()
        store._build_feature_catalog()
        return store

    def _load_final_bundle(self, t: str) -> ModelBundle:
        md = settings.MODEL_DIR
        try:
            blob = joblib.load(md / f"v1_final_{t}_model.joblib")
            pre_blob = joblib.load(md / f"v1_final_{t}_preprocessor.joblib")
            mode = blob.get("mode", "encoded")
            model = blob["model"]
            feat = list(blob["feature_cols"])
            cat = list(blob.get("cat_cols", []))
            transform = blob.get("transform", "raw")
            pre = pre_blob if mode == "encoded" and not isinstance(pre_blob, dict) else None
            return ModelBundle(
                target=t, model=model, mode=mode, feature_cols=feat, cat_cols=cat,
                transform=transform, preprocessor=pre, model_class=type(model).__name__,
                source_file=f"v1_final_{t}_model.joblib",
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.load_errors.append(f"{t}: {exc}")
            return ModelBundle(t, None, "encoded", [], [], "raw", None, "?", "", ok=False, error=str(exc))

    def _load_v13_bundle(self, t: str) -> ModelBundle:
        md = settings.MODEL_DIR
        try:
            model = joblib.load(md / f"v1_3_final_{t}_model.joblib")
            pre = joblib.load(md / "v1_3_final_preprocessor.joblib")
            card = self.config
            feat = list(card.get("feature_names") or card.get("features") or [])
            if not feat and hasattr(pre, "feature_names_in_"):
                feat = list(pre.feature_names_in_)
            return ModelBundle(
                target=t, model=model, mode="encoded", feature_cols=feat, cat_cols=[],
                transform="raw", preprocessor=pre, model_class=type(model).__name__,
                source_file=f"v1_3_final_{t}_model.joblib",
            )
        except Exception as exc:  # pragma: no cover
            self.load_errors.append(f"{t}: {exc}")
            return ModelBundle(t, None, "encoded", [], [], "raw", None, "?", "", ok=False, error=str(exc))

    # ---------------------------------------------------------------- guards
    def _run_leakage_guard(self) -> None:
        hits: dict[str, list[str]] = {}
        for t, b in self.bundles.items():
            bad = [c for c in b.feature_cols if contains_leak(c)]
            if bad:
                hits[t] = bad
                b.ok = False
                b.error = f"leakage tokens in feature_cols: {bad}"
        self.leakage_report = {
            "status": "PASS" if not hits else "FAIL",
            "checked_tokens": list(LEAK_TOKENS),
            "violations": hits,
        }

    def _build_feature_catalog(self) -> None:
        union: list[str] = []
        for b in self.bundles.values():
            for c in b.feature_cols:
                if c not in union:
                    union.append(c)
        prof: dict[str, dict] = {}
        snap_p = settings.DATASET_DIR / "ml_maintenance_snapshots.parquet"
        if snap_p.exists():
            cols = [c for c in union if c not in DERIVED_FROM_DATE]
            try:
                df = pd.read_parquet(snap_p, columns=[c for c in cols])
            except Exception:
                df = pd.read_parquet(snap_p)
            cat_all = set().union(*[set(b.cat_cols) for b in self.bundles.values()])
            for c in df.columns:
                s = df[c]
                if s.dtype == object or str(s.dtype) == "category" or c in cat_all:
                    prof[c] = {"type": "categorical",
                               "options": sorted(map(str, s.dropna().unique().tolist()))[:60]}
                elif str(s.dtype) == "bool":
                    prof[c] = {"type": "boolean"}
                else:
                    q = s.astype(float)
                    prof[c] = {
                        "type": "number",
                        "min": _num(q.min()), "max": _num(q.max()),
                        "p01": _num(q.quantile(0.01)), "p99": _num(q.quantile(0.99)),
                        "median": _num(q.median()), "mean": _num(q.mean()),
                    }
        catalog = []
        for c in union:
            meta = FEATURE_META.get(c, {})
            base = prof.get(c, {"type": "number"})
            if c in DERIVED_FROM_DATE:
                base = {"type": "derived"}
            catalog.append({
                "name": c,
                "label": meta.get("label", prettify(c)),
                "explain": meta.get("explain", ""),
                "group": meta.get("group", "Other"),
                "in_days_model": c in self.bundles.get("days", ModelBundle("", None, "", [], [], "", None, "", "")).feature_cols,
                "in_km_model": c in self.bundles.get("km", ModelBundle("", None, "", [], [], "", None, "", "")).feature_cols,
                "simple": c in SIMPLE_FIELDS,
                **base,
            })
        self.feature_catalog = catalog

    # ---------------------------------------------------------------- health
    def health(self) -> dict:
        d, k = self.bundles.get("days"), self.bundles.get("km")
        ok = bool(d and d.ok and k and k.ok and self.leakage_report.get("status") == "PASS")
        return {
            "status": "ok" if ok else "degraded",
            "days_model_loaded": bool(d and d.ok),
            "km_model_loaded": bool(k and k.ok),
            "dataset_version": self.dataset_version(),
            "model_generation": self.generation,
            "leakage_guard": self.leakage_report.get("status"),
            "errors": self.load_errors + [b.error for b in self.bundles.values() if b and b.error],
        }

    def dataset_version(self) -> str:
        return str(self.config.get("dataset_version")
                   or (self.config.get("dataset") or {}).get("dataset_version")
                   or "1.3.0")

    def model_info(self) -> dict:
        d, k = self.bundles["days"], self.bundles["km"]
        frozen = (self.config.get("frozen") or {})
        ens = [t for t, fz in (("DAYS", frozen.get("DAYS")), ("KM", frozen.get("KM")))
               if fz and fz.get("use_ensemble")]
        note = None
        if ens:
            note = (f"Reported {'/'.join(ens)} TEST metrics reflect a validation-selected blend; "
                    "live inference uses the persisted frozen primary model for that target.")
        return {
            "days_model_name": _friendly(d, frozen.get("DAYS")),
            "km_model_name": _friendly(k, frozen.get("KM")),
            "days_inference_model": d.model_class,
            "km_inference_model": k.model_class,
            "inference_note": note,
            "days_model_class": d.model_class,
            "km_model_class": k.model_class,
            "dataset_version": self.dataset_version(),
            "target_definition": "NEXT ANY SERVICE - raw days / raw km delta, observed-only regression",
            "split": "temporal (TRAIN < VALIDATION < TEST by snapshot date)",
            "feature_count_days": len(d.feature_cols),
            "feature_count_km": len(k.feature_cols),
            "days_transform": d.transform,
            "km_transform": k.transform,
            "model_generation": self.generation,
            "model_config": {
                "notebook": self.config.get("notebook"),
                "fast_mode": self.config.get("fast_mode"),
                "n_optuna_trials": self.config.get("n_optuna_trials"),
                "temporal_cv_folds": self.config.get("temporal_cv_folds"),
                "selection_rule": self.config.get("selection_rule"),
                "frozen": frozen,
            },
            "model_status": "frozen" if self.generation == "v1_final_tuning" else "v1.3-final",
            "production_validation_status": "PENDING - real fleet validation not yet performed",
            "synthetic_validation": "PASS (RideBase Synthetic Dataset v1.3)",
            "loaded_at": self.loaded_at,
        }


def _friendly(b: ModelBundle, frozen: dict | None) -> str:
    if not b or not b.model_class:
        return "unavailable"
    name = b.model_class
    if frozen:
        bits = [frozen.get("model", name)]
        if frozen.get("use_ensemble"):
            bits.append("+ blend(" + ", ".join(frozen.get("ensemble_members", [])) + ")")
        if frozen.get("target_transform") and frozen["target_transform"] != "raw":
            bits.append(f"[{frozen['target_transform']}]")
        return " ".join(bits)
    return name


def _num(v) -> float | None:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except Exception:
        return None


# ---------------------------------------------------------------- table readers
def _mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


@lru_cache(maxsize=256)
def _read_csv_cached(path: str, mtime: float) -> str:
    df = pd.read_csv(path)
    return df.to_json(orient="records")


def read_table(name: str) -> list[dict] | None:
    """`name` is a file stem under reports/tables (no extension)."""
    p = settings.REPORTS_DIR / "tables" / f"{name}.csv"
    if not p.exists():
        return None
    return json.loads(_read_csv_cached(str(p), _mtime(p)))


def read_report(name: str) -> str | None:
    p = settings.REPORTS_DIR / f"{name}.md"
    return p.read_text() if p.exists() else None


@lru_cache(maxsize=8)
def _read_parquet_cached(path: str, mtime: float, sample: int) -> str:
    df = pd.read_parquet(path)
    if sample and len(df) > sample:
        df = df.sample(sample, random_state=42).sort_index()
    return df.to_json(orient="records")


def read_predictions(sample: int = 0) -> list[dict] | None:
    p = settings.OUTPUTS_DIR / "v1_final_tuning_test_predictions.parquet"
    if not p.exists():
        p = settings.OUTPUTS_DIR / "v1_3_final_regression_test_predictions.parquet"
    if not p.exists():
        return None
    return json.loads(_read_parquet_cached(str(p), _mtime(p), sample))


def latest_artifact_mtime() -> float:
    roots = [settings.MODEL_DIR, settings.REPORTS_DIR / "tables", settings.OUTPUTS_DIR]
    newest = 0.0
    for r in roots:
        if r.exists():
            for f in r.glob("v1_final_*"):
                newest = max(newest, f.stat().st_mtime)
    return newest


# ---------------------------------------------------------------- singleton
_store: ArtifactStore | None = None
_lock = threading.Lock()


def get_store(reload: bool = False) -> ArtifactStore:
    global _store
    with _lock:
        if _store is None or reload:
            _store = ArtifactStore.load()
    return _store
