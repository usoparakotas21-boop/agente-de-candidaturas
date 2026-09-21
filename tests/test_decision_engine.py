import unittest

from app.decision_engine import HEURISTICS_VERSION, decide_opportunity, normalize_preferences


JOB = {
    "title": "Coordenador de Recursos Humanos",
    "company": "Empresa Alpha",
    "location": "Salvador/BA",
    "modality": "Hibrido",
    "description": "Gestao de RH, recrutamento, indicadores e Power BI.",
}


class DecisionEngineTest(unittest.TestCase):
    def test_defaults_to_review_with_automation_disabled(self):
        result = decide_opportunity(JOB, {"score": 91}, normalize_preferences({}))
        self.assertEqual(result["decision"], "REVISAR")
        self.assertIn("automacao desativada pelo usuario", result["reasons"])
        self.assertEqual(result["heuristics_version"], HEURISTICS_VERSION)
        self.assertEqual(result["heuristics_version"], "br-rh-2")
        self.assertIn("AUTOMATION_DISABLED", result["reason_codes"])

    def test_marks_high_score_match_as_automatic_when_authorized(self):
        preferences = normalize_preferences(
            {
                "target_roles": ["Coordenador de Recursos Humanos"],
                "locations": ["Salvador/BA"],
                "modalities": ["Hibrido"],
                "allow_automatic": True,
                "automatic_score": 85,
            }
        )
        result = decide_opportunity(JOB, {"score": 91}, preferences, capture_confidence=90)
        self.assertEqual(result["decision"], "AUTOMATICA")
        self.assertEqual(result["reason_codes"], ["AUTOMATIC_SCORE_REACHED"])

    def test_discards_excluded_company(self):
        result = decide_opportunity(
            JOB,
            {"score": 95},
            normalize_preferences({"excluded_companies": ["Empresa Alpha"]}),
        )
        self.assertEqual(result["decision"], "DESCARTAR")

    def test_discards_score_below_minimum(self):
        result = decide_opportunity(
            JOB,
            {"score": 49},
            normalize_preferences({"minimum_score": 65}),
        )
        self.assertEqual(result["decision"], "DESCARTAR")

    def test_reviews_location_mismatch(self):
        result = decide_opportunity(
            JOB,
            {"score": 90},
            normalize_preferences(
                {"locations": ["Recife/PE"], "allow_automatic": True}
            ),
            capture_confidence=90,
        )
        self.assertEqual(result["decision"], "REVISAR")
        self.assertIn("localizacao fora das preferencias", result["reasons"])

    def test_uses_structured_salary_bounds_before_raw_text(self):
        job = {**JOB, "salary": "R$ 8.000 a R$ 10.000", "salary_min": 8000, "salary_max": 10000}
        result = decide_opportunity(
            job,
            {"score": 90},
            normalize_preferences({"salary_min": 12000}),
        )
        self.assertIn("faixa salarial abaixo da preferência", result["reasons"])
        self.assertIn("SALARY_BELOW_PREFERENCE", result["reason_codes"])

    def test_unknown_fields_matching_saved_preferences_require_review(self):
        preferences = normalize_preferences(
            {
                "modalities": ["Remoto"],
                "locations": ["Salvador/BA"],
                "contract_types": ["CLT"],
                "schedules": ["Comercial"],
                "industries": ["Saúde"],
                "salary_min": 5000,
                "allow_automatic": True,
                "automatic_score": 85,
            }
        )
        incomplete_job = {
            "title": JOB["title"],
            "company": JOB["company"],
            "description": JOB["description"],
            "location": "",
            "modality": "",
            "contract_type": "",
        }
        result = decide_opportunity(
            incomplete_job,
            {"score": 95},
            preferences,
            capture_confidence=95,
        )
        self.assertEqual(result["decision"], "REVISAR")
        self.assertTrue(
            {
                "MODALITY_UNVERIFIED",
                "LOCATION_UNVERIFIED",
                "CONTRACT_TYPE_UNVERIFIED",
                "SCHEDULE_UNVERIFIED",
                "INDUSTRY_UNVERIFIED",
                "SALARY_UNVERIFIED",
            }.issubset(result["reason_codes"])
        )

    def test_contract_synonyms_match_without_inferring_a_new_contract(self):
        result = decide_opportunity(
            {**JOB, "contract_type": "PJ"},
            {"score": 91},
            normalize_preferences(
                {
                    "contract_types": ["Pessoa Jurídica"],
                    "allow_automatic": True,
                    "automatic_score": 85,
                }
            ),
            capture_confidence=90,
        )
        self.assertEqual(result["decision"], "AUTOMATICA")

    def test_keyword_matching_uses_word_boundaries(self):
        result = decide_opportunity(
            {**JOB, "title": "Estagiário Administrativo"},
            {"score": 91},
            normalize_preferences(
                {
                    "required_keywords": ["TI"],
                    "allow_automatic": True,
                    "automatic_score": 85,
                }
            ),
            capture_confidence=90,
        )
        self.assertEqual(result["decision"], "DESCARTAR")
        self.assertIn("REQUIRED_KEYWORD_MISSING", result["reason_codes"])

    def test_notification_preferences_are_normalized_for_lifecycle_emails(self):
        preferences = normalize_preferences(
            {
                "notification_frequency": "immediate",
                "notify_interviews": False,
                "notify_expiring": True,
                "notify_followups": False,
            }
        )
        self.assertEqual(preferences["notification_frequency"], "immediate")
        self.assertFalse(preferences["notify_interviews"])
        self.assertTrue(preferences["notify_expiring"])
        self.assertFalse(preferences["notify_followups"])
        self.assertEqual(
            normalize_preferences({"notification_frequency": "unknown"})["notification_frequency"],
            "daily",
        )


if __name__ == "__main__":
    unittest.main()
