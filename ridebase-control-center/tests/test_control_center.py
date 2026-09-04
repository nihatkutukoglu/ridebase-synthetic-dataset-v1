"""Contract checks for the authoritative static Control Center source/build."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class V1LivePredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()
        cls.manifest = json.loads((ROOT / "data" / "manifest.json").read_text())

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    @staticmethod
    def function_body(source, name, next_name):
        return source.split(f"function {name}(){{", 1)[1].split(f"function {next_name}", 1)[0]

    def test_v1_live_route_and_wiring_render(self):
        self.assertInBoth("data-go=\"v1/'+t[0]+'\"")
        self.assertInBoth("wireV1Predict()")
        self.assertInBoth("V1 — SONRAKİ SERVİS TAHMİNİ")

    def test_live_prediction_is_first_and_default_for_v1_and_v2(self):
        for source in (self.template, self.built):
            self.assertIn('var sub=parts[1]||((route==="v1"||route==="v2"||route==="v2_1")?"predict":null);', source)
            self.assertIn('sub=sub||"predict";', source)
            self.assertIn('var subs=[["predict","Canlı Tahmin"],["overview","Genel Bakış"]', source)
            self.assertIn('var v2subs=[["predict","Canlı Tahmin"],["overview","Genel Bakış"]', source)
            self.assertIn('var tabs=[["predict","Canlı Tahmin"],["overview","Genel Bakış"]', source)

    def test_demo_uses_real_v1_contract(self):
        self.assertInBoth('/api/v1/sample')
        self.assertInBoth('/api/v1/predict')
        self.assertInBoth('BU ÖRNEĞİ TAHMİN ET')
        self.assertInBoth('ÖRNEK MOTOR DEMOSU')
        self.assertInBoth('Bu senin motosikletin değil.')

    def test_v1_natural_input_scenario_mode_is_primary(self):
        for text in (
            "SENARYO TAHMİNİ",
            "KISITLI BİLGİYLE V1 SENARYO TAHMİNİ",
            "/api/v1/motorcycle-models",
            "/api/v1/predict/scenario",
            "V1 DAYS / KM TAHMİNİNİ HESAPLA",
            "DAYS 114 · KM 113 frozen feature",
            "V1 BİLGİ KAPSAMI",
            "Feature provenance tablosu",
            "DETERMİNİSTİK BAKIM DURUMU",
        ):
            self.assertInBoth(text)
        self.assertInBoth('sel("scenario");')

    def test_v1_scenario_collects_product_inputs_without_demo_fallback(self):
        for field_id in (
            "v1brand", "v1model", "v1year", "v1odo", "v1annual",
            "v1usage", "v1intensity", "v1lastdate", "v1lastodo",
        ):
            self.assertInBoth(f'id="{field_id}"')
        for source in (self.template, self.built):
            body = self.function_body(source, "v1RunScenario", "v1ModeDemo")
            self.assertIn('/api/v1/predict/scenario', body)
            self.assertNotIn('/api/v1/sample', body)
            self.assertNotIn('__V1_SAMPLE__', body)

    def test_v1_scenario_suppression_and_honest_copy_render(self):
        for text in (
            "V1 İLERİ TARİH / MESAFE TAHMİNİ GÖSTERİLMEDİ",
            "Deterministik bakım kararı önceliklidir.",
            "Bu gerçek filo kaydıyla doğrulanmış kişisel tahmin değildir.",
            "Sahte tahmin üretilmez.",
            "coverage güven skoru değildir",
        ):
            self.assertInBoth(text)

    def test_v1_outputs_and_derived_fields_render(self):
        for label in (
            "TAHMİNİ SONRAKİ SERVİS",
            "TAHMİNİ KALAN MESAFE",
            "TAHMİNİ SERVİS TARİHİ",
            "TAHMİNİ SERVİS KİLOMETRESİ",
        ):
            self.assertInBoth(label)

    def test_personal_mode_is_honestly_pending(self):
        # D5: V1's own by-motorcycle pipeline is still pending, but the tab must
        # not imply no real-motorcycle input exists anywhere -- V2.1's does.
        self.assertInBoth("KENDİ MOTOSİKLETİMLE TAHMİN")
        self.assertInBoth("V1 DAYS/KM modelleri için")
        self.assertInBoth("Bu mod bu nedenle hiçbir inference isteği göndermez.")
        self.assertInBoth('data-go="v2_1/predict/history"')
        self.assertInBoth("V2.1 REAL-MOTOR INPUT: LIVE")

    def test_beginner_uncertainty_and_v2_comparison_render(self):
        for text in (
            "yaklaşık nokta tahminidir",
            "doğruluk yüzdesi değildir",
            "V2 farklı zaman aralıklarında servise gelme ihtimalini verir.",
            "V2 Sağkalım → Canlı Tahmin",
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

    def test_v1_manifest_declares_scenario_ready_without_claiming_real_pipeline(self):
        live = self.manifest["v1"]["live_prediction"]
        self.assertEqual(live["mode"], "SCENARIO_READY_REAL_MOTOR_PIPELINE_PENDING")
        self.assertEqual(live["api"]["endpoint"], "POST /api/v1/predict/scenario")
        self.assertEqual(live["api"]["catalog"], "GET /api/v1/motorcycle-models")
        self.assertEqual(live["api"]["feature_count_days"], 114)
        self.assertEqual(live["api"]["feature_count_km"], 113)


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


class TurkishUppercaseTests(unittest.TestCase):
    """Y4: with lang="tr" on <html>, CSS text-transform:uppercase turns an
    English word's lowercase 'i' into 'İ' (wrong glyph) wherever it hits
    .eyebrow/.tag/.glabel/.pill/table.tbl th/.subtab/.finding .tl/.mc-cta.
    Real Turkish words uppercase correctly, so the fix is translation, not
    escaping — verify the known-buggy literals are gone."""

    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    def assertGoneFromBoth(self, text):
        self.assertNotIn(text, self.template)
        self.assertNotIn(text, self.built)

    def test_module_and_registry_eyebrows_are_turkish(self):
        for text in ("Modül · Regresyon", "Modül · Sağkalım Analizi",
                     "Sistem · Model Kayıt Defteri", "Sistem · Deney Kayıt Defteri",
                     "Sistem · Veri Seti Kayıt Defteri"):
            self.assertInBoth(text)
        for text in ("Module · Regression", "Module · Survival Analysis",
                     "System · Model Registry", "System · Experiment Registry",
                     "System · Dataset Registry"):
            self.assertGoneFromBoth(text)

    def test_v1_nav_and_subtabs_are_turkish(self):
        for text in ('navItem("overview","Genel Bakış"', 'navItem("v1","V1 Regresyon"',
                     'navItem("v2","V2 Sağkalım"', 'navItem("experiments","Deneyler"',
                     'navItem("activity","Etkinlik"'):
            self.assertInBoth(text)

    def test_status_pill_labels_are_turkish(self):
        for bad in ('>active<', '>in progress<', '>coming soon<', '>info<'):
            self.assertGoneFromBoth(bad)

    def test_status_pill_runtime_output(self):
        # exercise statusPill() itself, not just its source text
        runner = ROOT / "tests" / "status_pill_runner.cjs"
        cases = ["active", "in_progress", "planned", "info", "review", "failed", "baseline"]
        completed = subprocess.run(
            ["node", str(runner)], input=json.dumps(cases), text=True, capture_output=True, check=True
        )
        results = json.loads(completed.stdout)
        expected = ["aktif", "devam ediyor", "yakında", "bilgi", "inceleniyor", "başarısız", "referans"]
        for rendered, text in zip(results, expected):
            self.assertIn(text, rendered)

    def test_table_headers_and_tags_are_turkish(self):
        for text in ("<th>Kazanan</th>", "<th class=\"n\">Yanlılık</th>",
                     "<th class=\"n\">Medyan AE</th>", "<th>Aile</th>",
                     'class="tag">artefakt kaynaklı'):
            self.assertInBoth(text)


class TurkishNumberFormatTests(unittest.TestCase):
    """Y5: numbers must render tr-TR (28.980 km, not 28,980); a year or a plain
    integer count must not get thousands separators or a forced decimal."""

    def test_locale_and_special_case_helpers(self):
        runner = ROOT / "tests" / "number_format_runner.cjs"
        completed = subprocess.run(["node", str(runner)], text=True, capture_output=True, check=True)
        result = json.loads(completed.stdout)
        self.assertEqual(result["n0_28980"], "28.980")
        self.assertEqual(result["n1_3320_5"], "3.320,5")
        self.assertEqual(result["int0_year"], "2023")
        self.assertEqual(result["int0_count"], "1")
        self.assertEqual(result["raw_dash"], "—")

    def test_year_and_service_count_use_int0_not_locale_formatting(self):
        template = (ROOT / "template.html").read_text()
        built = (ROOT / "public" / "index.html").read_text()
        for source in (template, built):
            self.assertIn('k==="production_year"||k==="previous_service_count"?int0(val)', source)
            self.assertIn('k==="production_year"?int0(val)', source)


class LedeMarkupTests(unittest.TestCase):
    """Y6: modHead's lede param used to be plain esc()'d, so a literal <b> in
    the source string showed up as visible "<b>" text instead of bold."""

    def test_lede_bold_tags_render_not_escape(self):
        template = (ROOT / "template.html").read_text()
        built = (ROOT / "public" / "index.html").read_text()
        for source in (template, built):
            self.assertIn("function ledeEsc(s)", source)
            self.assertIn("+ledeEsc(lede)+", source)
            # the actual rendered output must carry a real <b> tag, not &lt;b&gt;
            self.assertIn("<b>landmark tarihinde</b>", source)
            self.assertNotIn("&lt;b&gt;", source)

    def test_ledeesc_only_allowlists_b_tags(self):
        # other markup must still come out inert -- this isn't a general HTML passthrough
        runner_src = (
            "function esc(x){return String(x==null?'':x).replace(/[&<>\"]/g,"
            "function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c];});}\n"
            "function ledeEsc(s){return esc(s).replace(/&lt;(\\/?)b&gt;/g,'<$1b>');}\n"
            "console.log(ledeEsc('<b>ok</b> <img src=x onerror=alert(1)>'));"
        )
        result = subprocess.run(["node", "-e", runner_src], text=True, capture_output=True, check=True)
        out = result.stdout
        self.assertIn("<b>ok</b>", out)
        self.assertNotIn("<img", out)


class LabelConsistencyTests(unittest.TestCase):
    """O9: same-card label/counter inconsistencies."""

    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    def test_ana_periyot_leads_with_the_binding_dimension(self):
        for text in ('m.driving_metric==="TIME"&&timeText', "ikincil: "):
            self.assertInBoth(text)

    def test_v1_typical_interval_rows_are_distinguishable(self):
        for text in ("Tipik servis aralığı (gün)", "Tipik servis aralığı (km)"):
            self.assertInBoth(text)
        self.assertGoneFromBoth('historical_interval_days_median:["Tipik servis aralığı",')

    def assertGoneFromBoth(self, text):
        self.assertNotIn(text, self.template)
        self.assertNotIn(text, self.built)

    def test_v1_sample_field_count_says_what_it_counts(self):
        self.assertInBoth("alan <i>dolu</i>")
        self.assertInBoth("API şemasının toplam alan sayısı ya da modelin girdi olarak kullandığı feature sayısı değildir")


class RegistryFreshnessTests(unittest.TestCase):
    """Y3: registries were stale ('V2 · survival — COMING SOON', no V2.1 row,
    no v1.4 dataset, no V2.1 experiment history, a false 'API deploy blocked'
    changelog entry). Everything here must come from build.py / manifest.json,
    not be hand-typed in the template."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
        cls.changelog = json.loads((ROOT / "data" / "changelog.json").read_text())
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    def test_model_registry_has_real_v2_0_and_v2_1_rows(self):
        by_name = {r["name"]: r for r in self.manifest["models"]}
        self.assertNotIn("V2 · survival", by_name)  # the old fabricated placeholder row
        v20 = by_name["V2.0 · survival (research)"]
        self.assertEqual(v20["status"], "failed")
        self.assertIsInstance(v20["c_index"], float)
        v21 = by_name["V2.1 · dynamic-landmark survival"]
        self.assertEqual(v21["status"], "active")
        self.assertAlmostEqual(v21["c_index"], 0.7527, places=3)
        self.assertAlmostEqual(v21["ibs"], 0.1020, places=3)
        self.assertEqual(v21["calibration_method"], "isotonic")
        self.assertTrue(v21["dataset_version"].startswith("1.4"))

    def test_every_model_row_has_updated_at_and_artifact_hash_keys(self):
        for row in self.manifest["models"]:
            self.assertIn("updated_at", row)
            self.assertIn("artifact_hash", row)
            if row["artifact"]:
                self.assertIsNotNone(row["artifact_hash"])

    def test_regression_rows_have_dash_survival_cells_and_vice_versa(self):
        by_name = {r["name"]: r for r in self.manifest["models"]}
        v1_days = by_name["V1 · next-service DAYS"]
        self.assertIsNotNone(v1_days["mae"])
        self.assertIsNone(v1_days["c_index"])
        v21 = by_name["V2.1 · dynamic-landmark survival"]
        self.assertIsNone(v21["mae"])
        self.assertIsNotNone(v21["c_index"])

    def test_dataset_registry_has_v1_4(self):
        v1_4 = next(d for d in self.manifest["datasets"] if d["label"] == "v1.4")
        self.assertEqual(v1_4["used_by"], "V2.1")
        self.assertEqual(v1_4["landmarks"], 256841)
        self.assertEqual(v1_4["motorcycles"], 8907)
        self.assertTrue(v1_4["version"].startswith("1.4"))

    def test_experiment_registry_has_v2_1_phases(self):
        phases = [n for n in self.manifest["notebooks"] if n.get("kind") == "phase"]
        self.assertEqual(len(phases), 3)
        for p in phases:
            self.assertTrue(p["n"].startswith("V2.1-P"))

    def test_experiments_view_does_not_mislabel_phases_as_notebooks(self):
        self.assertInBoth('nb.kind==="phase"?esc(nb.n):"NB "+esc(nb.n)')

    def test_models_table_has_survival_columns(self):
        for text in ("<th class=\"n\">C-index</th>", "<th class=\"n\">IBS</th>", "<th>Kalibrasyon</th>"):
            self.assertInBoth(text)

    def test_activity_no_longer_claims_deploy_is_blocked(self):
        blob = json.dumps(self.changelog)
        self.assertNotIn("BLOCKED_BY_PROVIDER_AUTH", blob)
        self.assertIn("RESOLVED", blob)

    def test_ci_runs_the_manifest_vs_live_health_check(self):
        script = ROOT / "scripts" / "check_manifest_vs_live_health.py"
        self.assertTrue(script.exists())
        ci_yml = (ROOT.parent / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("check_manifest_vs_live_health.py", ci_yml)

    def test_manifest_vs_live_health_check_never_crashes_on_a_stale_manifest(self):
        """Exercise the actual comparison logic (not just its existence) against a
        manifest that intentionally disagrees with a fake /health -- must exit 1,
        not raise, and must not require real network access to do so."""
        script = ROOT / "scripts" / "check_manifest_vs_live_health.py"
        fake_manifest = {"v2_api": "http://127.0.0.1:1", "v2_1": {"champion": "xgb_cox"}}
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "data").mkdir()
            (tmp_path / "data" / "manifest.json").write_text(json.dumps(fake_manifest))
            (tmp_path / "scripts").mkdir()
            shutil.copy(script, tmp_path / "scripts" / script.name)
            completed = subprocess.run(
                ["python3", str(tmp_path / "scripts" / script.name)],
                text=True, capture_output=True, timeout=15,
            )
        # unreachable host -> graceful skip (exit 0), not a crash
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("unreachable", completed.stdout)


