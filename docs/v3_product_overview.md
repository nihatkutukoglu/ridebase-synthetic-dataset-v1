# V3 Product Overview

**V3 — SONRAKİ SERVİSTE BEKLENEN İŞLEMLER**

> V3, bir sonraki tamamlanmış servis kaydında hangi işlemlerin görülme olasılığının
> daha yüksek olduğunu tahmin eder.

Status: **V3 SYNTHETIC PRODUCT CANDIDATE — SYNTHETICALLY VALIDATED, REAL FLEET
VALIDATION PENDING.**

## What V3 predicts

For one motorcycle at one landmark date: a calibrated probability, per maintenance
task, that the task appears on the work order of the **next completed service**.

## What V3 does NOT predict

| Not this | That is |
|---|---|
| when the next service happens | V2.1 (P30/P60/P90/P120) |
| whether maintenance is required | Maintenance Due — deterministic |
| how overdue maintenance is | Maintenance Urgency — deterministic 0–100 |
| probability of mechanical failure | nothing in RideBase predicts this |

`BRAKE_DISC_CHANGE = 0.21` means "a disc change is likely to appear on the next
work order", **not** "there is a 21% chance the disc fails". See
[`v2_1_v3_product_semantics.md`](v2_1_v3_product_semantics.md).

## The frozen model

| item | value |
|---|---|
| champion | CatBoost, binary relevance (one classifier per label) |
| labels | 44 (25 CORE + 19 LOW_FREQUENCY from the research label gate) |
| features | 277, all point-in-time safe at the landmark |
| threshold | single global 0.31, tuned on VALIDATION |
| calibration | per-label: 28 none, 14 isotonic, 2 sigmoid |
| world | RideBase Synthetic Dataset v1.4, V2.1 landmark grid |
| artifacts | `ridebase-ml/models/v3_research/` |

Nothing was retrained during productization. The research champion is used exactly
as frozen, and its hashes are recorded in
[`reports/v3_product/01_v3_frozen_hashes.json`](../reports/v3_product/01_v3_frozen_hashes.json).

## Frozen synthetic TEST performance

| metric | TEST | unseen-motorcycle TEST |
|---|---|---|
| P@1 (ranking) | 0.801 | 0.804 |
| P@3 (ranking) | 0.399 | 0.386 |
| R@3 | 0.680 | 0.697 |
| Micro F1 | 0.519 | 0.493 |
| Micro PR-AUC | 0.561 | 0.544 |
| mAP | 0.133 | 0.128 |

**P@1 is a ranking metric, not an accuracy figure.** It is the share of landmarks
where the highest-ranked task really was performed at the next completed service.
Calling it "80% accurate" is forbidden throughout the codebase and asserted against
by tests.

## Presentation policy

Not all 44 labels are shown with equal weight. Status is derived from the frozen
per-label TEST metrics and the Phase-9 generating-process audit
([`config/v3_product_label_policy.json`](../config/v3_product_label_policy.json)):

| status | count | treatment |
|---|---|---|
| PRIMARY | 12 | can lead the card, can reach YÜKSEK confidence |
| SECONDARY | 13 | shown, capped below YÜKSEK unless PRIMARY |
| LOW_CONFIDENCE | 4 | shown but de-emphasised, thin TEST support |
| HIDDEN_BY_DEFAULT | 15 | never leads; random-event tasks with no learnable signal |

This is **presentation only** — all 44 labels stay in the model and in every API
response under `all_task_probabilities`.

### Confidence tiers

`YÜKSEK` / `ORTA` / `DÜŞÜK` / `SINIRLI VERİ`, computed deterministically from
probability, label reliability and feature coverage. Two rules matter most:

1. A high probability on a `HIDDEN_BY_DEFAULT` label is **always DÜŞÜK**. Phase 9
   showed these are random events; a confident-looking score there is the model
   being confidently wrong.
2. Feature coverage below 80% caps everything at `SINIRLI VERİ`.

## How it is used

Primary flow: `POST /api/v3/predict/by-motorcycle` with a `motorcycle_id` and a
`landmark_date`. There is deliberately **no scenario route** — see
[`v3_api_contract.md`](v3_api_contract.md).

## Honest limitations

- Synthetic only. No real-fleet validation has been performed or is claimed.
- 15 of 44 labels are not learnable from any landmark observable.
- Macro F1 is low (0.111 on TEST) because a single global threshold under-serves
  low-frequency labels. Those are meant to be read as probabilities and ranks.
- mAP degrades 18% from VALIDATION to TEST under distribution shift.
- 12 labels have fewer than 30 TEST positives.
- The world's core generator is not in the repository, so the Phase-9 process
  audit is empirical rather than a code audit.
