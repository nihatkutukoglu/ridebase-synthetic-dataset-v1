"""Contract checks for the authoritative static Control Center source/build."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class V1LivePredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    def test_v1_live_route_and_wiring_render(self):
        self.assertInBoth("data-go=\"v1/'+t[0]+'\"")
        self.assertInBoth("wireV1Predict()")
        self.assertInBoth("V1 — SONRAKİ SERVİS TAHMİNİ")

    def test_demo_uses_real_v1_contract(self):
        self.assertInBoth('/api/v1/sample')
        self.assertInBoth('/api/v1/predict')
        self.assertInBoth('BU ÖRNEĞİ TAHMİN ET')
        self.assertInBoth('ÖRNEK MOTOR DEMOSU')
        self.assertInBoth('Bu senin motosikletin değil.')

    def test_v1_outputs_and_derived_fields_render(self):
        for label in (
            "TAHMİNİ SONRAKİ SERVİS",
            "TAHMİNİ KALAN MESAFE",
            "TAHMİNİ SERVİS TARİHİ",
            "TAHMİNİ SERVİS KİLOMETRESİ",
        ):
            self.assertInBoth(label)

    def test_personal_mode_is_honestly_pending(self):
        self.assertInBoth("KENDİ MOTOSİKLETİMLE TAHMİN")
        self.assertInBoth(
            "Gerçek motosiklet için kişisel tahmin, servis geçmişinden feature "
            "türetme hattı bağlandıktan sonra aktif olacak."
        )
        self.assertInBoth("Bu mod bu nedenle hiçbir inference isteği göndermez.")

    def test_beginner_uncertainty_and_v2_comparison_render(self):
        for text in (
            "yaklaşık nokta tahminidir",
            "doğruluk yüzdesi değildir",
            "V2 farklı zaman aralıklarında servise gelme ihtimalini verir.",
            "V2 Survival → Canlı Tahmin",
            "SENTETİK VERİDE DOĞRULANDI",
            "GERÇEK RIDEBASE FİLO TESTİ BEKLENİYOR",
        ):
            self.assertInBoth(text)

    def test_no_fake_prediction_fallback(self):
        self.assertInBoth("Sahte tahmin üretilmez.")
        self.assertNotIn("fallbackPrediction", self.template)
        self.assertNotIn("Math.random()", self.template)

    def test_cold_start_contract(self):
        self.assertInBoth("var V2_TIMEOUT=78000")
        self.assertInBoth("deneme '+(attempt+1)+'/3")

    def test_v2_combined_contract_remains(self):
        self.assertInBoth('/api/predict/service')
        self.assertInBoth('risk_30d')
        self.assertInBoth('function wireV2Predict()')


class V2ScenarioPredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    @staticmethod
    def function_body(source, name, next_name):
        return source.split(f"function {name}(){{", 1)[1].split(f"function {next_name}", 1)[0]

    def test_three_truthful_modes_render(self):
        for label in (
            "SENARYO TAHMİNİ",
            "ÖRNEK MOTORLA DEMO",
            "GERÇEK RIDEBASE MOTORU · YAKINDA",
            "REAL DATA PIPELINE PENDING",
        ):
            self.assertInBoth(label)

    def test_catalog_and_cascading_model_selection_contract(self):
        for text in (
            "/api/v2/motorcycle-models",
            "v2ModelsForBrand",
            "v2ModelById",
            "v2SpecCard",
            "Katalog referans aralığı",
        ):
            self.assertInBoth(text)

    def test_scenario_network_path_never_uses_sample(self):
        for source in (self.template, self.built):
            body = self.function_body(source, "v2RunScenario", "v2ModeDemo")
            self.assertIn('/api/v2/predict/scenario', body)
            self.assertNotIn('/api/v2/sample', body)
            self.assertNotIn('Object.assign', body)

    def test_demo_network_path_does_use_sample(self):
        for source in (self.template, self.built):
            body = self.function_body(source, "v2ModeDemo", "v2ModeReal")
            self.assertIn('/api/v2/sample', body)
            self.assertIn('/api/predict/service', body)
            self.assertIn('ÖRNEK MOTOR DEMOSU', body)

    def test_scenario_result_and_feature_coverage_render(self):
        for text in (
            "KISMİ BİLGİYLE SENARYO TAHMİNİ",
            "TAHMİN İÇİN KULLANILAN BİLGİ DÜZEYİ",
            "MISSING_PREPROCESSOR",
            "Bu oran modelin güven skoru değildir",
            "Teknik feature provenance tablosu",
        ):
            self.assertInBoth(text)

    def test_current_odometer_is_not_initial_mileage(self):
        self.assertInBoth("Güncel kilometre</b>, V2’deki <code>initial_mileage_km</code> değildir")
        self.assertNotIn('initial_mileage_km","Mevcut kilometre', self.template)

    def test_usage_fields_have_beginner_friendly_explanations(self):
        for text in (
            "Motosikletin göstergesinde yazan toplam kilometre.",
            "Ayda 1.000 km ≈ yılda 12.000 km.",
            "Günlük ulaşım (COMMUTER)",
            "Kurye / teslimat (COURIER)",
            "Hafta sonu / hobi (WEEKEND)",
            "Az / seyrek (LOW)",
            "Düzenli / orta (MEDIUM)",
            "Sık / yoğun (HIGH)",
        ):
            self.assertInBoth(text)

    def test_no_fake_or_random_fallback(self):
        self.assertNotIn("fallbackPrediction", self.template)
        self.assertNotIn("Math.random()", self.template)
        self.assertInBoth("Sahte tahmin üretilmez.")


if __name__ == "__main__":
    unittest.main()