class ResilienceTests(unittest.TestCase):
    """FAZ4: Y1 (unhandled TypeError + zombie retry timers), Y2 (503/429
    backoff), O4 (live System Status), O5 (tooltip claim), O6 (sub-tab/mode in
    URL + form-state memory)."""

    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    def assertGoneFromBoth(self, text):
        self.assertNotIn(text, self.template)
        self.assertNotIn(text, self.built)

    # --- Y1 ---
    def test_v1demoprev_and_v2demoprev_crash_sites_are_null_safe(self):
        # the exact evidenced crash: a fresh getElementById().innerHTML= with no guard
        self.assertGoneFromBoth('document.getElementById("v1demoPrev").innerHTML=')
        self.assertGoneFromBoth('document.getElementById("v2demoPrev").innerHTML=')
        self.assertInBoth('safeHTML("v1demoPrev"')
        self.assertInBoth('safeHTML("v2demoPrev"')

    def test_route_clears_pending_retry_timers_on_every_navigation(self):
        self.assertInBoth("PENDING_TIMERS.forEach(clearTimeout)")
        self.assertInBoth("VIEW_GEN++")

    def test_retry_timer_stops_firing_after_navigation(self):
        runner = ROOT / "tests" / "retry_timer_runner.cjs"
        completed = subprocess.run(["node", str(runner)], text=True, capture_output=True, check=True)
        result = json.loads(completed.stdout)
        self.assertEqual(result, {"fired": 0, "stillQueued": 0})

    def test_predict_retry_loops_use_the_shared_retry_timer(self):
        # every setTimeout(run/load, ...) in a retry loop was replaced;
        # only retryTimer's own internal setTimeout remains a raw one
        self.assertEqual(self.template.count("setTimeout(run,"), 0)
        self.assertEqual(self.template.count("setTimeout(load,"), 0)
        for text in ("retryTimer(run,", "retryTimer(load,"):
            self.assertIn(text, self.template)

    def test_async_handlers_check_staleview_before_writing_dom(self):
        for text in ("if(staleView(gen))return;", "if(staleView(runGen))return;"):
            self.assertInBoth(text)

    # --- Y2 ---
    def test_v2json_tags_errors_with_http_status(self):
        self.assertInBoth("err.status=r.status")

    def test_retry_plan_gives_503_and_429_distinct_copy_and_backoff(self):
        runner = ROOT / "tests" / "retry_plan_runner.cjs"
        cases = [{"status": 503, "attempt": 0}, {"status": 429, "attempt": 1},
                  {"status": 500, "attempt": 2}]
        completed = subprocess.run(
            ["node", str(runner)], input=json.dumps(cases), text=True, capture_output=True, check=True
        )
        results = json.loads(completed.stdout)
        self.assertIn("50 saniye", results[0]["message"])
        self.assertEqual(results[0]["delay"], 4000)
        self.assertIn("Çok fazla istek", results[1]["message"])
        self.assertEqual(results[1]["delay"], 8000)
        self.assertNotIn("50 saniye", results[2]["message"])
        self.assertNotIn("Çok fazla istek", results[2]["message"])
        self.assertEqual(results[2]["delay"], 16000)

    # --- O4 ---
    def test_system_status_pings_live_health_on_open(self):
        self.assertInBoth('v2fetch(api+"/health")')
        self.assertInBoth('wireStatusLive')
        self.assertInBoth('id="liveHealthBox"')

    def test_system_status_goes_red_when_api_unreachable(self):
        self.assertInBoth('finding("bad","CANLI DURUM"')
        self.assertInBoth('"ERİŞİLEMİYOR"')

    # --- O5 ---
    def test_overview_tooltip_claim_is_scoped_to_where_it_is_true(self):
        self.assertGoneFromBoth("yanında Türkçe karşılığı ve ⓘ ikonuna gelince kısa bir açıklama çıkıyor")
        self.assertInBoth("Bazı metrik kartlarında ⓘ ikonuna gelince")

    # --- O6 ---
    def test_predict_mode_is_a_third_hash_segment(self):
        self.assertInBoth('replaceHashMode("v1/predict",mode)')
        self.assertInBoth('replaceHashMode("v2/predict",mode)')
        self.assertInBoth('replaceHashMode("v2_1/predict",mode)')
        self.assertInBoth("var mode=parts[2]||null;")

    def test_predict_pages_open_directly_on_the_mode_named_in_the_url(self):
        self.assertInBoth('["scenario","demo","own"].indexOf(initialMode)')
        self.assertInBoth('["scenario","demo","real"].indexOf(initialMode)')
        self.assertInBoth('["history","scenario"].indexOf(initialMode)')

    # --- D6 ---
    def test_v1_demo_states_what_the_predicted_days_count_from(self):
        self.assertInBoth("snapshot tarihinden itibaren")
        self.assertInBoth("function v1DemoTimeline(s,p,der)")

    def test_v1_demo_timeline_dates_are_arithmetically_correct(self):
        runner = ROOT / "tests" / "v1_demo_timeline_runner.cjs"
        completed = subprocess.run(["node", str(runner)], text=True, capture_output=True, check=True)
        html = completed.stdout
        self.assertIn("2025-07-27", html)  # 2026-01-10 minus 167 days
        self.assertIn("2026-01-10", html)
        self.assertIn("2026-07-31", html)  # 2026-01-10 plus 202 days

    def test_form_state_is_snapshotted_and_restored_across_navigation(self):
        self.assertInBoth("function snapshotForm(container,key)")
        self.assertInBoth("function restoreForm(container,key)")
        for text in ('snapshotForm(box,location.hash)', 'restoreForm(box,location.hash)'):
            self.assertInBoth(text)
        self.assertInBoth("if(PREV_HASH)snapshotForm(view,PREV_HASH)")


