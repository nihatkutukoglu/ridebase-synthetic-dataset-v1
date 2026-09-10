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

1. **Motosiklet bilgileri** — kimlik ve landmark anındaki PIT-safe bağlam
2. **En olası 3 servis işlemi** — ad, olasılık, confidence; bunun yalnız alt küme olduğu açıkça yazılır
3. **Tüm V3 tahminleri** — kullanıcı açınca 44 etiketin tamamı azalan olasılıkla; gizli/zayıf etiketler düşük güvenle
4. **Bakım planı** — V3'ten ayrı `DETERMINISTIC_POLICY` listesi, durum şiddeti ve politika ilerlemesine göre sıralı
5. **Warnings** block — her zaman zorunlu kapsam uyarıları
6. **Collapsed technical details** — provenance, frozen threshold ve timing

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

- `V3 — EN OLASI 3 SERVİS İŞLEMİ`
- `V3, 44 işlem arasından bir sonraki tamamlanmış servis kaydında görülme olasılığı en yüksek olan 3 işlemi öne çıkarır.`
- `Bu liste yalnızca en yüksek 3 tahmini gösterir; diğer V3 tahminleri aşağıda görülebilir.`
- `Bu bölüm ML tahmini değildir. Mevcut kilometre, süre ve bakım politikasına göre kontrol edilmesi gereken planlı bakım kalemlerini gösterir.`
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
