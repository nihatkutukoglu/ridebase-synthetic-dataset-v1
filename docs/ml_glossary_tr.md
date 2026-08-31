# RideBase ML — Basit Terim Sözlüğü (TR)

Bu sözlük, Control Center ve API'de geçen teknik terimlerin veri bilimi bilmeyen biri
için kısa Türkçe karşılığıdır. Kural: **önce anlaşılır Türkçe, sonra teknik terim.**

> **En önemli not:** R², C-index, AUC gibi metrikler **"doğruluk yüzdesi" değildir.**
> "AUC 0.95 = %95 doğruluk" **denmez.** Her metrik kendi anlamıyla okunur.

| Terim | Basit açıklama | Yön |
|---|---|---|
| **Feature** (özellik) | Modelin tahmin yaparken kullandığı bilgi. Örn. son servisten bu yana geçen gün, yıllık tipik km, motor hacmi. | — |
| **Target** (hedef) | Modelin tahmin etmeye çalıştığı şey. V1: kaç gün / kaç km sonra servis. V2: 30/60/90/120 gün içinde servise gelme ihtimali. | — |
| **Train** | Modelin öğrendiği veri. | — |
| **Validation** | Modelin ve ayarlarının seçildiği veri. | — |
| **Test** | En son sınav. Model seçmek için kullanılmaz; config donduktan sonra bir kez açılır. | — |
| **MAE** | Ortalama ne kadar yanıldık (gün veya km). "MAE 21 gün" = tahminler ortalama ~21 gün sapıyor. | Düşük daha iyi |
| **RMSE** | MAE gibi ama büyük hataları daha ağır cezalandırır. | Düşük daha iyi |
| **Median AE** | Tipik hata; aykırı değerlerden etkilenmez. | Düşük daha iyi |
| **R²** | Modelin hedefteki değişimi ne kadar açıkladığı. **Yüzde doğruluk değildir.** Negatif = sabit bir tahminden bile kötü. | Yüksek daha iyi |
| **Censoring / Right-censored** (sağ-sansür) | Veri seti kapandığında sonraki servisi henüz görülmemiş kayıt. Motorun o gün geldiği anlamına gelmez; **en az** o süredir gelmediğini biliyoruz. | — |
| **Survival Analysis** | "Tam kaç gün sonra" yerine "şu süre içinde olma ihtimali" modelleyen yöntem. Sağ-sansürlü kayıtları da kullanır. | — |
| **Horizon** (zaman aralığı) | Ne kadar ileriye baktığımız. 90 günlük horizon = önümüzdeki 90 gün. | — |
| **C-index** | Modelin hangi motorun daha erken servise geleceğini doğru **sıralama** gücü. 0.50 rastgele, 1.00 kusursuz. **Doğruluk yüzdesi değildir.** IPCW C-index = sansürü hesaba katan sürümü. | Yüksek daha iyi |
| **Brier Score** | Verilen olasılıkların hata seviyesi. "%70 gelir" dediklerimizin gerçekte ~%70 gelmesini isteriz. | Düşük daha iyi (0 mükemmel) |
| **Integrated Brier (IBS)** | Tüm horizon'lar (30/60/90/120) boyunca ortalama olasılık hatası, tek sayı. | Düşük daha iyi |
| **AUC** | "Gelecek" ve "gelmeyecek" bir motor çiftinde modelin gelecek olana daha yüksek risk verme olasılığı. 0.50 yazı-tura, 1.00 kusursuz ayrım. **Doğruluk yüzdesi değildir.** | Yüksek daha iyi |
| **Calibration** (kalibrasyon) | Modelin verdiği yüzdelere ne kadar güvenebileceğimiz. İyi kalibre model "%70" dediğinde benzer 100 motordan ~70'i gerçekten gelir. | Hata düşük daha iyi (GOOD < 0.03 < MODERATE < 0.07 < POOR) |
| **Risk Group** (risk grubu) | Motorları 90 günlük servis ihtimaline göre LOW / MEDIUM / HIGH gruplarına ayırma. HIGH = yakın zamanda gelme ihtimali yüksek. | — |
| **Ensemble** | Birden fazla modelin tahminini birleştirip tek sonuç üretmek. V2 final: %60 XGBoost-Cox + %40 CoxNet. | — |
| **Cox / CoxNet / XGBoost-Cox** | Survival modeli türleri. Cox = klasik; CoxNet = düzenlileştirilmiş Cox; XGBoost-Cox = karar ağaçlı Cox. | — |
| **Median service days** | Modelin servis olasılığının %50'ye ulaştığı yaklaşık gün sayısı. | — |
| **Temporal drift** | Geçmişteki servis davranışı ile gelecekteki davranışın farklılaşması. | — |
| **API** | Dashboard ile model arasında iletişim kuran servis. | — |
| **Artifact** | Kaydedilmiş model veya rapor dosyası. | — |
| **Preprocessor** | Ham veriyi modelin anlayacağı biçime çeviren kayıtlı dönüşüm (production'da sadece uygulanır, yeniden eğitilmez). | — |
| **Calibrator** | Modelin verdiği yüzdeleri gerçeğe daha yakın hale getiren düzeltme katmanı. | — |
| **Golden parity** | Notebook'taki tahmin ile production API'nin tahmininin birebir aynı olması. | PASS beklenir |
| **SYNTHETICALLY VALIDATED** | Model gerçek RideBase servis verisi yerine kontrollü sentetik v1.3 veri üzerinde geliştirildi. | — |
| **REAL FLEET VALIDATION: PENDING** | Gerçek RideBase servis geçmişi geldiğinde model ayrıca test edilecek ve gerekirse yeniden eğitilecek. | — |

## Model / uygulama / gerçek-filo ayrımı

- **APPLICATION: PILOT YAYINDA** — uygulama dağıtılabilir durumda.
- **MODEL: SENTETİK VERİDE DOĞRULANDI** — skorlar RideBase Synthetic Dataset v1.3 üzerinde.
- **REAL FLEET VALIDATION: BEKLENİYOR** — gerçek filo performansı henüz ölçülmedi.

Bu üçü aynı şey değildir ve karıştırılmaz.