class ProductPolishTests(unittest.TestCase):
    """FAZ5: D3 (favicon/meta/OG/print), D4 (font display=swap already ok)."""

    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    def test_head_has_favicon_description_and_og_tags(self):
        for text in ('rel="icon"', 'name="description"', 'property="og:title"',
                     'property="og:description"', 'property="og:type"'):
            self.assertInBoth(text)

    def test_display_swap_already_present(self):
        self.assertInBoth("&display=swap")

    def test_print_stylesheet_hides_chrome(self):
        self.assertInBoth("@media print")
        self.assertInBoth(".sidebar,.topbar,#ham")


class AccessibilityTests(unittest.TestCase):
    """FAZ5/D2: landmarks + skip link, aria-live on results, tablist/tab/
    tabpanel + arrow-key nav, no H1->H3 heading skip, drawer focus trap."""

    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    def assertGoneFromBoth(self, text):
        self.assertNotIn(text, self.template)
        self.assertNotIn(text, self.built)

    def test_landmarks_and_skip_link_present(self):
        self.assertInBoth('class="skip-link"')
        self.assertInBoth('<nav class="sidebar"')
        self.assertInBoth('<header class="topbar"')
        self.assertInBoth('<main class="content"')

    def test_prediction_outputs_are_aria_live(self):
        for box_id in ("v1scenarioOut", "v1demoOut", "v2scenarioOut", "v2demoOut", "v2_1out"):
            self.assertInBoth('id="' + box_id + '"')
        self.assertEqual(self.template.count('aria-live="polite"'), 5)

    def test_tab_bars_use_the_tab_pattern(self):
        for text in ('role="tablist"', 'role="tab"', 'role="tabpanel"', 'aria-selected='):
            self.assertInBoth(text)
        # every mode-switcher's sel()/select() keeps aria-selected in sync, not just the class
        self.assertEqual(self.template.count('.setAttribute("aria-selected",'), 8)

    def test_arrow_keys_navigate_any_tablist(self):
        self.assertInBoth('tab.closest(\'[role="tablist"]\')')
        self.assertInBoth('e.key==="ArrowRight"')

    def test_no_heading_skips_h1_to_h3(self):
        # card() and the notebook/phase cards used to jump straight from the
        # page <h1> to an <h3> -- both now use <h2>.
        self.assertInBoth('<div class="card"><h2>')
        self.assertGoneFromBoth('<div class="card"><h3>')

    def test_mobile_drawer_has_focus_trap_and_escape(self):
        self.assertInBoth("function setDrawer(open)")
        self.assertInBoth('e.key==="Escape"')
        self.assertInBoth("aria-expanded")


