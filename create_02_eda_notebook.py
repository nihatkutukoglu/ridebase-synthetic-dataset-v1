from pathlib import Path
import re

import nbformat as nbf
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "ridebase_v1_1"
NOTEBOOK_PATH = ROOT / "ridebase-ml" / "notebooks" / "02_eda.ipynb"


TABLES = [
    ("workshops", "df_workshops", "source_tables", "workshops.csv", "Servis noktalarının konum, kapasite, uzmanlık, fiyat ve operasyon özellikleri."),
    ("customers", "df_customers", "source_tables", "customers.csv", "Müşteri kimliği, segmenti, bağlı olduğu servis ve müşteri yaşam döngüsü bilgileri."),
    ("motorcycles", "df_motorcycles", "source_tables", "motorcycles.csv", "Müşterilere ait motosiklet örnekleri; model, üretim yılı, sahiplik ve gözlem dönemi bilgileri."),
    ("motorcycle_models", "df_motorcycle_models", "source_tables", "ridebase_motorcycle_models_v1.csv", "Motosiklet modellerinin teknik özellik masterı ve simülasyonda kullanılan model aralıkları."),
    ("usage_profiles", "df_usage_profiles", "source_tables", "usage_profiles.csv", "Motosikletlerin kullanım tipi, sürüş yoğunluğu, yol dağılımı ve çevresel kullanım profili."),
    ("mileage_monthly", "df_mileage_monthly", "source_tables", "mileage_timeline_monthly.csv", "Her motosiklet için aylık longitudinal kilometre gelişimi."),
    ("maintenance_tasks", "df_maintenance_tasks", "source_tables", "maintenance_tasks.csv", "Bakım işlemlerinin canonical taksonomisi ve teknik uygulanabilirlik kuralları."),
    ("maintenance_policies", "df_maintenance_policies", "source_tables", "maintenance_policies.csv", "Model veya politika grubuna göre kilometre, zaman, aşınma ve kullanım koşullu bakım kuralları."),
    ("appointments", "df_appointments", "source_tables", "appointments.csv", "Servis randevuları ve CONVERTED/CANCELLED/NO_SHOW/RESCHEDULED yaşam döngüsü."),
    ("services", "df_services", "source_tables", "services.csv", "Ham/base servis olayı tablosu. Toplu maliyet alanları burada bilinçli olarak boş bırakılmıştır."),
    ("services_enriched", "df_services_enriched", "source_tables", "services_enriched.csv", "Servis olaylarının hesaplanmış maliyet alanları eklenmiş analiz-hazır sürümü."),
    ("service_tasks", "df_service_tasks", "source_tables", "service_tasks.csv", "Her servis planında yer alan bakım görevleri, durumları, süreleri ve işçilik maliyetleri."),
    ("service_parts", "df_service_parts", "source_tables", "service_parts.csv", "Servis görevlerinde kullanılan parçalar, miktarlar, uyumluluk ve alış/satış tutarları."),
    ("service_status_history", "df_service_status_history", "derived_outputs", "service_status_history.csv", "Her servisin canonical ve monoton durum zaman çizelgesi; timestamp onarımlarının güvenilir kaynağı."),
    ("noise_audit", "df_noise_audit", "derived_outputs", "noise_audit.csv", "Kontrollü metin gürültüsü, tahmini kilometre ve timestamp onarımlarının denetim izi."),
    ("ml_snapshots", "df_ml_snapshots", "derived_outputs", "ml_maintenance_snapshots.parquet", "Her teslim edilmiş servis sonrasında, yalnızca o ana kadarki bilgilerle oluşturulan ML feature snapshot'ları."),
    ("next_service_targets", "df_next_service_targets", "derived_outputs", "ml_next_service_targets.parquet", "Her snapshot için bir sonraki servise kalan gün/kilometre ve right-censoring hedefleri."),
    ("next_task_targets", "df_next_task_targets", "derived_outputs", "ml_next_task_targets.parquet", "Bir sonraki gözlenen servisteki canonical task'lar için çok etiketli hedef tablosu."),
    ("split_manifest", "df_split_manifest", "derived_outputs", "split_manifest.csv", "Zaman bazlı train/validation/test ayrımı ve unseen-motorcycle/workshop değerlendirme rejimleri."),
]


