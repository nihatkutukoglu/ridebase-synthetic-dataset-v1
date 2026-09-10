"""Deterministic scheduled-maintenance plan enrichment for V3 product responses.

The plan is deliberately downstream of V3 inference. It reads no probability and
cannot alter a V3 rank, threshold, applicability mask, or confidence policy.
Task state follows the existing V2.1 landmark semantics: active SCHEDULED policy,
model scope over group scope, last completed task (or observation start), and the
policy's TIME_ONLY / KM_ONLY / WHICHEVER_FIRST trigger.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from .config import settings

log = logging.getLogger("ridebase.api.v3.maintenance_plan")

SOURCE = "DETERMINISTIC_POLICY"
NOTE_TR = (
    "Bu bölüm ML tahmini değildir. Mevcut kilometre, süre ve bakım politikasına "
    "göre kontrol edilmesi gereken planlı bakım kalemlerini gösterir."
)
_STATUS_ORDER = {
    "KRİTİK": 0,
    "ÇOK GECİKMİŞ": 1,
    "GECİKMİŞ": 2,
    "YAKLAŞIYOR": 3,
    "NORMAL": 4,
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def task_mapping() -> dict[str, dict[str, Any]]:
    raw = json.loads(settings.V3_MAINTENANCE_MAPPING_PATH.read_text(encoding="utf-8"))
    rows = raw.get("mappings", [])
    allowed = {"EXACT", "RELATED_BUT_NOT_EQUIVALENT", "NO_MAPPING"}
    mapping = {str(row["v3_task_code"]): dict(row) for row in rows}
    if len(rows) != 44 or len(mapping) != 44:
        raise ValueError("V3 maintenance mapping must contain 44 unique labels")
    if any(row.get("status") not in allowed for row in mapping.values()):
        raise ValueError("V3 maintenance mapping contains an invalid status")
    return mapping


def all_task_rows(payload: dict[str, Any], predictor: Any) -> list[dict[str, Any]]:
    """Add product metadata to all 44 frozen probabilities without changing them."""
    from ridebase_ml.v3.product import TIER_DISPLAY_TR, confidence_tier

    probabilities = payload.get("all_task_probabilities") or {}
    applicable = payload.get("applicable_tasks") or {}
    binary = payload.get("binary_predictions") or {}
    policy = predictor.label_policy
    top_three = {row.get("task_code") for row in (payload.get("top_tasks") or [])[:3]}
    mapping = task_mapping()
    rows = []
    for code in predictor.labels:
        pol = policy[code]
        probability = float(probabilities[code])
        confidence, reason = confidence_tier(
            probability, pol, float(payload.get("feature_coverage", 1.0))
        )
        relation = mapping[code]
        rows.append({
            "task_code": code,
            "display_name": pol.display_name_tr,
            "probability": probability,
            "predicted": bool(binary.get(code)),
            "applicable": bool(applicable.get(code, True)),
            "confidence": confidence,
            "confidence_display": TIER_DISPLAY_TR[confidence],
            "confidence_reason": reason,
            "product_status": pol.product_status,
            "mapping_status": relation["status"],
            "maintenance_task_code": relation.get("maintenance_task_code"),
            "in_top_3": code in top_three,
        })
    rows.sort(key=lambda row: (-row["probability"], row["task_code"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def _selected_policies(adapter: Any, motorcycle_id: str, landmark: date) -> list[dict[str, Any]]:
    """Use the frozen V2.1 model/group precedence helper, not a second selector."""
    import pandas as pd

    from ridebase_ml.v2_1.landmarks import _applicable_policies

    motorcycle = adapter.get_motorcycle(motorcycle_id, landmark)
    model = adapter.get_model_master(motorcycle_id, landmark)
    policies = adapter.get_maintenance_policy(motorcycle_id, landmark)
    if not motorcycle or not model or not policies:
        return []
    selected = _applicable_policies(
        str(motorcycle.get("model_id", "")),
        str(model.get("policy_group", "")),
        pd.DataFrame(policies),
    )
    return selected.to_dict("records") if not selected.empty else []


def _task_names(adapter: Any) -> dict[str, str]:
    try:
        return {
            str(row.get("task_code")): str(row.get("canonical_name_tr") or row.get("task_code"))
            for row in adapter.read_table("maintenance_tasks")
            if row.get("task_code")
        }
    except Exception:
        return {}


def _history_anchors(
    adapter: Any,
    motorcycle_id: str,
    landmark: date,
    observation_start: date,
    initial_odometer: float | None,
) -> dict[str, tuple[date, float | None, str | None]]:
    services = {
        str(row.get("service_id")): row
        for row in adapter.get_services_before(motorcycle_id, landmark)
        if str(row.get("status", "")).upper() == "DELIVERED"
        and _date(row.get("_effective_at")) is not None
        and (_date(row.get("_effective_at")) or date.max) <= landmark
    }
    candidates: dict[str, list[tuple[date, str, float | None]]] = {}
    for task in adapter.get_service_tasks_before(motorcycle_id, landmark):
        if str(task.get("status", "")).upper() != "COMPLETED":
            continue
        sid = str(task.get("service_id", ""))
        service = services.get(sid)
        if service is None:
            continue
        task_date = _date(service.get("_effective_at"))
        if task_date is None or task_date > landmark:
            continue
        code = str(task.get("task_code", ""))
        candidates.setdefault(code, []).append((task_date, sid, _number(service.get("odometer_km"))))
    anchors: dict[str, tuple[date, float | None, str | None]] = {}
    for code, rows in candidates.items():
        task_date, sid, odometer = max(rows, key=lambda row: (row[0], row[1]))
        anchors[code] = (task_date, odometer, sid)
    anchors["__BASELINE__"] = (observation_start, initial_odometer, None)
    return anchors


def _current_odometer(adapter: Any, motorcycle_id: str, landmark: date) -> float | None:
    rows = []
    for row in adapter.get_mileage_before(motorcycle_id, landmark):
        effective = _date(row.get("_effective_at"))
        value = _number(row.get("closing_odometer_km"))
        if effective is not None and effective <= landmark and value is not None and value >= 0:
            rows.append((effective, str(row.get("timeline_id", "")), value))
    return max(rows, key=lambda row: (row[0], row[1]))[2] if rows else None


def _interval(policy: dict[str, Any], recurring: str, initial: str) -> float | None:
    value = _number(policy.get(recurring))
    return value if value is not None else _number(policy.get(initial))


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _evaluate_item(
    policy: dict[str, Any],
    name: str,
    landmark: date,
    current_odometer: float | None,
    anchor: tuple[date, float | None, str | None],
) -> dict[str, Any] | None:
    from ridebase_ml.policy.urgency import calculate_maintenance_urgency

    code = str(policy["task_code"])
    anchor_date, anchor_odometer, service_id = anchor
    interval_km = _interval(policy, "recurring_km", "initial_trigger_km")
    interval_months = _interval(policy, "recurring_months", "initial_trigger_months")
    interval_days = interval_months * 30.4375 if interval_months is not None else None
    elapsed_days = float(max((landmark - anchor_date).days, 0))
    elapsed_km = (
        max(current_odometer - anchor_odometer, 0.0)
        if current_odometer is not None and anchor_odometer is not None else None
    )
    km_ratio = elapsed_km / interval_km if elapsed_km is not None and interval_km and interval_km > 0 else None
    time_ratio = elapsed_days / interval_days if interval_days and interval_days > 0 else None
    mode = str(policy.get("trigger_mode") or "WHICHEVER_FIRST")
    eligible_ratios = (
        [time_ratio] if mode == "TIME_ONLY" else
        [km_ratio] if mode == "KM_ONLY" else
        [km_ratio, time_ratio]
    )
    eligible_ratios = [ratio for ratio in eligible_ratios if ratio is not None]
    if not eligible_ratios:
        return None
    progress = max(eligible_ratios)
    overdue_km = max(elapsed_km - interval_km, 0.0) if elapsed_km is not None and interval_km else None
    remaining_km = max(interval_km - elapsed_km, 0.0) if elapsed_km is not None and interval_km else None
    overdue_days = max(elapsed_days - interval_days, 0.0) if interval_days else None
    remaining_days = max(interval_days - elapsed_days, 0.0) if interval_days else None
    urgency = calculate_maintenance_urgency(
        progress_ratio=progress,
        km_ratio=km_ratio if mode != "TIME_ONLY" else None,
        day_ratio=time_ratio if mode != "KM_ONLY" else None,
        overdue_km=overdue_km,
        overdue_days=overdue_days,
        interval_km=interval_km,
        interval_days=interval_days,
        remaining_km=remaining_km,
        remaining_days=remaining_days,
    )
    due_by_km = km_ratio >= 1.0 if km_ratio is not None else None
    due_by_time = time_ratio >= 1.0 if time_ratio is not None else None
    if mode == "TIME_ONLY":
        due_now = bool(due_by_time)
    elif mode == "KM_ONLY":
        due_now = bool(due_by_km)
    else:
        due_now = bool(due_by_km or due_by_time)
    return {
        "task_code": code,
        "display_name": name,
        "status": urgency["maintenance_urgency_level"],
        "maintenance_urgency_score": urgency["maintenance_urgency_score"],
        "maintenance_urgency_reason": urgency["maintenance_urgency_reason"],
        "determining_dimension": urgency["determining_dimension"],
        "progress_ratio": _round(progress, 4),
        "km_progress_ratio": _round(km_ratio, 4),
        "time_progress_ratio": _round(time_ratio, 4),
        "due_now": due_now,
        "due_by_km": due_by_km,
        "due_by_time": due_by_time,
        "trigger_mode": mode,
        "interval_km": _round(interval_km),
        "interval_days": _round(interval_days),
        "last_completed_date": anchor_date.isoformat(),
        "last_completed_odometer_km": _round(anchor_odometer),
        "last_completed_service_id": service_id,
        "next_due_km": _round(anchor_odometer + interval_km) if anchor_odometer is not None and interval_km else None,
        "next_due_date": (anchor_date + timedelta(days=round(interval_days))).isoformat() if interval_days else None,
        "remaining_km": _round(remaining_km),
        "remaining_days": _round(remaining_days),
        "overdue_km": _round(overdue_km),
        "overdue_days": _round(overdue_days),
        "policy_id": policy.get("policy_id"),
        "policy_scope": policy.get("scope_type"),
        "policy_version": policy.get("policy_version"),
        "evidence_level": policy.get("evidence_level"),
        "policy_confidence": policy.get("confidence"),
        "source_authority": policy.get("source_authority"),
        "manufacturer_exact": str(policy.get("is_manufacturer_exact_interval", "")).lower() in {"1", "true", "yes"},
        "source": SOURCE,
    }


def build_maintenance_plan(motorcycle_id: str, landmark_date: Any, adapter: Any) -> dict[str, Any]:
    from ridebase_ml.v2_1.source_contract import HistoryFeatureRequest

    request = HistoryFeatureRequest.parse(motorcycle_id, landmark_date)
    landmark = request.landmark_date
    motorcycle = adapter.get_motorcycle(request.motorcycle_id, landmark)
    if not motorcycle:
        return {"items": [], "source": SOURCE, "note": NOTE_TR, "empty_reason": "Motosiklet bağlamı bulunamadı."}
    observation_start = _date(motorcycle.get("observation_start_date"))
    if observation_start is None:
        return {"items": [], "source": SOURCE, "note": NOTE_TR, "empty_reason": "Bakım başlangıç tarihi bulunamadı."}
    policies = _selected_policies(adapter, request.motorcycle_id, landmark)
    if not policies:
        return {"items": [], "source": SOURCE, "note": NOTE_TR, "empty_reason": "Bu motosiklet için bakım planı eşlemesi bulunamadı."}
    current_odometer = _current_odometer(adapter, request.motorcycle_id, landmark)
    anchors = _history_anchors(
        adapter,
        request.motorcycle_id,
        landmark,
        observation_start,
        _number(motorcycle.get("initial_mileage_km")),
    )
    names = _task_names(adapter)
    items = []
    skipped = []
    for policy in policies:
        code = str(policy.get("task_code", ""))
        item = _evaluate_item(
            policy,
            names.get(code, code),
            landmark,
            current_odometer,
            anchors.get(code, anchors["__BASELINE__"]),
        )
        if item is None:
            skipped.append(code)
        else:
            items.append(item)
    items.sort(key=lambda row: (_STATUS_ORDER[row["status"]], -row["progress_ratio"], row["task_code"]))
    result: dict[str, Any] = {
        "items": items,
        "source": SOURCE,
        "note": NOTE_TR,
        "landmark_date": landmark.isoformat(),
        "current_odometer_km": current_odometer,
        "policy_item_count": len(items),
        "due_item_count": sum(bool(item["due_now"]) for item in items),
        "sort_policy": "status_severity_then_progress_desc; never V3 probability",
        "future_records_used": False,
    }
    if skipped:
        result["skipped_policy_task_codes"] = sorted(skipped)
        result["warning"] = "Ölçülebilir kilometre veya zaman girdisi olmayan politika kalemleri gösterilmedi."
    if not items:
        result["empty_reason"] = "Mevcut landmark verileriyle hesaplanabilir planlı bakım kalemi bulunamadı."
    return result


def safe_maintenance_plan(motorcycle_id: str, landmark_date: Any, adapter: Any) -> dict[str, Any]:
    """A plan-source failure must never block or mutate an otherwise valid V3 answer."""
    try:
        return build_maintenance_plan(motorcycle_id, landmark_date, adapter)
    except Exception as exc:  # pragma: no cover - defensive production boundary
        log.warning("V3 maintenance plan unavailable for %s @ %s: %s", motorcycle_id, landmark_date, exc)
        return {
            "items": [],
            "source": SOURCE,
            "note": NOTE_TR,
            "empty_reason": "Bakım planı kaynağı kullanılamadı; V3 tahmini bundan etkilenmedi.",
        }
