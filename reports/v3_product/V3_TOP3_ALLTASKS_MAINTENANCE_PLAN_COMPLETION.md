# V3 Top-3 + All Predictions + Maintenance Plan Completion

Tarih: 2026-09-10  
Doğrulanan backend release SHA: `248c93555f409b2622a20999f07a0c3bcbd297c0`

## 1. Problem

Önceki ana V3 kartı yalnız Top-3 işlemi güçlü biçimde öne çıkarıyor, diğer 41
donmuş etiket yalnız teknik tabloda görünüyordu. Özellikle yüksek toplam
kilometreli bir motosiklette bu görünüm “yalnız bu üç işlem yapılacak” veya
“motosiklet toplam kilometresi boyunca bakım görmedi” biçiminde yanlış
okunabiliyordu. V3 gerçekte 44 işlemin tamamı için bir sonraki tamamlanmış servis
kaydında görülme olasılığı üretir; Top-3 bunun yalnız sıralı alt kümesidir.

## 2. Final UX

Sonuç ekranının sırası:

1. `MOTOSİKLET BİLGİLERİ`: toplam kilometre, son servis kilometresi ve son servisten beri kilometre/gün ayrı gösterilir.
2. `V3 — EN OLASI 3 SERVİS İŞLEMİ`: Top-3 görsel olarak birincildir ve 44 tahminin alt kümesi olduğu iki açık cümleyle anlatılır.
3. `TÜM V3 TAHMİNLERİ`: varsayılan kapalıdır; “Tüm 44 tahmini göster” açıldığında aynı 44 olasılığı azalan sırada, ad/sıra/confidence/product status ile gösterir. `HIDDEN_BY_DEFAULT` etiketler yalnız bu açık genişletmede ve düşük güvenle görünür.
4. `BAKIM PLANINA GÖRE KONTROL EDİLMESİ GEREKENLER`: ML’den ayrı karttır; yalnız deterministik politika durumunu gösterir.
5. Uyarılar/kapsam.
6. Teknik detay ve provenance.

Yalnız `EXACT` eşleşen ve seçili motosikletin planında bulunan V3 görevi
“Bakım planında da yer alıyor” rozeti alabilir. Rozet olasılık, sıra, confidence
veya eşik kararına girdi değildir.

## 3. V3 Integrity

| Gate | Result |
|---|---:|
| Retraining / recalibration | NO |
| Frozen V3 probability cells compared | 22,000 |
| Representative landmarks | 500 |
| Max / mean probability delta | `0.0 / 0.0` |
| Top-3 ranking mismatches | 0 |
| Top-5 ranking mismatches | 0 |
| Full 44-label ranking mismatches | 0 |
| Threshold mismatches | 0 |
| Feature mismatches | 0 / 138,500 |
| Frozen V3 hash inventory | 11/11 identical |

`all_tasks`, `motorcycle_context` ve `maintenance_plan`, donmuş predictor çağrısı
tamamlandıktan sonra eklenir. `all_task_probabilities`, `top_tasks`,
`binary_predictions`, applicability ve frozen threshold çıktıları değiştirilmez.

## 4. Maintenance Plan

- Kaynak: `DETERMINISTIC_POLICY`.
- Veri: aynı V2.1 read-only PIT history adapter; motosiklet/model master, landmark’a kadar kilometre, teslim edilmiş servis, tamamlanmış görev ve mevcut politika satırları.
- Politika seçimi: mevcut V2.1 `_applicable_policies` semantiği; aynı görevde model kapsamı grup kapsamına üstün, yalnız aktif `SCHEDULED` satırlar.
- Başlangıç: görevin son tamamlandığı servis; yoksa motosikletin gözlem başlangıcı ve ilk kilometresi. Gelecek servis/görev/kilometre kullanımı yoktur.
- Tetikler: `KM_ONLY`, `TIME_ONLY`, `WHICHEVER_FIRST` ayrı uygulanır.
- Durumlar: `NORMAL`, `YAKLAŞIYOR`, `GECİKMİŞ`, `ÇOK GECİKMİŞ`, `KRİTİK`.
- Aciliyet: mevcut `calculate_maintenance_urgency` doğrudan yeniden kullanılır; ikinci formül eklenmedi ve dosya hash’i değişmedi.
- Sıra: durum şiddeti, sonra effective progress azalan, sonra görev kodu. V3 olasılığı okunmaz.
- Eksik veri: ölçülemeyen politika kalemi atlanır ve uyarı döner; politika yoksa “Bu motosiklet için bakım planı eşlemesi bulunamadı.”; gecikmiş kalem yoksa “Şu anda bakım planına göre gecikmiş planlı bakım kalemi görünmüyor.”