EXACT = {
    "workshop_id": "Servis noktasının benzersiz kimliği.",
    "customer_id": "Müşterinin benzersiz kimliği.",
    "motorcycle_id": "Motosiklet örneğinin benzersiz kimliği.",
    "model_id": "Teknik model masterına bağlanan model kimliği.",
    "service_id": "Servis olayının benzersiz kimliği.",
    "appointment_id": "Randevunun benzersiz kimliği.",
    "service_task_id": "Servis görevi satırının benzersiz kimliği.",
    "service_part_id": "Serviste kullanılan parça satırının benzersiz kimliği.",
    "snapshot_id": "Feature ve target tablolarını birleştiren benzersiz snapshot anahtarı.",
    "source_service_id": "Snapshot'ı oluşturan mevcut servis olayının kimliği.",
    "next_service_id": "Snapshot sonrasındaki ilk servis kimliği; censored ise NULL.",
    "task_code": "Canonical bakım görevi kodu.",
    "policy_id": "Bakım politikası kuralının benzersiz kimliği.",
    "usage_profile_id": "Kullanım profili satırının benzersiz kimliği.",
    "timeline_id": "Aylık kilometre zaman çizelgesi satır kimliği.",
    "manifest_id": "Split manifest satırının benzersiz kimliği.",
    "noise_audit_id": "Gürültü/onarım audit kaydının benzersiz kimliği.",
    "status_history_id": "Servis durum geçmişi satırının benzersiz kimliği.",
    "brand": "Motosiklet markası.",
    "model_name": "Motosiklet model adı.",
    "category": "Scooter, commuter, naked vb. motosiklet kategorisi.",
    "powertrain_type": "Güç aktarma türü: ICE veya EV.",
    "production_year": "Motosiklet örneğinin üretim yılı.",
    "production_start_year": "Simülasyonda model için kullanılan en erken üretim yılı.",
    "production_end_year": "Simülasyonda model için kullanılan en geç üretim yılı.",
    "production_year_range_basis": "Model üretim yılı aralığının hangi kuralla belirlendiği.",
    "production_year_range_confidence": "Üretim yılı aralığının güven seviyesi; OEM kesinliği değildir.",
    "cooling_type": "Motor soğutma türü: AIR, OIL, LIQUID veya EV için NONE.",
    "final_drive_type": "Son aktarım türü: zincir, kayış, şaft veya doğrudan aktarım.",
    "transmission_type": "Şanzıman/aktarma sistemi türü.",
    "engine_displacement_cc": "Motor hacmi (cc); bilinmiyorsa NULL.",
    "engine_oil_service_qty_l": "Bakımda kullanılan motor yağı miktarı (litre); bilinmiyorsa NULL.",
    "spark_plug_count": "Buji adedi; bilinmiyorsa NULL, uygulanmıyorsa 0 olabilir.",
    "is_active": "İlgili müşteri veya motosiklet kaydının veri setinin gözlem süresi sonunda RideBase sisteminde hâlâ takip edilip edilmediğini gösterir. 1 hâlâ aktif/takip ediliyor, 0 takip sona ermiş demektir. Motosikletin motorunun o anda çalışıp çalışmadığını göstermez.",
    "churn_date": "Pasif müşterinin ayrılma tarihi; aktif müşteride NULL.",
    "observation_start_date": "Motosiklet gözlem döneminin başlangıç tarihi.",
    "observation_end_date": "Pasif motosiklette gözlem bitiş tarihi; aktif motosiklette NULL olabilir.",
    "profile_start_date": "Kullanım profilinin geçerlilik başlangıcı.",
    "profile_end_date": "Pasif motosiklette profil bitişi; aktif motosiklette NULL olabilir.",
    "received_at": "Servisin kabul edildiği ham zaman damgası.",
    "completed_at": "Servis/görevin tamamlanma zaman damgası; bağlama göre ham veya görev seviyesi.",
    "delivered_at": "Motosikletin müşteriye teslim edildiği ham zaman damgası.",
    "status_at": "Canonical servis durum olayının zaman damgası.",
    "snapshot_at": "Canonical DELIVERED anına eşit snapshot zaman damgası.",
    "snapshot_odometer_km": "Snapshot anındaki kilometre sayacı.",
    "odometer_km": "Servis kabulündeki kilometre sayacı.",
    "opening_odometer_km": "Aylık dönemin açılış kilometresi.",
    "closing_odometer_km": "Aylık dönemin kapanış kilometresi.",
    "km_added": "Aylık dönemde eklenen kilometre.",
    "target_event_observed": "Snapshot sonrası servis gözlendiyse 1, aksi halde 0.",
    "is_right_censored": "Gözlem ufkunda sonraki servis bilinmiyorsa 1.",
    "days_to_next_service": "Bir sonraki servise kalan temiz gün hedefi; censored ise NULL.",
    "km_to_next_service": "Bir sonraki servise kalan geçerli kilometre hedefi; censored/geçersiz ise NULL.",
    "days_to_event_or_censor": "Servis olayına veya administrativ censor tarihine kadar geçen gün.",
    "next_task_codes": "Sonraki gözlenen servisteki canonical task kodları; censored ise NULL.",
    "next_completed_task_codes": "Sonraki serviste tamamlanan task kodları; censored ise NULL.",
    "next_declined_task_codes": "Sonraki serviste reddedilen task kodları; censored ise NULL, reddedilen yoksa boş liste gösterimi.",
    "primary_time_split": "Ana zaman bazlı TRAIN/VALIDATION/TEST etiketi.",
    "unseen_motorcycle_split": "Motosiklet bazlı group-holdout değerlendirme etiketi.",
    "unseen_workshop_split": "Workshop bazlı group-holdout değerlendirme etiketi.",
    "canonical_clean_value": "Kullanılabilir canonical temiz/onarılmış değer.",
    "original_clean_value": "Varsa gürültü öncesi birebir değer; saklanmadıysa NULL.",
    "clean_value_available": "Canonical temiz temsil mevcutsa 1.",
    "original_clean_value_available": "Birebir gürültü öncesi değer saklandıysa 1.",
    "repair_applied": "Audit kaydında onarım uygulandıysa 1.",
    "repair_reason": "Timestamp onarım gerekçesi; onarım yoksa NULL.",
    "labor_total": "Toplam işçilik tutarı; base services tablosunda bilinçli boş, enriched tabloda dolu.",
    "parts_total": "Toplam parça satış tutarı; base services tablosunda bilinçli boş, enriched tabloda dolu.",
    "discount_total": "Toplam indirim tutarı; base services tablosunda bilinçli boş, enriched tabloda dolu.",
    "tax_total": "Toplam vergi tutarı; base services tablosunda bilinçli boş, enriched tabloda dolu.",
    "grand_total": "İndirim ve vergi sonrası genel servis tutarı; enriched tablo analiz kaynağıdır.",
    "data_origin": "Kaydın nereden geldiğini gösterir. SYNTHETIC değeri, kaydın gerçek bir müşteri, motosiklet veya servis işleminden alınmadığını; bilgisayar tarafından yapay olarak üretildiğini belirtir. Veri analizi sırasında gerçek operasyon verisiyle karıştırılmaması için tutulur.",
    "generator_version": "Kaydı oluşturan sentetik veri üretim kodunun ve kurallarının sürümüdür. 1.1.0 değeri, kaydın RideBase v1.1 üretim kurallarıyla hazırlandığını gösterir. Bu alan motosikletin ECU/yazılım sürümü değildir; veri üretimini izlemek ve farklı dataset sürümlerini ayırmak içindir.",
    "random_seed": "Sentetik üretimdeki rastgele görünen seçimleri tekrar üretilebilir yapan başlangıç sayısıdır. Seed 42 ve üretim kuralları aynı tutulursa aynı seçimler yeniden elde edilir. Gerçek dünyada müşteri veya motosiklete ait bir özellik değildir ve ML modeline verilmemelidir.",
    "scenario_id": "Sentetik üretim senaryosu kimliği.",
    "model_assignment_basis": "Sentetik bir motosiklete hangi modelin atanacağını belirleyen yöntemin adıdır. MARKET_WEIGHT_X_CUSTOMER_TYPE_X_WORKSHOP_SPECIALIZATION ifadesi; modelin simülasyondaki pazar ağırlığının, müşteri tipinin ve bağlı servisin uzmanlık alanının birlikte değerlendirildiğini anlatır. Gerçek bir satış veya OEM atama kaydı değildir.",
    "notes": "Kayıt hakkında gerektiğinde ek açıklama yazılabilecek opsiyonel not alanıdır. Bu tabloda bütün değerler boşsa pandas veri tipini float64 olarak tahmin edebilir; buna rağmen alanın kavramsal anlamı sayısal ölçüm değil serbest metindir. Boş olması veri hatası değildir.",
    "vin_synthetic": "Motosiklet için yapay olarak üretilmiş şasi/araç kimlik numarasıdır. VIN, Vehicle Identification Number (Araç Kimlik Numarası) anlamına gelir. Örneğin RBSYN28086615C98F içindeki RB RideBase'i, SYN sentetik olduğunu, kalan karakterler ise benzersizliği temsil eder. Gerçek bir araca ait değildir. Tabloları birleştirmek için bunun yerine motorcycle_id kullanılmalı; benzersiz kimlik olduğu için ML özelliği olarak modele verilmemelidir.",
    "plate_synthetic": "Motosiklet için yapay olarak üretilmiş plaka numarasıdır. Örneğin SYN-35-000001 içinde SYN kaydın sentetik olduğunu, 35 simüle edilen şehir plaka kodunu, 000001 ise benzersiz sıra numarasını gösterir. Gerçek bir araç veya kişiye ait değildir. Tablo bağlantılarında motorcycle_id kullanılmalı; bu benzersiz kimlik ML modeline özellik olarak verilmemelidir.",
    "workshop_name": "Servis noktasına verilen sentetik işletme adı. Gerçek bir işletmeyi temsil etmez; raporlarda servisleri okunabilir adla göstermek için kullanılır.",
    "city": "Servis noktasının veya müşterinin bulunduğu şehir. Bölgesel servis yoğunluğu ve kullanım farklılıklarını karşılaştırmak için kullanılır.",
    "district_profile": "Servis çevresinin yerleşim karakteri. Örneğin yoğun metropol, banliyö veya daha seyrek yerleşim; trafik, müşteri hacmi ve kullanım biçimini temsil eden sentetik kategoridir.",
    "region": "Şehrin bağlı olduğu coğrafi bölge; örneğin Marmara veya Ege. Bölgesel karşılaştırmalarda kullanılır.",
    "climate_zone": "Kullanım bölgesinin iklim sınıfı. Sıcaklık ve nem gibi çevresel koşulların sürüş mevsimselliği ve bakım/aşınma simülasyonuna etkisini temsil eder; gerçek zamanlı hava durumu değildir.",
    "price_level": "Servis noktasının göreli fiyat segmenti. LOW/MEDIUM/HIGH gibi sınıflar gerçek TL tarifesi değil, servisler arası fiyat seviyesi farkını simüle eder.",
    "opening_time": "Servis noktasının normal çalışma günlerindeki açılış saati.",
    "closing_time": "Servis noktasının normal çalışma günlerindeki kapanış saati.",
    "working_days": "Servisin düzenli açık olduğu haftanın günleri. Virgülle ayrılmış gün kodları kullanılır; MON Pazartesi, TUE Salı vb.",
    "sunday_open": "Servis pazar günü açıksa 1, kapalıysa 0.",
    "service_bay_count": "Aynı anda motosiklet üzerinde çalışılabilen fiziksel servis istasyonu/lift alanı sayısı.",
    "technician_count": "Servis noktasındaki toplam teknisyen sayısı.",
    "senior_technician_count": "Toplam teknisyenler içindeki kıdemli teknisyen sayısı.",
    "daily_service_capacity": "Servis noktasının bir iş gününde tamamlayabileceği yaklaşık motosiklet sayısı.",
    "appointment_rate": "Servislerin randevulu gelme payı. 0,45 değeri yaklaşık %45 demektir.",
    "walk_in_rate": "Randevusuz gelen servislerin payı. 0,55 değeri yaklaşık %55 demektir.",
    "avg_parts_lead_days": "Stokta olmayan bir parçanın servise ulaşması için gereken ortalama gün sayısı.",
    "same_day_parts_rate": "Gerekli parçanın aynı gün temin edilebilme oranı. 0–1 aralığındadır.",
    "multibrand": "Servis birden fazla motosiklet markasına hizmet veriyorsa 1; tek marka/uzman servis ise 0.",
    "specialization": "Servisin yoğunlaştığı motosiklet kategorileri. Birden fazla kategori noktalı virgülle ayrılabilir.",
    "supported_powertrains": "Servisin bakım yapabildiği güç sistemi türleri; örneğin ICE içten yanmalı, EV elektrikli motosiklet.",
    "supported_final_drives": "Servisin desteklediği son aktarım sistemleri; örneğin CHAIN zincir, V_BELT kayış, SHAFT şaft.",
    "supports_ev": "Servis elektrikli motosiklete hizmet verebiliyorsa 1.",
    "supports_abs_diagnostics": "Serviste ABS arıza tespit imkânı varsa 1.",
    "supports_advanced_diagnostics": "Serviste ileri seviye elektronik/ECU teşhis imkânı varsa 1.",
    "labor_rate_index": "Servisin işçilik fiyatını referans seviyeye göre çarpan göreli endeks. 1,0 referans; 1,2 yaklaşık %20 daha yüksek fiyat seviyesi demektir.",
    "parts_sale_multiplier": "Parça alış maliyetinden satış fiyatına geçerken kullanılan servis bazlı göreli çarpan.",
    "customer_volume_index": "Servisin göreli müşteri yoğunluğu endeksi. 1,0 referans hacmi temsil eder.",
    "courier_customer_share": "Müşteriler içinde kurye/yoğun ticari kullanım profiline sahip olanların tahmini payı.",
    "seasonality_strength": "Kullanım veya servis talebinin mevsimlere göre ne kadar değiştiğini gösteren 0–1 arası sentetik güç katsayısı.",
}


