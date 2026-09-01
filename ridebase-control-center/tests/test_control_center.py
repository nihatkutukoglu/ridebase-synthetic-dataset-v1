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


if __name__ == "__main__":
    unittest.main()
