import unittest

from app.job_intake import parse_job_text


SAMPLE = """
Empresa: Exemplo Tecnologia
Cargo: Coordenador de Recursos Humanos
Localização: Salvador/BA
Modalidade: Híbrido
Salário: R$ 8.000,00 a R$ 10.000,00
Buscamos profissional com experiência em recrutamento, folha de pagamento,
gestão de equipes, indicadores, Power BI e relações trabalhistas.
Candidate-se: https://exemplo.gupy.io/jobs/12345
"""


class JobIntakeParserTest(unittest.TestCase):
    def test_extracts_public_url_without_scheme(self):
        result = parse_job_text(
            "Coordenador de Recursos Humanos\n"
            "Canil Palazzo\n"
            "Lauro de Freitas, Brasil\n"
            "Descricao completa da oportunidade com requisitos e responsabilidades.\n"
            "bebee.com/br/jobs/coordenador-de-recursos-humanos-canil-palazzo-lauro-de-freitas-ba"
        )
        self.assertTrue(result["url"].startswith("https://bebee.com/"))
        self.assertEqual(result["location"], "Lauro de Freitas, Brasil")

    def test_company_is_read_after_title_and_navigation_is_ignored(self):
        result = parse_job_text(
            "Entra\n"
            "Coordenador de Recursos Humanos Generalista\n"
            "Canil Palazzo\n"
            "Lauro de Freitas/BA\n"
            "Buscamos profissional com experiencia em Recursos Humanos, "
            "gestao de pessoas, indicadores, recrutamento e selecao."
        )
        self.assertEqual(result["company"], "Canil Palazzo")

    def test_wrapped_title_is_joined_before_company_detection(self):
        result = parse_job_text(
            "Entra\n"
            "Coordenador de Recursos Humanos\n"
            "Generalista\n"
            "Canil Palazzo\n"
            "Lauro de Freitas/BA\n"
            "Buscamos profissional com experiencia em Recursos Humanos, "
            "gestao de pessoas, indicadores, recrutamento e selecao."
        )
        self.assertEqual(
            result["title"],
            "Coordenador de Recursos Humanos Generalista",
        )
        self.assertEqual(result["company"], "Canil Palazzo")

    def test_section_heading_is_not_used_as_company(self):
        result = parse_job_text(
            "Coordenador de Recursos Humanos\n"
            "Generalista\n"
            "Descricao da vaga\n"
            "Canil Palazzo\n"
            "Lauro de Freitas/BA\n"
            "Buscamos profissional com experiencia em Recursos Humanos, "
            "gestao de pessoas, indicadores, recrutamento e selecao."
        )
        self.assertEqual(result["company"], "Canil Palazzo")

    def test_extracts_labeled_job(self):
        result = parse_job_text(SAMPLE, "gupy")
        self.assertEqual(result["company"], "Exemplo Tecnologia")
        self.assertEqual(result["title"], "Coordenador de Recursos Humanos")
        self.assertEqual(result["location"], "Salvador/BA")
        self.assertEqual(result["modality"], "Hibrido")
        self.assertEqual(result["url"], "https://exemplo.gupy.io/jobs/12345")
        self.assertTrue(result["external_id"].startswith("intake-"))

    def test_fingerprint_is_stable(self):
        first = parse_job_text(SAMPLE, "email")
        second = parse_job_text(SAMPLE, "linkedin")
        self.assertEqual(first["external_id"], second["external_id"])

    def test_rejects_short_text(self):
        with self.assertRaises(ValueError):
            parse_job_text("Vaga de RH")


if __name__ == "__main__":
    unittest.main()