TURKISH_EXACT = {
    "workshop_id": "servis noktası kimliği", "workshop_name": "servis noktası adı",
    "customer_id": "müşteri kimliği", "motorcycle_id": "motosiklet kimliği",
    "model_id": "model kimliği", "service_id": "servis kimliği",
    "appointment_id": "randevu kimliği", "service_task_id": "servis görevi kimliği",
    "service_part_id": "servis parçası satır kimliği", "snapshot_id": "anlık görüntü kimliği",
    "task_code": "bakım görevi kodu", "city": "şehir", "region": "coğrafi bölge",
    "district_profile": "yerleşim bölgesi profili", "climate_zone": "iklim bölgesi sınıfı",
    "price_level": "fiyat seviyesi", "opening_time": "açılış saati", "closing_time": "kapanış saati",
    "working_days": "çalışma günleri", "sunday_open": "pazar günü açık mı",
    "service_bay_count": "servis çalışma istasyonu sayısı", "technician_count": "teknisyen sayısı",
    "senior_technician_count": "kıdemli teknisyen sayısı", "daily_service_capacity": "günlük servis kapasitesi",
    "appointment_rate": "randevulu geliş oranı", "walk_in_rate": "randevusuz geliş oranı",
    "avg_parts_lead_days": "ortalama parça tedarik süresi", "same_day_parts_rate": "aynı gün parça temin oranı",
    "multibrand": "çok markalı servis mi", "specialization": "uzmanlık alanları",
    "supported_powertrains": "desteklenen güç sistemleri", "supported_final_drives": "desteklenen son aktarım türleri",
    "supports_ev": "elektrikli motosiklet desteği", "supports_abs_diagnostics": "ABS teşhis desteği",
    "supports_advanced_diagnostics": "ileri teşhis desteği", "labor_rate_index": "işçilik fiyat endeksi",
    "parts_sale_multiplier": "parça satış çarpanı", "customer_volume_index": "müşteri hacmi endeksi",
    "courier_customer_share": "kurye müşteri payı", "seasonality_strength": "mevsimsellik gücü",
    "brand": "marka", "model_name": "model adı", "category": "motosiklet kategorisi",
    "powertrain_type": "güç sistemi türü", "production_year": "üretim yılı",
    "production_start_year": "model üretim başlangıç yılı", "production_end_year": "model üretim bitiş yılı",
    "cooling_type": "soğutma türü", "final_drive_type": "son aktarım türü",
    "transmission_type": "şanzıman türü", "engine_displacement_cc": "motor hacmi",
    "engine_oil_service_qty_l": "servislik motor yağı miktarı", "spark_plug_count": "buji sayısı",
    "is_active": "aktif mi", "churn_date": "müşteri ayrılma tarihi",
    "observation_start_date": "gözlem başlangıç tarihi", "observation_end_date": "gözlem bitiş tarihi",
    "received_at": "servise kabul zamanı", "completed_at": "tamamlanma zamanı", "delivered_at": "teslim zamanı",
    "snapshot_at": "anlık görüntü zamanı", "snapshot_odometer_km": "anlık kilometre",
    "target_event_observed": "hedef olay gözlendi mi", "is_right_censored": "sağdan sansürlü mü",
    "days_to_next_service": "sonraki servise kalan gün", "km_to_next_service": "sonraki servise kalan kilometre",
    "data_origin": "veri kökeni", "generator_version": "üretici sürümü", "random_seed": "rastgelelik tohumu",
    "scenario_id": "senaryo kimliği", "notes": "notlar",
    "vin_synthetic": "sentetik şasi numarası", "plate_synthetic": "sentetik plaka numarası",
    "model_assignment_basis": "motosiklet modeli atama yöntemi",
}


