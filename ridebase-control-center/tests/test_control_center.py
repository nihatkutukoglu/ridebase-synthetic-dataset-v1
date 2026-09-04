"""Contract checks for the authoritative static Control Center source/build."""

from pathlib import Path
import subprocess
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

    def test_live_prediction_is_first_and_default_for_v1_and_v2(self):
        for source in (self.template, self.built):
            self.assertIn('var sub=parts[1]||((route==="v1"||route==="v2"||route==="v2_1")?"predict":null);', source)
            self.assertIn('sub=sub||"predict";', source)
            self.assertIn('var subs=[["predict","Canlı Tahmin"],["overview","Overview"]', source)
            self.assertIn('var v2subs=[["predict","Canlı Tahmin"],["overview","Genel Bakış"]', source)
            self.assertIn('var tabs=[["predict","Canlı Tahmin"],["overview","Overview"]', source)
            self.assertIn('var tabs=[["predict","Canlı Tahmin"],["overview","Genel Bakış"]', source)

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

    def test_deterministic_maintenance_status_is_separate_and_prominent(self):
        for text in (
            "function v2MaintenanceCard",
            "DETERMİNİSTİK BAKIM DURUMU",
            "SERVİS ŞİMDİ GEREKLİ",
            "BAKIM İLERLEMESİ",
            "Ana bakım periyodu",
            "MÜŞTERİNİN KENDİLİĞİNDEN SERVİSE GELME İHTİMALİ",
            "V1 KİŞİSEL TARİH / MESAFE GÖSTERİLMEDİ",
            "model yılı ve Türkiye pazarı",
            "d.maintenance",
            "d.decision",
        ):
            self.assertInBoth(text)

    def test_incomplete_history_is_presented_as_cohort_scenario(self):
        for text in (
            "GENEL / BENZER MOTORLARA DAYALI SENARYO",
            "Güncel kilometre, son servis tarihi ve son servis kilometresi birlikte gerekli",
            "kişisel bakım tarihi hesaplanmadı",
            "müşterinin kendiliğinden gelme ihtimali",
            "decision.show_v1_point_estimate===false",
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

    def test_v2_0_failed_audit_stays_visible_and_v2_1_is_not_v2_0(self):
        # V2.0's failed audit must remain prominent, and its research scenario is
        # never relabelled as V2.1.
        for text in (
            "V2.0 · LIVE-SCENARIO AUDIT FAILED",
            "V2.0 CANLI SENARYO İÇİN GÜVENİLİR DEĞİL",
            "V2.0 ARAŞTIRMA SENARYOSU · ÜRÜN KARARI İÇİN KULLANMA",
            "SOURCE SCHEMA v1.3 · UNCHANGED",
        ):
            self.assertInBoth(text)
        # the obsolete "modelling stopped / not published" claims are gone
        for text in (
            "V2.1 DYNAMIC LANDMARK · MODELLEME DURDURULDU",
            "V2.1 modeli, metriği veya tahmin API rotası yayımlanmadı",
            "DATA GATE FAILED",
        ):
            self.assertNotIn(text, self.template)
            self.assertNotIn(text, self.built)

    def test_v2_0_scenario_is_never_presented_as_v2_1(self):
        for source in (self.template, self.built):
            body = self.function_body(source, "v2RunScenario", "v2ModeDemo")
            self.assertIn("V2.0 ARAŞTIRMA SENARYOSU", body)
            self.assertIn("arbitrary-day auditini geçmedi", body)
            self.assertNotIn("V2.1 tahmini", body)

    def test_v2_1_experimental_live_state_is_truthful(self):
        for text in (
            "V2.1 Landmark",                       # dedicated route/module
            "v2_1:{label:\"V2.1 Landmark\"",       # SPA route registered
            "/api/v2_1/predict/scenario",          # V2.1 API path, not /api/v2/
            "wireV2_1Predict",
            "EXPERIMENTAL LIVE (SYNTHETIC)",
            "SENTETİK VERİDE DOĞRULANDI",
            "GERÇEK RIDEBASE FİLO TESTİ BEKLENİYOR",
            "REAL FLEET",
            "Bu yüzdeler <b>bakım ihtimali değildir.</b>",   # due vs return-risk separated
            "gizli değerlerini kullanmaz",                    # no hidden sample overlay
            "current_odometer_km_at_landmark olur — initial_mileage_km DEĞİL",
            "Girdi / OOD uyarıları (sonuçların ÜSTÜNDE)",     # OOD above result cards
            "Sahte tahmin üretilmez.",                        # API-down: no fake result
            "coverage is not a confidence score",
        ):
            self.assertInBoth(text)

    def test_v2_1_history_and_scenario_modes_are_distinct(self):
        for text in (
            "HISTORY PIPELINE",
            "SCENARIO / WHAT-IF",
            "/api/v2_1/predict/by-motorcycle",
            "/api/v2_1/predict/scenario",
            "HISTORY SOURCE: SYNTHETIC V1.4",
            "KISMİ BİLGİYLE SENARYO TAHMİNİ",
        ):
            self.assertInBoth(text)

        for source in (self.template, self.built):
            history_body = source.split("function v2_1RunHistory(){", 1)[1].split(
                "function v2_1HistoryResultCard", 1
            )[0]
            scenario_body = source.split("function v2_1RunScenario(){", 1)[1].split(
                "function v2_1ResultCard", 1
            )[0]
            self.assertIn("/api/v2_1/predict/by-motorcycle", history_body)
            self.assertNotIn("/api/v2_1/predict/scenario", history_body)
            self.assertIn("/api/v2_1/predict/scenario", scenario_body)
            self.assertNotIn("/api/v2_1/predict/by-motorcycle", scenario_body)

    def test_v2_1_history_result_is_honest_and_failure_has_no_fallback(self):
        for text in (
            "V2.1 EXPERIMENTAL LIVE · SYNTHETICALLY VALIDATED · REAL FLEET VALIDATION PENDING",
            "Bu sentetik V1.4 geçmişidir; gerçek RideBase müşteri geçmişi değildir.",
            "CURRENT ODOMETER",
            "LAST SERVICE",
            "FEATURE COVERAGE",
            "History feature provenance",
            "Girdi / OOD / HISTORY uyarıları (sonuçların ÜSTÜNDE)",
            "Sahte tahmin veya sahte geçmiş üretilmez.",
        ):
            self.assertInBoth(text)
        self.assertNotIn("REAL VALIDATED", self.template.upper())
        self.assertNotIn("Math.random()", self.template)

    def test_v2_1_status_manifest_is_truthful(self):
        import json
        manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
        v21 = manifest["v2_1"]
        self.assertEqual(v21["status"], "EXPERIMENTAL_LIVE")
        self.assertTrue(v21["model_available"])
        self.assertTrue(v21["prediction_route_available"])
        self.assertTrue(v21["history_pipeline_available"])
        self.assertEqual(v21["history_source"], "SYNTHETIC_V1_4")
        self.assertEqual(v21["history_parity"]["status"], "PASS")
        self.assertEqual(v21["history_api"]["status"], "PASS")
        self.assertEqual(v21["data_gate_status"], "PASS")
        self.assertEqual(v21["model_gate_status"], "PASS")
        self.assertEqual(v21["real_fleet_validation"], "PENDING")
        self.assertEqual(v21["champion"], "xgb_cox")
        self.assertEqual(v21["selection_split"], "VALIDATION")
        self.assertEqual(v21["golden_parity"]["parity_pass"], True)
        self.assertEqual(v21["p30_health"]["exact_zero_share"], 0.0)
        # V2.0 failure still recorded, V3 still on hold
        self.assertIn("V2.0 LIVE-SCENARIO AUDIT FAILED", manifest["production_status"]["model"])
        v3 = [m for m in manifest["modules"] if m["id"] == "v3"][0]
        self.assertEqual(v3["status"], "planned")

    def test_v2_1_primary_and_v2_0_legacy_scenario_product_contract(self):
        """Phase 9 Test: V2.1 is primary prediction, V2.0 is demoted legacy, and annual usage semantics are robust."""
        for text in (
            "V2.1 MÜŞTERİ SERVİS DÖNÜŞ TAHMİNİ",
            "Bu yüzdeler müşterinin belirtilen süre içinde servise geri dönme olasılığını tahmin eder. Bakım gerekliliği yukarıdaki deterministik bakım politikasından gelir.",
            "V2.0 LEGACY ARAŞTIRMA KARŞILAŞTIRMASI",
            "Arbitrary-day canlı senaryo auditini geçmedi. Ürün kararı için kullanılmaz.",
            "Legacy araştırma sonucunu göster",
            "Modelde kullanılan tahmini yıllık km",
            "Son dönem kullanım temposu (yıllıklandırılmış)",
            "DÜŞÜK GÜVEN: KISA GÖZLEM PENCERESİ",
            "HORIZON MONOTONİK",
            "P30 ≤ P60 ≤ P90 ≤ P120",
        ):
            self.assertInBoth(text)

        for source in (self.template, self.built):
            scenario_body = self.function_body(source, "v2RunScenario", "v2ModeDemo")
            self.assertIn("/api/v2_1/predict/scenario", scenario_body)
            self.assertIn("/api/v2/predict/scenario", scenario_body)
            self.assertIn("v2_1PrimaryCard", scenario_body)
            self.assertIn("v2LegacyCard", scenario_body)

    def test_deterministic_maintenance_urgency_score_ui_and_explanation_panel(self):
        """Urgency UI tests: 0-100 severity score, bands, explanation panel, and decoupling microcopy."""
        for text in (
            "function v2CalculateUrgency",
            "function v2UrgencyCard",
            "BAKIM ACİLİYETİ",
            "DETERMİNİSTİK ŞİDDET BANDI (0–100)",
            "KRİTİK",
            "ÇOK GECİKMİŞ",
            "GECİKMİŞ",
            "YAKLAŞIYOR",
            "NORMAL",
            "Bakım aciliyeti deterministik bakım politikasından hesaplanır. V2.1 yüzdeleri müşterinin servise dönme davranışını tahmin eder.",
            "Neden bu skor? (Deterministik Açıklama Paneli)",
            "Ana periyot",
            "Son servisten beri",
            "Gecikme",
            "KM ilerlemesi",
            "Zaman ilerlemesi",
            "Belirleyici ölçüt",
            "Aciliyet skoru",
            "Seviye",
            "Fallback only; backend urgency fields are canonical.",
            "Bakım periyodu içinde.",
            "Bakım zamanı yaklaşıyor.",
            "Bakım periyodu aşılmış.",
            "Bakım periyodu önemli ölçüde aşılmış.",
            "Bakım periyodu ciddi ölçüde aşılmış.",
        ):
            self.assertInBoth(text)

        for source in (self.template, self.built):
            scenario_body = self.function_body(source, "v2RunScenario", "v2ModeDemo")
            self.assertIn("v2CalculateUrgency", scenario_body)
            self.assertIn("v2UrgencyCard", scenario_body)

    def test_backend_fields_are_canonical_and_partial_contract_uses_full_fallback(self):
        runner = ROOT / "tests" / "maintenance_urgency_runner.cjs"
        payload = """[
          {"status":"OVERDUE","progress_ratio":10,"progress_pct":1000,
           "maintenance_urgency_score":17,"maintenance_urgency_level":"NORMAL",
           "maintenance_urgency_reason":"Backend gerekçesi","determining_dimension":"TIME"},
          {"status":"OVERDUE","progress_ratio":10,"progress_pct":1000,
           "maintenance_urgency_score":17,"maintenance_urgency_level":"NORMAL"}
        ]"""
        completed = subprocess.run(
            ["node", str(runner)], input=payload, text=True, capture_output=True, check=True
        )
        import json
        canonical, fallback = json.loads(completed.stdout)
        self.assertEqual(canonical["source"], "BACKEND_CANONICAL")
        self.assertEqual(canonical["score"], 17)
        self.assertEqual(canonical["level"], "NORMAL")
        self.assertEqual(canonical["reason"], "Backend gerekçesi")
        self.assertEqual(canonical["determining_dimension"], "TIME")
        self.assertEqual(fallback["source"], "FRONTEND_FALLBACK")
        self.assertEqual(fallback["score"], 100)
        self.assertEqual(fallback["level"], "KRİTİK")

    def test_python_frontend_fallback_parity_is_complete(self):
        audit = ROOT.parent / "scripts" / "audit_maintenance_urgency_parity.py"
        completed = subprocess.run(
            ["python3", str(audit)], text=True, capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_urgency_copy_never_implies_mechanical_failure_probability(self):
        forbidden = ("mekanik risk", "arıza riski", "failure risk")
        for source in (self.template, self.built):
            lowered = source.lower()
            for phrase in forbidden:
                self.assertNotIn(phrase, lowered)


if __name__ == "__main__":
    unittest.main()