Her madde görev kodu/adı, durum, urgency açıklaması, km/zaman/effective progress,
km/zaman due bayrakları, sonraki km/tarih, kalan/geciken km/gün ve politika
kanıt alanlarını taşır. Hiçbir maddede V3 probability alanı yoktur.

## 5. Task-Policy Mapping

| V3 Task | Policy Item | Mapping Type |
|---|---|---|
| ENGINE_OIL_CHANGE | ENGINE_OIL_CHANGE | EXACT |
| CHAIN_CLEAN | CHAIN_CLEAN | EXACT |
| CHAIN_LUBRICATE | CHAIN_LUBRICATE | EXACT |
| CHAIN_INSPECTION | CHAIN_INSPECTION | EXACT |
| BATTERY_TEST | BATTERY_TEST | EXACT |
| AIR_FILTER_INSPECTION | AIR_FILTER_INSPECTION | EXACT |
| AIR_FILTER_CHANGE | AIR_FILTER_CHANGE | EXACT |
| BRAKE_FLUID_CHECK | BRAKE_FLUID_CHECK | EXACT |
| GENERAL_SAFETY_INSPECTION | GENERAL_SAFETY_INSPECTION | EXACT |
| BRAKE_FLUID_CHANGE | BRAKE_FLUID_CHANGE | EXACT |
| CVT_BELT_INSPECTION | CVT_BELT_INSPECTION | EXACT |
| CVT_CASE_INSPECTION | CVT_CASE_INSPECTION | EXACT |
| COOLANT_LEVEL_CHECK | COOLANT_LEVEL_CHECK | EXACT |
| CVT_BELT_CHANGE | CVT_BELT_CHANGE | EXACT |
| FORK_INSPECTION | FORK_INSPECTION | EXACT |
| CVT_ROLLER_INSPECTION | CVT_ROLLER_INSPECTION | EXACT |
| FRONT_BRAKE_PAD_INSPECTION | FRONT_BRAKE_PAD_INSPECTION | EXACT |
| SPARK_PLUG_INSPECTION | SPARK_PLUG_INSPECTION | EXACT |
| VALVE_CLEARANCE_INSPECTION | VALVE_CLEARANCE_INSPECTION | EXACT |
| FRONT_TIRE_INSPECTION | FRONT_TIRE_INSPECTION | EXACT |
| FINAL_GEAR_OIL_CHANGE | FINAL_GEAR_OIL_CHANGE | EXACT |
| WHEEL_BEARING_INSPECTION | WHEEL_BEARING_INSPECTION | EXACT |
| SPARK_PLUG_CHANGE | SPARK_PLUG_CHANGE | EXACT |
| COOLANT_CHANGE | COOLANT_CHANGE | EXACT |
| REAR_TIRE_INSPECTION | REAR_TIRE_INSPECTION | EXACT |
| REAR_BRAKE_PAD_INSPECTION | REAR_BRAKE_PAD_INSPECTION | EXACT |
| STEERING_BEARING_INSPECTION | STEERING_BEARING_INSPECTION | EXACT |
| FRONT_TIRE_CHANGE | FRONT_TIRE_INSPECTION | RELATED_BUT_NOT_EQUIVALENT |
| REAR_TIRE_CHANGE | REAR_TIRE_INSPECTION | RELATED_BUT_NOT_EQUIVALENT |
| BATTERY_CHANGE | BATTERY_TEST | RELATED_BUT_NOT_EQUIVALENT |
| WHEEL_BEARING_CHANGE | WHEEL_BEARING_INSPECTION | RELATED_BUT_NOT_EQUIVALENT |
| STEERING_BEARING_CHANGE | STEERING_BEARING_INSPECTION | RELATED_BUT_NOT_EQUIVALENT |
| VALVE_CLEARANCE_ADJUST | VALVE_CLEARANCE_INSPECTION | RELATED_BUT_NOT_EQUIVALENT |
| FORK_SEAL_CHANGE | FORK_INSPECTION | RELATED_BUT_NOT_EQUIVALENT |
| BRAKE_SYSTEM_BLEED | BRAKE_FLUID_CHECK | RELATED_BUT_NOT_EQUIVALENT |
| WHEEL_BALANCE | FRONT_TIRE_INSPECTION | RELATED_BUT_NOT_EQUIVALENT |
| FUEL_SYSTEM_DIAGNOSTIC | — | NO_MAPPING |
| ENGINE_COMPRESSION_TEST | — | NO_MAPPING |
| ABS_DIAGNOSTIC | — | NO_MAPPING |
| ENGINE_FAULT_DIAGNOSTIC | — | NO_MAPPING |
| THROTTLE_BODY_CLEAN | — | NO_MAPPING |
| BRAKE_DISC_CHANGE | — | NO_MAPPING |
| ECU_DIAGNOSTIC_SCAN | — | NO_MAPPING |
| FUEL_INJECTOR_CLEAN | — | NO_MAPPING |