TOKEN_TR = {
    "workshop": "servis noktası", "customer": "müşteri", "motorcycle": "motosiklet", "model": "model",
    "service": "servis", "task": "görev", "part": "parça", "appointment": "randevu", "status": "durum",
    "history": "geçmiş", "source": "kaynak", "target": "hedef", "current": "mevcut", "next": "sonraki",
    "previous": "önceki", "date": "tarih", "time": "zaman", "at": "zamanı", "year": "yıl",
    "month": "ay", "day": "gün", "days": "gün", "km": "kilometre", "count": "sayı",
    "total": "toplam", "average": "ortalama", "avg": "ortalama", "rate": "oran", "ratio": "oran",
    "price": "fiyat", "cost": "maliyet", "quantity": "miktar", "type": "tür", "category": "kategori",
    "name": "ad", "code": "kod", "flag": "işaret", "reason": "neden", "basis": "dayanak",
    "version": "sürüm", "observed": "gözlenen", "estimated": "tahmini", "active": "aktif",
    "completed": "tamamlanan", "declined": "reddedilen", "created": "oluşturulma", "scheduled": "planlanan",
    "opening": "açılış", "closing": "kapanış", "city": "şehir", "region": "bölge", "climate": "iklim",
    "zone": "bölgesi", "profile": "profili", "level": "seviyesi", "supported": "desteklenen",
    "supports": "destekliyor", "required": "gerekli", "is": "mı", "has": "var mı", "use": "kullanım",
    "usage": "kullanım", "mileage": "kilometre", "odometer": "kilometre sayacı", "annual": "yıllık",
    "daily": "günlük", "monthly": "aylık", "rolling": "hareketli", "cumulative": "birikimli",
    "repair": "onarım", "clean": "temiz", "original": "orijinal", "canonical": "standartlaştırılmış",
    "available": "mevcut", "sequence": "sıra", "split": "veri bölümü", "primary": "ana",
}