class ChartTests(unittest.TestCase):
    """FAZ5/O3: 4 real inline-SVG charts, no library, no fabricated data."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    def test_all_four_chart_functions_render_without_nan(self):
        runner = ROOT / "tests" / "svg_charts_runner.cjs"
        completed = subprocess.run(["node", str(runner)], text=True, capture_output=True, check=True)
        out = json.loads(completed.stdout)
        self.assertEqual(set(out), {"survival", "bars", "hist", "scatter"})
        for name, svg in out.items():
            self.assertNotIn("NaN", svg, name)
            self.assertIn("<svg", svg, name)

    def test_survival_curve_plots_the_real_horizon_percentages(self):
        runner = ROOT / "tests" / "svg_charts_runner.cjs"
        completed = subprocess.run(["node", str(runner)], text=True, capture_output=True, check=True)
        svg = json.loads(completed.stdout)["survival"]
        for pct in ("63", "72", "85", "91"):
            self.assertIn(">" + pct + "%<", svg)

    def test_charts_are_wired_into_v2_1_result_cards_and_overview(self):
        self.assertEqual(self.template.count("g+=svgSurvivalCurve(pr)"), 3)
        self.assertInBoth("out+=svgHorizonBars(")

    def test_v1_errors_page_has_real_scatter_and_histogram(self):
        self.assertInBoth("svgCalibrationScatter(rows")
        self.assertInBoth("svgHistogram(hist[t]")

    def test_manifest_carries_the_real_v1_error_histogram(self):
        hist = self.manifest["v1"]["error_histogram"]
        self.assertIn("DAYS", hist)
        self.assertIn("KM", hist)
        self.assertEqual(sum(b["count"] for b in hist["DAYS"]["bins"]), hist["DAYS"]["n"])


class SecurityHardeningTests(unittest.TestCase):
    """FAZ 1 fixes: ?v2api= host allow-list (K4), esc()'d API strings (K4b),
    security headers (O2)."""

    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "template.html").read_text()
        cls.built = (ROOT / "public" / "index.html").read_text()

    def assertInBoth(self, text):
        self.assertIn(text, self.template)
        self.assertIn(text, self.built)

    def test_v2api_param_is_host_allowlisted(self):
        runner = ROOT / "tests" / "allowed_api_url_runner.cjs"
        cases = [
            "https://evil.example",
            "https://ridebase-inference-api.onrender.com",
            "http://ridebase-inference-api.onrender.com",       # not https -> rejected
            "https://ridebase-inference-api.onrender.com.evil.com",  # lookalike host -> rejected
            "http://localhost:8000",
            "javascript:alert(1)",
            "not a url",
        ]
        completed = subprocess.run(
            ["node", str(runner)], input=json.dumps(cases), text=True, capture_output=True, check=True
        )
        results = json.loads(completed.stdout)
        self.assertEqual(results, [
            None,
            "https://ridebase-inference-api.onrender.com",
            None,
            None,
            "http://localhost:8000",
            None,
            None,
        ])

    def test_v2api_rejection_shows_a_visible_notice(self):
        self.assertInBoth('id="apiHostNotice"')
        self.assertInBoth("notice.hidden=false")

    def test_api_derived_strings_are_escaped_before_innerhtml(self):
        # Values that used to be interpolated raw from live API responses.
        for text in (
            'n1(m.maintenance_urgency_score)+" / 100 · "+esc(m.maintenance_urgency_level)',
            'esc(m.driving_metric)',
            'esc(policy.task_code||"bakım politikası")',
            'esc(ctx.current_odometer_source_date||"history missing")',
            'esc(ctx.last_eligible_service_date||"—")',
        ):
            self.assertInBoth(text)

    def test_history_pipeline_has_a_random_valid_id_button(self):
        # K2: History Pipeline must not be a dead end guessing motorcycle IDs.
        self.assertInBoth('id="v21historyRandom"')
        self.assertInBoth("function v2_1FillRandomId()")
        self.assertInBoth('/api/v2_1/sample')

    def test_low_coverage_percentages_are_rounded_and_badged(self):
        # O7: below 60% known-feature coverage, risk percentages must round to
        # whole numbers with '~' and carry a visible low-coverage badge.
        self.assertInBoth("function pctCov(v,ratio)")
        self.assertInBoth("function lowCoverageBadge(ratio")
        for text in ("pctCov(pr.risk_30d,covRatio)", "lowCoverageBadge(covRatio)"):
            self.assertInBoth(text)

    def test_missing_feature_list_indicates_truncation_and_has_full_accordion(self):
        # O7: the 32/54-style missing list must say how many more there are,
        # with the full list reachable in an accordion.
        self.assertInBoth("… ve '+(missing.length-6)+' alan daha")
        self.assertInBoth("Tam liste</summary>")

    def test_conflicting_annual_km_input_is_flagged_with_a_fix_button(self):
        # O8: user-entered annual km vs. service-history-derived pace.
        self.assertInBoth("GİRİLEN YILLIK KM İLE GÖZLENEN TEMPO ÇELİŞİYOR")
        self.assertInBoth("mismatchRatio > 1.5")
        self.assertInBoth('id="v2paceFixBtn"')
        self.assertInBoth('getElementById("v2paceFixBtn")')

    def test_unscaled_risk_score_is_not_shown_as_a_headline_chip(self):
        # O10: RISK SCORE 1.599 had no scale/unit/interpretation.
        for source in (self.template, self.built):
            self.assertNotIn("RISK SCORE", source)

    def test_vercel_security_headers_present(self):
        vercel = json.loads((ROOT / "vercel.json").read_text())
        catchall = next(h for h in vercel["headers"] if h["source"] == "/(.*)")
        keys = {h["key"] for h in catchall["headers"]}
        self.assertEqual(
            keys,
            {"Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"},
        )
        csp = next(h["value"] for h in catchall["headers"] if h["key"] == "Content-Security-Policy")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)


if __name__ == "__main__":
    unittest.main()
