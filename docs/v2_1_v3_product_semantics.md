# V2.1 vs V3 — Product Semantics

Two models, two questions, two denominators. They are never combined.

## The four separate layers

| Layer | Question | Type | Output |
|---|---|---|---|
| **Maintenance Due** | Bakım gerekiyor mu? | deterministic policy | yes / no |
| **Maintenance Urgency** | Ne kadar acil / gecikmiş? | deterministic policy | 0–100 score |
| **V2.1** | Müşteri ne zaman servise dönecek? | ML survival | P30 / P60 / P90 / P120 |
| **V3** | Döndüğünde ne yapılacak? | ML multi-label | per-task probability |

## Allowed readings

- **V2.1** — "90 gün içinde servise dönüş olasılığı %62."
  The denominator is *this motorcycle, over the next 90 days*.
- **V3** — "Bir sonraki tamamlanmış serviste motor yağı değişimi görülme olasılığı %82."
  The denominator is *the next completed service, whenever it happens*.

V3 carries **no time horizon at all**. If the bike comes in next week the number
applies to that visit; if it comes in next year it applies to that visit. V3 says
nothing about which.

## Forbidden readings

| Forbidden | Why |
|---|---|
| `V2.1 × V3` as a "task within 90 days" probability | The two are not independent and V3 is not conditioned on a horizon. The product would be a number with no defined meaning. |
| "V3 shows a 82% chance of an oil change in the next 90 days" | Smuggles V2.1's horizon into a V3 number. V3's condition is *at the next service*, not *within a window*. |
| "V3 is a risk score" | V3 predicts what a workshop will write on a work order, not the likelihood of anything going wrong. |
| "V3 says maintenance is due" | Maintenance necessity is deterministic and comes from the policy engine, not from V3. |
| Reconciling V3 against Maintenance Urgency | Different denominators. A bike can be highly overdue (urgency 100) and still have a low V3 probability for a specific task, because that task simply is not usually performed at this kind of visit. |

## Why they are kept apart in code

- No V3 route reads a V2.1 artifact, and no V2.1 route reads a V3 artifact.
- The V3 API response contains no urgency score and no V2.1 horizon probability.
  `test_response_never_carries_urgency_or_v2_1_scores` asserts this on every payload.
- `ridebase_ml.v3.product` never imports V2.1 or the policy engine. The only
  deterministic input V3 uses is the OEM interval table, and it enters as a
  *feature* at training time — never as a post-hoc adjustment to a probability.
- V3 does not consume V2.1's output even though the Phase-20 oracle study showed
  next-visit timing is exactly the missing observable. That coupling would
  propagate V2.1's calibration error into V3's displayed percentages and make a V3
  number move whenever V2.1 was retrained. It is deliberately not implemented.

## Showing them together

Both may appear on the same screen, in **separate cards**, each with its own
question written above the numbers. What must never happen is a combined figure, a
shared progress bar, or copy that implies one explains the other.

A defensible joint sentence:

> "Bu müşterinin 90 gün içinde servise dönme olasılığı %62 (V2.1). Döndüğünde en
> olası işlemler: motor yağı %82, zincir bakımı %64 (V3)."

Two sentences, two models, no arithmetic between them.
