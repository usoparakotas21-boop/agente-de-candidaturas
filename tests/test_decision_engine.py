import unittest

from app.decision_engine import decide_opportunity, normalize_preferences


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


if __name__ == "__main__":
    unittest.main()