Özet: 27 `EXACT`, 9 `RELATED_BUT_NOT_EQUIVALENT`, 8 `NO_MAPPING`; toplam
44/44 tekil kayıt. Değişim ile kontrol gibi farklı eylemler eşdeğer sayılmaz.

## 6. High-Mileage Example

Yerel production-contract akışındaki `MC000046 @ 2026-05-31` örneği:

| Field | Value |
|---|---:|
| Güncel kilometre | 88,191 km |
| Son servisten beri | 682 km / 31 gün |
| V3 Top-3 | ENGINE_OIL_CHANGE; FRONT_TIRE_CHANGE; AIR_FILTER_CHANGE |
| Bakım planı ön sırası | FORK_INSPECTION; FRONT_BRAKE_PAD_INSPECTION; GENERAL_SAFETY_INSPECTION |

Toplam 88 bin km, son bakımdan beri 88 bin km anlamına gelmez. Kart bu iki
ölçüyü ayrı satırlarda ve bakım planını V3 sıralamasından ayrı bölümde gösterir.
Bu nedenle önceki bakım geçmişi yokmuş veya yalnız Top-3 işlem yapılacakmış gibi
okunması engellenir.

## 7. Test Matrix

Bu matris gerçek V1.4 TEST landmark’larından seçildi ve güncel yerel API sözleşmesiyle çalıştırıldı.