def humanize(value: str) -> str:
    return value.replace("__", " ").replace("_", " ").strip()


def turkish_name(column: str) -> str:
    if column in TURKISH_EXACT:
        return TURKISH_EXACT[column]
    if column.startswith("task__"):
        return f"sonraki serviste {humanize(column.removeprefix('task__')).lower()} görevi var mı"
    words = column.replace("__", "_").split("_")
    translated = [TOKEN_TR.get(word, word) for word in words]
    return " ".join(translated)


def describe_column(dataset: str, column: str) -> str:
    if column in EXACT:
        return EXACT[column]
    if column.startswith("task__"):
        task = humanize(column.removeprefix("task__"))
        return f"Sonraki gözlenen serviste {task} görevinin bulunma etiketi: 1/0; right-censored ise NULL."
    if column.startswith("days_since_"):
        return f"Snapshot anında son {humanize(column.removeprefix('days_since_'))} olayından beri geçen gün; geçmiş olay yoksa NULL."
    if column.startswith("km_since_"):
        return f"Snapshot anında son {humanize(column.removeprefix('km_since_'))} olayından beri geçen kilometre; geçmiş olay yoksa NULL."
    if column.startswith("current_"):
        return f"Snapshot'ı oluşturan mevcut servise ait {humanize(column.removeprefix('current_'))} özelliği."
    if column.startswith("next_service_"):
        return f"Bir sonraki servise ait {humanize(column.removeprefix('next_service_'))} bilgisi; censored ise NULL."
    if column.startswith("next_"):
        return f"Bir sonraki gözlenen olaya ait {humanize(column.removeprefix('next_'))} bilgisi; censored ise NULL olabilir."
    if column.startswith("target_"):
        return f"Modelleme hedefi veya hedef kalite bayrağı: {humanize(column.removeprefix('target_'))}."
    if column.startswith("censor_"):
        return f"Right-censoring için {humanize(column.removeprefix('censor_'))} bilgisi."
    if column.startswith("rolling"):
        return f"Yakın geçmiş servisler üzerinden hesaplanan hareketli {humanize(column)} özelliği."
    if column.startswith("avg_"):
        return f"Ortalama {humanize(column.removeprefix('avg_'))} değeri."
    if column.startswith("total_"):
        return f"Toplam {humanize(column.removeprefix('total_'))} sayısı veya tutarı."
    if column.startswith("cumulative_"):
        return f"Snapshot anına kadar birikimli {humanize(column.removeprefix('cumulative_'))} değeri."
    if column.endswith("_id"):
        return f"{humanize(column.removesuffix('_id')).capitalize()} için kimlik veya dış anahtar."
    if column.endswith("_at"):
        return f"{humanize(column.removesuffix('_at')).capitalize()} olayının zaman damgası."
    if column.endswith("_date"):
        return f"{humanize(column.removesuffix('_date')).capitalize()} tarihi."
    if column.endswith("_count"):
        return f"{humanize(column.removesuffix('_count')).capitalize()} adedi."
    if column.endswith("_ratio"):
        return f"{humanize(column.removesuffix('_ratio')).capitalize()} oranı; genellikle 0–1 aralığında."
    if column.endswith("_rate"):
        return f"{humanize(column.removesuffix('_rate')).capitalize()} oranı/hızı."
    if column.endswith("_pct"):
        return f"{humanize(column.removesuffix('_pct')).capitalize()} yüzdesi."
    if column.startswith("is_") or column.startswith("supports_") or column.startswith("requires_"):
        return f"{humanize(column).capitalize()} durumunu gösteren bayrak veya uygulanabilirlik alanı."
    if column.endswith("_version"):
        return f"{humanize(column.removesuffix('_version')).capitalize()} sürümü."
    if column.endswith("_source") or column.endswith("_basis"):
        return f"{humanize(column).capitalize()} için kaynak/yöntem bilgisi."
    if column.endswith("_km"):
        return f"Kilometre cinsinden {humanize(column.removesuffix('_km'))} değeri."
    if column.endswith("_days"):
        return f"Gün cinsinden {humanize(column.removesuffix('_days'))} değeri."
    if column.endswith("_minutes"):
        return f"Dakika cinsinden {humanize(column.removesuffix('_minutes'))} değeri."
    if column.endswith("_total") or column.endswith("_cost") or column.endswith("_price"):
        return f"Parasal {humanize(column)} değeri; para birimi ilgili currency alanıyla belirlenir."
    return f"{turkish_name(column).capitalize()} bilgisini tutar. Bu alanın gerçek örnek değerleri yan sütunda gösterilmiştir; yorumlarken tablonun bir satırının neyi temsil ettiği dikkate alınmalıdır."


