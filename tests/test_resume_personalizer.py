import unittest

from app.resume_personalizer import personalize_resume


class ResumePersonalizerTruthfulnessTests(unittest.TestCase):
    def test_summary_never_invents_tenure_or_skills_from_the_vacancy(self):
        profile = {
            "summary": "Analista com experiência em recrutamento e seleção.",
            "experience_texts": ["Recrutamento e seleção."],
            "experiences": [{
                "role": "Analista de RH",
                "company": "Empresa A",
                "description": "Recrutamento e seleção.",
            }],
            "skills": ["Excel"],
        }
        result = personalize_resume(
            "Analista de RH",
            "A vaga pede treinamento e desenvolvimento, gestão de equipes e Power BI.",
            profile,
        )
        self.assertIn(profile["summary"], result["tailored_summary"])
        self.assertNotIn("10 anos", result["tailored_summary"])
        self.assertNotIn("Power BI", result["tailored_summary"])
        self.assertNotIn("Treinamento e Desenvolvimento", result["tailored_summary"])
        self.assertEqual(result["prioritized_skills"], [])

    def test_summary_can_surface_only_experience_and_skills_present_in_profile(self):
        profile = {
            "summary": "Profissional de RH.",
            "experience_texts": ["Recrutamento e seleção com Excel."],
            "experiences": [{
                "role": "Analista de RH",
                "company": "Empresa A",
                "description": "Recrutamento e seleção com Excel.",
            }],
            "skills": ["Excel"],
        }
        result = personalize_resume("Analista de RH", "Recrutamento e seleção e Excel.", profile)
        self.assertIn("Profissional de RH.", result["tailored_summary"])
        self.assertIn("Recrutamento e Seleção", result["tailored_summary"])
        self.assertIn("Excel", result["tailored_summary"])


if __name__ == "__main__":
    unittest.main()
