# V3 Top-3, Tüm Tahminler ve Bakım Planı — Preflight

Tarih: 2026-09-10  
Başlangıç SHA: `0b33aed3b6629bc86edfa416d0bb1fb0cd3fac69`

## Mevcut durum

- V3 donmuş sözleşmesi 277 özellik ve 44 etiketten oluşuyor. Ürün yanıtı `top_tasks`, `all_task_probabilities`, `binary_predictions`, eşik politikası ve bağlamı ayrı alanlarda döndürüyor.
- Control Center motosiklet bilgisini V3 sonuçlarından önce gösteriyor; ana kart seçilebilir Top-3/Top-5 listeyi, teknik detay ise yalnız görev kodu/olasılık/eşik kararını gösteriyor.
- Ana kullanıcı yüzeyinde “Top-3 yalnız bir alt kümedir” açıklaması, tüm 44 tahminin açıkça genişletilebildiği ürün listesi ve görev bazlı deterministik bakım planı bulunmuyor.
- V2.1 read-only adapter motosiklet, kilometre, teslim edilmiş servis, tamamlanmış servis görevi, model master ve bakım politikalarını landmark tarihinde PIT-safe olarak sağlıyor.
- Kanonik görev-vade semantiği, aktif `SCHEDULED` politikaları model kapsamına grup kapsamından üstün tutuyor; görev için son tamamlanmış işlem yoksa gözlem başlangıcı/ilk kilometreyi başlangıç kabul ediyor; `TIME_ONLY`, `KM_ONLY` ve `WHICHEVER_FIRST` tetiklerini ayırıyor.
- Bakım aciliyeti `ridebase_ml.policy.urgency.calculate_maintenance_urgency` içinde tek deterministik 0–100 eğri ve `NORMAL / YAKLAŞIYOR / GECİKMİŞ / ÇOK GECİKMİŞ / KRİTİK` bantlarıyla uygulanıyor.

## Görev ve politika envanteri

- V3 etiketi: 44
- Bakım görev master kaydı: 86
- Bakım politika kaydı: 621
- Aktif planlı görev kodu: 36
- V3 ile aktif planlı politika arasında birebir görev kodu eşleşmesi: 27
- İlişkili fakat eşdeğer olmayan eşleme: 9
- Savunulabilir plan eşlemesi olmayan V3 etiketi: 8

Eşleme sınırı `config/v3_maintenance_task_mapping.json` ve `docs/v3_maintenance_task_mapping.md` ile açıkça kayda alınacaktır. Yalnız `EXACT` eşleşme ve seçili motosiklet planında mevcut görev rozet alacaktır.

## Uygulama sınırları

1. Donmuş V3 predictor çağrısı ve 44 olasılık üretildikten sonra yalnız response enrichment yapılacak.
2. Tüm tahmin listesi 44 ham kalibre olasılığı azalan sırada gösterecek; eşik, confidence ve product status mevcut politika kaynaklarından okunacak.
3. Gizli etiketler yalnız kullanıcının açıkça genişlettiği “TÜM V3 TAHMİNLERİ” bölümünde gösterilecek ve düşük güvenle işaretlenecek.
4. Bakım planı V3 olasılığını kullanmayacak; aynı adapter, landmark sınırı, aktif planlı politika seçimi ve kanonik urgency fonksiyonunu kullanacak.
5. Politika/ölçüm yokluğunda görev veya tarih uydurulmayacak; yapılandırılmış boş durum döndürülecek.
6. V2.1, Maintenance Due, Maintenance Urgency, V3 ve Maintenance Plan ayrı alanlar ve ayrı metinlerle korunacak.

## Riskler ve kapılar

- Backend enrichment kaynak hatası V3 tahminini bloke etmemeli veya olasılıklarını değiştirmemeli.
- Plan sırası yalnız durum önceliği ve görev progress oranına göre olmalı; V3 olasılığına göre olmamalı.
- Aynı girdide plan ve tüm tahmin satırları deterministik olmalı, görev tekrarı olmamalı.
- Gelecek servis, görev veya kilometre kaydı landmark öncesi hesaplamaya sızmamalı.
- Docker üretim imajı eşleme dosyasını açık bir path ile taşımalı.
- Tam regresyon ve donmuş artifact hash kontrolleri değişiklikten sonra yeniden çalıştırılmalı.

Preflight sonucu: **UYGULAMAYA UYGUN**. Model yeniden eğitimi veya artifact değişikliği gerekmiyor.
