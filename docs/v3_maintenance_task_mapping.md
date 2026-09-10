# V3 ↔ Bakım Politikası Görev Eşlemesi

Bu eşleme yalnız sunum içindir. V3 olasılığını, sırasını, eşiğini veya bakım planı durumunu değiştirmez.

- `EXACT`: V3 etiketi ile aktif planlı bakım görev kodu aynıdır. Yalnız bu durumda ve görev seçili motosikletin bakım planında gerçekten mevcutsa “Bakım planında da yer alıyor” rozeti gösterilebilir.
- `RELATED_BUT_NOT_EQUIVALENT`: İşlemler aynı parçaya/sisteme ilişkindir ancak aynı eylem değildir; örneğin kontrol ile değişim birbirinin yerine geçmez. Rozet gösterilmez.
- `NO_MAPPING`: Mevcut planlı bakım politikasında savunulabilir bir eş yoktur. Arıza teşhisi veya servis bulgusuna bağlı işlemler için plan görevi icat edilmez.

Makinece okunabilir kaynak: `config/v3_maintenance_task_mapping.json`.

## Denetim özeti

Donmuş V3 taksonomisindeki 44 etiketin tamamı tekil olarak sınıflandırılmıştır:

- 27 `EXACT`
- 9 `RELATED_BUT_NOT_EQUIVALENT`
- 8 `NO_MAPPING`

`EXACT` kayıtlar, V1.4 `maintenance_policies.csv` içinde aktif `SCHEDULED` görev koduyla birebir eşleşir. Lastik/akü değişimi gibi yalnız aşınma veya koşul bazlı politikası olan eylemler planlı periyot gibi sunulmaz; bunlar uygun kontrol göreviyle `RELATED_BUT_NOT_EQUIVALENT` olarak işaretlenir. Tanı, arıza ve servis bulgusu işlemleri için eşleme uydurulmaz.

Bu dosya periyotların güvenilirlik düzeyini yükseltmez. Politika satırındaki `evidence_level`, `confidence`, `source_authority` ve üreticiye özgü olup olmadığı bakım planı yanıtında ayrı alanlar olarak korunur.