def example_values(series: pd.Series, limit: int = 3) -> str:
    values = series.dropna().astype(str)
    values = values[values.str.strip().ne("")].drop_duplicates().head(limit).tolist()
    if not values:
        return "NULL"
    cleaned = [value[:55] + ("…" if len(value) > 55 else "") for value in values]
    return ", ".join(f"`{value}`" for value in cleaned).replace("|", "\\|")


def load_schema(layer: str, filename: str) -> pd.DataFrame:
    path = DATA_ROOT / layer / filename
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


schemas = {}
for key, _, layer, filename, _ in TABLES:
    df = load_schema(layer, filename)
    schemas[key] = [(column, str(dtype), example_values(df[column])) for column, dtype in df.dtypes.items()]


nb = nbf.v4.new_notebook()
nb.metadata.kernelspec = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb.metadata.language_info = {"name": "python", "version": "3.11"}

cells = [
    nbf.v4.new_markdown_cell(
        "# RideBase — 02 EDA: Veri Sözlüğü ve DataFrame Hazırlığı\n\n"
        "Bu notebook RideBase Synthetic Dataset **v1.1** içindeki 19 tablonun amacını ve bütün sütunlarını açıklar; "
        "ardından dosyaları açık dataframe değişkenlerine yükler.\n\n"
        "Her sütun için teknik İngilizce adın yanında **Türkçe karşılık**, sade anlam ve gerçek örnek değer verilir. "
        "Buradaki **anlam/semantik**, bir sütunun yalnızca veri tipini değil, gerçek hayatta neyi temsil ettiğini ve nasıl yorumlanması gerektiğini ifade eder.\n\n"
        "> Not: Yüksek NULL oranı tek başına veri hatası değildir. Right-censoring, aktif varlıklar, uygulanabilirlik kuralları, "
        "opsiyonel metinler ve bilinmeyen teknik özellikler gerçek NULL ile temsil edilir."
    ),
    nbf.v4.new_markdown_cell(
        "## Veri katmanları\n\n"
        "- **source_tables:** İlişkisel operasyon ve master tabloları.\n"
        "- **derived_outputs:** Canonical zaman çizelgesi, audit, ML feature/target ve split tabloları.\n"
        "- `services.csv` base event tablosudur; maliyet analizi için `services_enriched.csv` kullanılmalıdır.\n"
        "- Snapshot feature'ları yalnızca `snapshot_at` anına kadar olan bilgileri içerir; gelecek hedefleri ayrı tablolardadır."
    ),
    nbf.v4.new_markdown_cell("## Tablolar ve tüm sütunların açıklamaları")
]

