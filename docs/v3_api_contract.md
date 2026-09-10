# V3 API Contract

Base path `/api/v3`. **Research/product-candidate surface — not production-validated.**
Every response carries `validation_scope: SYNTHETIC_ONLY` and
`real_fleet_validation: PENDING`.

## Routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v3/model/info` | frozen model identity, counts, what V3 does *not* predict |
| GET | `/api/v3/labels` | 44-task taxonomy + presentation policy + frozen per-label metrics |
| GET | `/api/v3/metrics` | frozen synthetic TEST metrics, read from the artifact |
| GET | `/api/v3/sample` | a valid `motorcycle_id` + `landmark_date` pair (input only) |
| POST | `/api/v3/predict` | predict from a complete frozen feature row (ML-facing) |
| POST | `/api/v3/predict/batch` | up to 100 feature rows |
| POST | `/api/v3/predict/by-motorcycle` | **primary product flow**: ID + landmark → PIT history → V3 |
| ~~POST~~ | ~~`/api/v3/predict/scenario`~~ | **not implemented** — see below |

### Why there is no scenario route

80.5% of the frozen 277-feature contract depends on per-task service history that
natural user input cannot supply. Fabricating it changes the top-3 answer in
**97.3%** of real landmarks, with individual probabilities moving up to 0.81. Full
measurement in [`reports/v3_product/09_scenario_feasibility.md`](../reports/v3_product/09_scenario_feasibility.md).
`POST /api/v3/predict/scenario` returns 404 and a test asserts it stays that way.

## POST /api/v3/predict/by-motorcycle

```json
{ "motorcycle_id": "MC000515", "landmark_date": "2026-03-31", "top_k": 3,
  "include_hidden": false }
```

`top_k` is bounded to 1–10 by the schema (default 3, product default 3, optional 5).
`include_hidden` opts the random-event labels into the ranked list; they are
excluded by default.

### Response

```json
{
  "model_version": "v3.0-research",
  "status": "V3_SYNTHETIC_PRODUCT_CANDIDATE",
  "validation_scope": "SYNTHETIC_ONLY",
  "real_fleet_validation": "PENDING",
  "landmark_date": "2026-03-31",
  "motorcycle_id": "MC000515",
  "input_source": "SYNTHETIC_HISTORY_V1_4",
  "heading": "V3 — EN OLASI 3 SERVİS İŞLEMİ",
  "top_tasks": [
    { "task_code": "ENGINE_OIL_CHANGE", "display_name": "Motor Yağı Değişimi",
      "display_name_en": "Engine Oil Change", "component_group": "ENGINE",
      "probability": 0.8231, "percent": 82.3, "rank": 1,
      "confidence": "YUKSEK", "confidence_display": "YÜKSEK",
      "confidence_reason": "PRIMARY label (frozen TEST PR-AUC 0.854 on 4626 positives) at probability 82%",
      "product_status": "PRIMARY" }
  ],
  "all_task_probabilities": { "…": "all 44 labels, always" },
  "all_tasks": [
    { "rank": 1, "task_code": "ENGINE_OIL_CHANGE",
      "display_name": "Motor Yağı Değişimi", "probability": 0.8231,
      "confidence": "YUKSEK", "product_status": "PRIMARY",
      "mapping_status": "EXACT", "in_top_3": true }
  ],
  "binary_predictions":     { "…": "all 44 labels at the frozen global threshold 0.31" },
  "applicable_tasks":       { "…": "hardware applicability per label" },
  "feature_coverage": 1.0,
  "missing_features": [],
  "history_provenance": { "source": "v2_1_history_adapter", "prior_services_used": 9,
                          "prior_task_lines_used": 38,
                          "task_history_boundary": "parent service received_at <= landmark",
                          "declined_tasks_excluded": true },
  "maintenance_plan": {
    "source": "DETERMINISTIC_POLICY",
    "note": "Bu bölüm ML tahmini değildir. Mevcut kilometre, süre ve bakım politikasına göre kontrol edilmesi gereken planlı bakım kalemlerini gösterir.",
    "items": [
      { "task_code": "ENGINE_OIL_CHANGE", "status": "YAKLAŞIYOR",
        "progress_ratio": 0.91, "due_now": false,
        "next_due_km": 42000, "remaining_km": 700 }
    ]
  },
  "timing_ms": { "history_build": 33.4, "prediction": 24.7, "total": 58.1 },
  "warnings": ["…"],
  "provenance": { "…": "frozen policy, what V3 does not predict, deployed:false" }
}
```

**Raw model output and product presentation are returned side by side and never
mixed.** `all_task_probabilities` is exactly what the frozen model produced after
the deterministic applicability mask. `top_tasks` is what the presentation policy
chose to lead with. `all_tasks` is a presentation-only view of those same 44
numbers with name, rank, confidence and product status. The policy never edits a
probability.

`maintenance_plan` is a separate deterministic output. It uses the same PIT-safe
history adapter and existing scheduled-policy/urgency semantics, never a V3
probability. Items are ordered by severity (`KRİTİK` → `NORMAL`) and then policy
progress descending. Missing policy or measurement inputs produce an explicit
empty state rather than a fabricated task or due date.

### Status codes

| Code | Meaning |
|---|---|
| 200 | prediction produced |
| 404 | unknown `motorcycle_id` |
| 422 | landmark before the motorcycle's observation window, malformed date, `top_k` out of range, or an incomplete feature row on `/predict` |
| 413 | request body over `MAX_REQUEST_BYTES` |
| 503 | V3 artifacts unavailable, or `V3_ENABLED=false` |

**No failure path ever returns a fabricated prediction.** A missing history, an
unknown bike or an out-of-window landmark is an error, not a guess.

## Operational notes

| item | value |
|---|---|
| model load | once at startup (`init_v3`), never per request |
| cold start (full stack) | ~1.8 s, of which V3 ~1.4 s |
| warm `by-motorcycle` p50 | ~57 ms (history ~33 ms, inference ~25 ms) |
| batch cap | 100 rows (`MAX_BATCH`), enforced by schema and handler |
| V3 process memory | ~113 MB (94 MB models + 19 MB reference tables) |
| full stack peak RSS | ~452 MB against Render free's 512 MB |
| kill switch | `V3_ENABLED=false` → `/api/v3/*` 503, V1/V2.0/V2.1 unaffected |

Artifact paths are module constants; no request field selects a file. There is no
upload endpoint and no stack trace reaches a client.