| Scenario | Motorcycle | Odometer | Since last service | V3 Top-3 | Maintenance-plan top items | Agreement | Result |
|---|---|---:|---:|---|---|---|---|
| low odometer / recent service | MC000039 @ 2026-03-31 | 9,346 | 437 km / 11 d | ENGINE_OIL_CHANGE; BATTERY_TEST; AIR_FILTER_INSPECTION | AIR_FILTER_INSPECTION (ÇOK GECİKMİŞ); BATTERY_TEST (ÇOK GECİKMİŞ); BRAKE_FLUID_CHECK (ÇOK GECİKMİŞ) | 3 exact | PASS |
| high odometer / recent service | MC000046 @ 2026-05-31 | 88,191 | 682 km / 31 d | ENGINE_OIL_CHANGE; FRONT_TIRE_CHANGE; AIR_FILTER_CHANGE | FORK_INSPECTION (KRİTİK); FRONT_BRAKE_PAD_INSPECTION (KRİTİK); GENERAL_SAFETY_INSPECTION (KRİTİK) | 2 exact | PASS |
| near maintenance | MC000049 @ 2026-01-31 | 88,388 | 4,755 km / 80 d | ENGINE_OIL_CHANGE; COOLANT_LEVEL_CHECK; CVT_BELT_INSPECTION | CVT_CASE_INSPECTION (KRİTİK); FRONT_BRAKE_PAD_INSPECTION (KRİTİK); FRONT_TIRE_INSPECTION (KRİTİK) | 3 exact | PASS |
| overdue | MC000006 @ 2026-04-30 | 29,055 | 5,030 km / 284 d | ENGINE_OIL_CHANGE; BATTERY_TEST; AIR_FILTER_INSPECTION | CVT_CASE_INSPECTION (KRİTİK); FORK_INSPECTION (KRİTİK); FRONT_BRAKE_PAD_INSPECTION (KRİTİK) | 3 exact | PASS |
| extreme overdue | MC000008 @ 2026-05-31 | 142,032 | 4,920 km / 72 d | ENGINE_OIL_CHANGE; FRONT_TIRE_CHANGE; GENERAL_SAFETY_INSPECTION | REAR_TIRE_INSPECTION (KRİTİK); CVT_CASE_INSPECTION (KRİTİK); SPARK_PLUG_INSPECTION (KRİTİK) | 2 exact | PASS |
| sparse history | MC000017 @ 2026-03-31 | 20,837 | 1,016 km / 216 d | ENGINE_OIL_CHANGE; BATTERY_TEST; AIR_FILTER_CHANGE | CVT_BELT_INSPECTION (YAKLAŞIYOR); CVT_CASE_INSPECTION (YAKLAŞIYOR); CVT_ROLLER_INSPECTION (YAKLAŞIYOR) | 3 exact | PASS |
| rich history | MC000022 @ 2026-04-30 | 73,916 | 4,582 km / 150 d | ENGINE_OIL_CHANGE; FRONT_TIRE_CHANGE; BRAKE_FLUID_CHANGE | FRONT_TIRE_INSPECTION (KRİTİK); STEERING_BEARING_INSPECTION (KRİTİK); REAR_BRAKE_PAD_INSPECTION (KRİTİK) | 2 exact | PASS |
| older motorcycle | MC000110 @ 2026-01-31 | 51,762 | 4,583 km / 182 d | ENGINE_OIL_CHANGE; BRAKE_FLUID_CHECK; CVT_BELT_CHANGE | AIR_FILTER_INSPECTION (KRİTİK); FORK_INSPECTION (KRİTİK); FRONT_TIRE_INSPECTION (KRİTİK) | 3 exact | PASS |
| newer motorcycle | MC000010 @ 2026-03-31 | 8,666 | 922 km / 302 d | ENGINE_OIL_CHANGE; CHAIN_CLEAN; CHAIN_LUBRICATE | CHAIN_CLEAN (KRİTİK); CHAIN_LUBRICATE (ÇOK GECİKMİŞ); AIR_FILTER_INSPECTION (ÇOK GECİKMİŞ) | 3 exact | PASS |
| high usage | MC000041 @ 2026-01-31 | 124,151 | 2,282 km / 50 d | ENGINE_OIL_CHANGE; FRONT_TIRE_CHANGE; CHAIN_CLEAN | CHAIN_CLEAN (KRİTİK); CHAIN_LUBRICATE (KRİTİK); CHAIN_INSPECTION (KRİTİK) | 2 exact | PASS |
| low usage | MC000023 @ 2026-03-31 | 21,666 | 1,284 km / 283 d | ENGINE_OIL_CHANGE; CHAIN_LUBRICATE; CHAIN_CLEAN | CHAIN_CLEAN (KRİTİK); CHAIN_LUBRICATE (KRİTİK); CLUTCH_FREE_PLAY_CHECK (KRİTİK) | 3 exact | PASS |
| partial mapping / EV | MC000337 @ 2026-05-31 | 20,611 | 1,299 km / 290 d | GENERAL_SAFETY_INSPECTION; FRONT_BRAKE_PAD_INSPECTION; FRONT_TIRE_INSPECTION | EV_CHARGING_PORT_INSPECTION (GECİKMİŞ); FRONT_BRAKE_PAD_INSPECTION (GECİKMİŞ); FRONT_TIRE_INSPECTION (GECİKMİŞ) | 3 exact; EV-only plan items remain separate | PASS |

Ek birim vakaları: model politikasının grup politikasına üstünlüğü, aynı görev
tekrarının kaldırılması, eksik kilometrede time-only politikanın korunması,
km-only kalemin dürüstçe atlanması, politika bulunmaması, future injection ve
T−1/T/T+1 monotonluğu.

## 8. Frontend

