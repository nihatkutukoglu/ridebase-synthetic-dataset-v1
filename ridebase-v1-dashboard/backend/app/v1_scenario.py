"""Natural-input V1 scenario inference built on the shared deterministic context."""
from __future__ import annotations

from typing import Any, Dict, List

from .artifacts import DERIVED_FROM_DATE, ArtifactStore
from .predictor import predict
from .schemas import V1ScenarioRequest
from .v2_scenario import catalog_response as shared_catalog_response
from .v2_scenario import coverage_for_features, derive_scenario


def _input_options(store: ArtifactStore) -> Dict[str, List[Any]]:
    by_name = {item["name"]: item for item in store.feature_catalog}
    return {
        key: list(by_name.get(key, {}).get("options", []))
        for key in ("usage_type", "riding_intensity")
    }


def catalog_response(store: ArtifactStore) -> Dict[str, Any]:
    result = shared_catalog_response()
    result["input_options"] = _input_options(store)
    result["consumer"] = "V1_SCENARIO"
    return result


def predict_scenario(req: V1ScenarioRequest, store: ArtifactStore) -> Dict[str, Any]:
    days_order = list(store.bundles["days"].feature_cols)
    km_order = list(store.bundles["km"].feature_cols)
    union_order = list(dict.fromkeys(days_order + km_order))
    built = derive_scenario(
        req,
        feature_order=union_order,
        options=_input_options(store),
    )

    known = {item["name"] for item in store.feature_catalog}
    features = {
        key: value for key, value in built["features"].items()
        if key in known and key not in DERIVED_FROM_DATE
    }
    origins = dict(built["origins"])
    if req.current_odometer_km is not None and "snapshot_odometer_km" in known:
        features["snapshot_odometer_km"] = req.current_odometer_km
        origins["snapshot_odometer_km"] = {
            "source": "USER_INPUT",
            "detail": "Current odometer entered by the user.",
        }
    for feature in DERIVED_FROM_DATE:
        if feature in union_order:
            origins.setdefault(feature, {
                "source": "DERIVED",
                "detail": "Derived canonically from snapshot_date by the V1 inference service.",
            })

    union_coverage, provenance = coverage_for_features(union_order, origins)
    days_coverage, _ = coverage_for_features(days_order, origins)
    km_coverage, _ = coverage_for_features(km_order, origins)
    for row in provenance:
        feature = row["feature"]
        row["in_days_model"] = feature in days_order
        row["in_km_model"] = feature in km_order

    inference = predict(store, features, req.snapshot_date, strict=False)
    maintenance = built["maintenance"]
    show_prediction = maintenance["status"] not in {"UNKNOWN", "OVERDUE"}
    if maintenance["status"] == "OVERDUE":
        suppressed_reason = (
            "Bakım periyodu aşıldığı için ileri tarih/mesafe tahmini gösterilmez; "
            "deterministik servis kararı önceliklidir."
        )
    elif maintenance["status"] == "UNKNOWN":
        suppressed_reason = (
            "Güncel kilometre, son servis tarihi ve son servis kilometresi tamamlanmadan "
            "kişisel V1 tarih/mesafe tahmini gösterilmez."
        )
    else:
        suppressed_reason = None

    warnings = list(built["warnings"])
    ood = inference["input_diagnostics"].get("out_of_distribution", [])
    if ood:
        warnings.append(
            f"{len(ood)} V1 girdisi sentetik eğitim verisinin tipik p01–p99 aralığı dışında."
        )

    return {
        "mode": "V1_SCENARIO_PARTIAL",
        "selected_motorcycle": built["model"],
        "prediction": inference["prediction"] if show_prediction else None,
        "derived": inference["derived"] if show_prediction else None,
        "typical_model_error": inference["typical_model_error"],
        "input_diagnostics": inference["input_diagnostics"],
        "maintenance": maintenance,
        "decision": {
            "primary_source": "DETERMINISTIC_MAINTENANCE_POLICY",
            "primary_action": maintenance["action"],
            "primary_action_label": maintenance["action_label"],
            "prediction_scope": (
                "PARTIAL_INPUT_SCENARIO" if show_prediction else "SUPPRESSED"
            ),
            "show_v1_point_estimate": show_prediction,
            "v1_suppressed_reason": suppressed_reason,
        },
        "coverage": {
            "union": union_coverage,
            "days": days_coverage,
            "km": km_coverage,
        },
        "provenance": provenance,
        "warnings": warnings,
        "model": inference["model"],
        "warning": inference["warning"],
        "interpretation": (
            "This is a partial-input V1 scenario, not a real-fleet personal prediction. "
            "Deterministic maintenance policy remains the source of truth for whether service is due."
        ),
    }
