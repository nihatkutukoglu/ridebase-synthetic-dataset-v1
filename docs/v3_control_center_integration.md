# V3 Control Center Integration

The V3 module is a **distinct section** in the existing Control Center. No other
module was redesigned, and V1 / V2.0 / V2.1 / Maintenance Urgency wording is
unchanged (asserted by tests).

## Where it lives

- Sidebar: **V3 Next Task** (previously a `soon:true` placeholder, now a live module)
- Routes: `#v3/predict` (default) and `#v3/overview`
- Source: `ridebase-control-center/template.html`, section
  `/* ---------------- V3 — NEXT SERVICE TASKS ---------------- */`
- Rebuild: `python3 build.py` regenerates `RideBase_Control_Center.html`

## Canlı Tahmin (`#v3/predict`)

Flow: motorcycle ID + landmark date (+ optional "rastgele geçerli ID getir",
which calls `GET /api/v3/sample`) → `POST /api/v3/predict/by-motorcycle`.

Result hierarchy, in order:

1. **Top 3 tasks** (5 selectable) — Turkish display name, probability bar, percentage
2. **Confidence tier** chip — YÜKSEK / ORTA / DÜŞÜK / SINIRLI VERİ
3. **Feature coverage**, input source, `SYNTHETIC_ONLY`, `GERÇEK FİLO: PENDING`
4. **Warnings** block — always includes the three mandatory disclaimers
5. **Collapsed technical details** — all 44 label probabilities, the binary decision
   at the frozen threshold, and timing

Error handling: unknown bike → clean message from the 404; pre-observation landmark
→ clean message from the 422. **No fabricated prediction is ever rendered.**

## Genel Bakış (`#v3/overview`)

Frozen synthetic TEST metrics as a secondary technical section: P@1, P@3, R@3,
Micro F1, mAP, plus unseen-motorcycle P@1, and the label-policy counts.

**P@1 is labelled "P@1 (sıralama)"** with the note "en olası işlem gerçekten yapıldı
mı — **doğruluk oranı değildir**". A test walks every occurrence of `P@1` in both
the template and the built HTML and requires any nearby accuracy word to be
negated.

## Required copy (enforced by tests)

- `V3 — SONRAKİ SERVİSTE BEKLENEN İŞLEMLER`
- `Bu tahminler sentetik veri üzerinde doğrulanmıştır. Gerçek filo doğrulaması henüz yapılmamıştır.`
- `Bu yüzdeler mekanik arıza olasılığı değildir.`
- `Bakım gereksinimi ve bakım aciliyeti deterministik bakım politikasından ayrı hesaplanır.`

## Forbidden copy (enforced by tests)

`kesin yapılacak`, `arıza riski`, `gerçek veride doğruluk`, `accurate` / `accuracy`
used as a claim. `ridebase_ml.v3.product.assert_copy_is_safe` guards every string
the backend emits; `V3Module.test_forbidden_claims_are_absent_from_the_v3_module`
guards the frontend.

The V3 module must also never mention a **time horizon** — no `30 gün`, `90 gün`,
`P30`, `P90`. V3 has no horizon; a test asserts those strings are absent from the
V3 section.

## Tests

- `ridebase-control-center/tests/v3_module_runner.cjs` renders the result card from
  a fixed payload in Node and reports what a viewer would see.
- `tests/test_control_center.py::V3Module` — 16 gates: wiring, rendering,
  percentages, confidence tiers, no NaN/undefined, disclaimers, copy bans, and
  that V2.1 and Maintenance Urgency wording is untouched.