- Zorunlu Top-3 ve bakım-planı metinleri template ve build artefaktlarında test edilir.
- Tüm 44 satır, azalan olasılık, Türkçe yüzde, confidence, product status, Top-3 rozeti ve zayıf satırların görsel azaltımı Node renderer ile doğrulanır.
- Plan kartı, durum çipleri, deterministic kaynak, exact rozet, politika-yok/no-overdue durumları test edilir.
- Yüksek kilometre bağlamında toplam kilometrenin “son servisten beri” ölçüsünden önce ve ayrı etiketle gösterildiği doğrulanır.
- Tablo responsive overflow konteynerinde; mevcut mobil grid/drawer davranışı korunur.
- Etkileşimli tarayıcı CLI bu ortamda kurulu değildir. Görsel A→B→C browser otomasyonu bu nedenle çalıştırılamadı; DOM renderer, responsive markup, HTTP production içerik ve stale-generation korumaları geçti.

Yorumlanabilirlik soruları: Top-3’ün alt küme olduğu açık; 44 tahmin erişilebilir;
planın ML olmadığı açık; toplam ve servis-sonrası km ayrı; V3 ile Due/Urgency
ayrı; yüksek kilometre önceki bakım yokluğu gibi okunmuyor; V3-plan uyuşması
yalnız exact, betimleyici rozetle anlatılıyor. Bu sonuçların canlı backend ile
etkileşimli doğrulaması manuel deploy sonrasına bağlıdır.

## 9. Regression

| Suite / Gate | Result |
|---|---:|
| `ridebase-ml/tests` | 203 passed |
| backend tests | 153 passed |
| Control Center tests | 123 passed |
| Core total | 479 passed, 0 failed |
| Legacy React smoke | 5 passed |
| Legacy React TypeScript | PASS |
| Legacy React production build | PASS |
| V3 scenario product audit | PASS, 15 scenarios |
| Research↔serving parity | PASS, 500 landmarks / 22,000 probabilities |
| V3 frozen hashes | 11/11 identical |
| V2.1 + urgency frozen hashes | 21/21 identical |

Tek uyarı mevcut XGBoost eski-serileştirme uyumluluk uyarısıdır; başarısız gate
değildir. V3/V2.1 modeli eğitilmedi, eşik/kalibratör/artefakt değiştirilmedi,
Maintenance Urgency kaynak kodu hash’i `7e11476156d0a55544f326867f6089b0432debe33110b6bd472f173cdb7cfbcf`
olarak aynı kaldı.

## 10. Deployment

| Surface | State |
|---|---|
| GitHub `main` | pushed through `248c93555f409b2622a20999f07a0c3bcbd297c0` |
| Existing Vercel project | production READY; no new project created |
| Production alias | `https://ridebase-ml-control-center.vercel.app/#v3/predict` |
| Vercel immutable deployment | `https://ridebase-ml-control-center-nushhc85e-nihats-projects-181e6f5a.vercel.app` |
| Existing Render service | reachable and V3 healthy, but still serving pre-change response |
| Render action required | manual deploy of `main`; `autoDeploy: false` |
| Intended backend release SHA | `248c93555f409b2622a20999f07a0c3bcbd297c0` |

Canlı frontend HTTP kontrolü yeni heading, “Tüm 44 tahmini göster”, bakım planı
başlığı ve deterministic açıklamayı doğruladı. Canlı Render örneği
`MC000751 @ 2026-01-31` için Top-3 ve 44 probability döndürüyor ancak
`all_tasks=false`, `maintenance_plan=false`; dolayısıyla backend canlı iddiası
yapılmadı. Frontend bu geçiş halinde sahte plan üretmek yerine açıkça “Backend
dağıtımı gerekli” gösteriyor. Full live 5-bike ve A→B→C audit, Render manuel
deploy sonrasına bırakıldı.

## 11. Final Verdict

V3 UX COMPLETE —
MANUAL BACKEND DEPLOY REQUIRED

V3 PROBABILITIES AND RANKINGS REMAIN FROZEN.
THE TOP-3 IS ONLY A RANKED SUBSET OF THE FULL V3 OUTPUT.
MAINTENANCE-PLAN RECOMMENDATIONS ARE DETERMINISTIC AND ARE NOT V3 PROBABILITIES.
V2.1, MAINTENANCE DUE, MAINTENANCE URGENCY, V3, AND MAINTENANCE PLAN REMAIN SEPARATE.
NO REAL-FLEET VALIDATION IS CLAIMED.