for key, var_name, layer, filename, purpose in TABLES:
    column_cards = []
    for number, (column, dtype, examples) in enumerate(schemas[key], start=1):
        desc = describe_column(key, column).replace("|", "\\|")
        column_cards.append(
            f"#### {number}. `{column}` — {turkish_name(column)}\n\n"
            f"- **Veri tipi:** `{dtype}`\n"
            f"- **Ne demek?** {desc}\n"
            f"- **Veri içinden örnekler:** {examples}"
        )
    cells.append(nbf.v4.new_markdown_cell(
        f"### `{key}` — `{filename}`\n\n"
        f"**DataFrame:** `{var_name}`  \n"
        f"**Katman:** `{layer}`  \n"
        f"**Amaç:** {purpose}  \n"
        f"**Sütun sayısı:** {len(schemas[key])}\n\n"
        "Aşağıda her sütun yatay kaydırma gerektirmeyen dikey bilgi kartı biçiminde açıklanmıştır.\n\n"
        + "\n\n---\n\n".join(column_cards)
    ))

cells.extend([
    nbf.v4.new_markdown_cell("## DataFrame yükleme kodları"),
    nbf.v4.new_code_cell(
        "from pathlib import Path\n"
        "import json\n\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "from IPython.display import display\n\n"
        "pd.set_option(\"display.max_columns\", None)\n"
        "pd.set_option(\"display.max_rows\", 200)\n"
        "pd.set_option(\"display.max_colwidth\", 160)\n"
        "pd.set_option(\"display.width\", 220)"
    ),
    nbf.v4.new_code_cell(
        "def find_project_root() -> Path:\n"
        "    current = Path.cwd().resolve()\n"
        "    for candidate in [current, *current.parents]:\n"
        "        if (candidate / \"notebooks\").is_dir() and (candidate / \"src\").is_dir():\n"
        "            return candidate\n"
        "    raise FileNotFoundError(\"ridebase-ml proje kökü bulunamadı.\")\n\n"
        "PROJECT_ROOT = find_project_root()\n"
        "DATASET_ROOT = PROJECT_ROOT.parent / \"ridebase_v1_1\"\n"
        "SOURCE_DIR = DATASET_ROOT / \"source_tables\"\n"
        "DERIVED_DIR = DATASET_ROOT / \"derived_outputs\"\n"
        "REPORTS_DIR = PROJECT_ROOT / \"reports\"\n\n"
        "if not SOURCE_DIR.is_dir() or not DERIVED_DIR.is_dir():\n"
        "    raise FileNotFoundError(f\"RideBase v1.1 bulunamadı: {DATASET_ROOT}\")\n\n"
        "print(\"Project root :\", PROJECT_ROOT)\n"
        "print(\"Dataset root :\", DATASET_ROOT)\n"
        "print(\"Source tables:\", SOURCE_DIR)\n"
        "print(\"Derived files:\", DERIVED_DIR)"
    ),
    nbf.v4.new_code_cell(
        "# Source tablolar\n"
        "df_workshops = pd.read_csv(SOURCE_DIR / \"workshops.csv\", encoding=\"utf-8-sig\")\n"
        "df_customers = pd.read_csv(SOURCE_DIR / \"customers.csv\", encoding=\"utf-8-sig\")\n"
        "df_motorcycles = pd.read_csv(SOURCE_DIR / \"motorcycles.csv\", encoding=\"utf-8-sig\")\n"
        "df_motorcycle_models = pd.read_csv(SOURCE_DIR / \"ridebase_motorcycle_models_v1.csv\", encoding=\"utf-8-sig\")\n"
        "df_usage_profiles = pd.read_csv(SOURCE_DIR / \"usage_profiles.csv\", encoding=\"utf-8-sig\")\n"
        "df_mileage_monthly = pd.read_csv(SOURCE_DIR / \"mileage_timeline_monthly.csv\", encoding=\"utf-8-sig\")\n"
        "df_maintenance_tasks = pd.read_csv(SOURCE_DIR / \"maintenance_tasks.csv\", encoding=\"utf-8-sig\")\n"
        "df_maintenance_policies = pd.read_csv(SOURCE_DIR / \"maintenance_policies.csv\", encoding=\"utf-8-sig\")\n"
        "df_appointments = pd.read_csv(SOURCE_DIR / \"appointments.csv\", encoding=\"utf-8-sig\")\n"
        "df_services = pd.read_csv(SOURCE_DIR / \"services.csv\", encoding=\"utf-8-sig\")\n"
        "df_services_enriched = pd.read_csv(SOURCE_DIR / \"services_enriched.csv\", encoding=\"utf-8-sig\")\n"
        "df_service_tasks = pd.read_csv(SOURCE_DIR / \"service_tasks.csv\", encoding=\"utf-8-sig\")\n"
        "df_service_parts = pd.read_csv(SOURCE_DIR / \"service_parts.csv\", encoding=\"utf-8-sig\")\n\n"
        "print(\"13 source dataframe yüklendi.\")"
    ),
    nbf.v4.new_code_cell(
        "# Derived / ML tablolar\n"
        "df_service_status_history = pd.read_csv(DERIVED_DIR / \"service_status_history.csv\", encoding=\"utf-8-sig\")\n"
        "df_noise_audit = pd.read_csv(DERIVED_DIR / \"noise_audit.csv\", encoding=\"utf-8-sig\")\n"
        "df_ml_snapshots = pd.read_parquet(DERIVED_DIR / \"ml_maintenance_snapshots.parquet\", engine=\"pyarrow\")\n"
        "df_next_service_targets = pd.read_parquet(DERIVED_DIR / \"ml_next_service_targets.parquet\", engine=\"pyarrow\")\n"
        "df_next_task_targets = pd.read_parquet(DERIVED_DIR / \"ml_next_task_targets.parquet\", engine=\"pyarrow\")\n"
        "df_split_manifest = pd.read_csv(DERIVED_DIR / \"split_manifest.csv\", encoding=\"utf-8-sig\")\n\n"
        "with open(DERIVED_DIR / \"dataset_metadata.json\", encoding=\"utf-8\") as file:\n"
        "    dataset_metadata = json.load(file)\n\n"
        "with open(DERIVED_DIR / \"quality_report.json\", encoding=\"utf-8\") as file:\n"
        "    quality_report = json.load(file)\n\n"
        "print(\"6 derived dataframe ve 2 JSON dokümanı yüklendi.\")"
    ),
    nbf.v4.new_code_cell(
        "dataframes = {\n"
        "    \"workshops\": df_workshops,\n"
        "    \"customers\": df_customers,\n"
        "    \"motorcycles\": df_motorcycles,\n"
        "    \"motorcycle_models\": df_motorcycle_models,\n"
        "    \"usage_profiles\": df_usage_profiles,\n"
        "    \"mileage_monthly\": df_mileage_monthly,\n"
        "    \"maintenance_tasks\": df_maintenance_tasks,\n"
        "    \"maintenance_policies\": df_maintenance_policies,\n"
        "    \"appointments\": df_appointments,\n"
        "    \"services\": df_services,\n"
        "    \"services_enriched\": df_services_enriched,\n"
        "    \"service_tasks\": df_service_tasks,\n"
        "    \"service_parts\": df_service_parts,\n"
        "    \"service_status_history\": df_service_status_history,\n"
        "    \"noise_audit\": df_noise_audit,\n"
        "    \"ml_snapshots\": df_ml_snapshots,\n"
        "    \"next_service_targets\": df_next_service_targets,\n"
        "    \"next_task_targets\": df_next_task_targets,\n"
        "    \"split_manifest\": df_split_manifest,\n"
        "}\n\n"
        "print(\"Registry tablo sayısı:\", len(dataframes))"
    ),
    nbf.v4.new_code_cell(
        "inventory = pd.DataFrame([\n"
        "    {\n"
        "        \"dataset\": name,\n"
        "        \"rows\": len(df),\n"
        "        \"columns\": len(df.columns),\n"
        "        \"missing_cells\": int(df.isna().sum().sum()),\n"
        "        \"duplicate_rows\": int(df.duplicated().sum()),\n"
        "        \"memory_mb\": round(df.memory_usage(deep=True).sum() / 1_000_000, 2),\n"
        "    }\n"
        "    for name, df in dataframes.items()\n"
        "]).sort_values(\"rows\", ascending=False).reset_index(drop=True)\n\n"
        "display(inventory)"
    ),
    nbf.v4.new_markdown_cell("## DataFrame inceleme yardımcıları"),
    nbf.v4.new_code_cell(
        "def show_dataframe(dataset_name: str, n: int = 5):\n"
        "    \"\"\"Registry'deki bir tabloyu boyut, sütun ve örnek satırlarla gösterir.\"\"\"\n"
        "    if dataset_name not in dataframes:\n"
        "        raise KeyError(f\"Bilinmeyen dataset: {dataset_name}. Seçenekler: {list(dataframes)}\")\n"
        "    df = dataframes[dataset_name]\n"
        "    print(f\"{dataset_name}: {df.shape[0]:,} satır × {df.shape[1]} sütun\")\n"
        "    print(\"Sütunlar:\", df.columns.tolist())\n"
        "    display(df.head(n))\n\n"
        "show_dataframe(\"services_enriched\")"
    ),
    nbf.v4.new_markdown_cell(
        "## Sonraki adım\n\n"
        "Dataframe'ler hazır. Bundan sonraki hücrelerde sırasıyla entity dağılımları, servis davranışı, zaman analizi, "
        "segment karşılaştırmaları ve ML hedef analizi yapılabilir."
    ),
])

nb.cells = cells
nbf.write(nb, NOTEBOOK_PATH)
print(f"Created: {NOTEBOOK_PATH}")
