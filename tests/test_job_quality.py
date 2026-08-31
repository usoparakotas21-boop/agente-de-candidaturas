import unittest

from app.job_intake import parse_job_text
from app.job_quality import assess_job_capture, split_job_alert


class JobQualityTest(unittest.TestCase):
    def test_splits_summary_email_by_job_urls(self):
        content = """
        Vagas recomendadas para voce
        Analista de Recursos Humanos
        Empresa Alpha
        Salvador/BA
        Requisitos: recrutamento, selecao e indicadores de RH.
        https://example.com/jobs/101
        Coordenador de Departamento Pessoal
        Empresa Beta
        Recife/PE
        Responsabilidades: folha de pagamento, beneficios e gestao de equipe.
        https://example.com/jobs/202
        """

        blocks = split_job_alert("2 novas vagas", content)

        self.assertEqual(len(blocks), 2)
        self.assertIn("Analista de Recursos Humanos", blocks[0])
        self.assertIn("/jobs/101", blocks[0])
        self.assertNotIn("/jobs/202", blocks[0])
        self.assertIn("Coordenador de Departamento Pessoal", blocks[1])

    def test_keeps_single_job_content_intact(self):
        content = (
            "Coordenador de RH\nEmpresa Alpha\nSalvador/BA\n"
            "Descricao completa com requisitos, responsabilidades e beneficios.\n"
            "https://example.com/jobs/101"
        )
        self.assertEqual(split_job_alert("Nova vaga", content), [content])

    def test_uses_specific_subject_when_body_has_no_title(self):
        content = (
            "Empresa: Empresa Alpha\nLocal: Salvador/BA\n"
            "Requisitos e responsabilidades detalhados para esta oportunidade.\n"
            "https://example.com/jobs/101"
        )
        block = split_job_alert("Analista de Recursos Humanos", content)[0]
        self.assertTrue(block.startswith("Analista de Recursos Humanos\n"))

    def test_recognizes_indeed_tracking_job_url(self):
        content = (
            "Analista de RH\nEmpresa Alpha\nSalvador/BA\n"
            "Requisitos e responsabilidades da oportunidade profissional.\n"
            "https://br.indeed.com/rc/clk?jk=abc123"
        )
        self.assertEqual(len(split_job_alert("Nova vaga", content)), 1)

    def test_approves_complete_capture(self):
        parsed = parse_job_text(
            "Cargo: Coordenador de Recursos Humanos\n"
            "Empresa: Empresa Alpha\nLocal: Salvador/BA\n"
            "Responsabilidades: liderar recrutamento e selecao, folha de pagamento, "
            "beneficios, indicadores e gestao de equipe. Requisitos: experiencia em "
            "Recursos Humanos, legislacao trabalhista e Power BI. A empresa oferece "
            "beneficios e oportunidades de desenvolvimento profissional.\n"
            "https://example.com/jobs/101"
        )
        quality = assess_job_capture(parsed)
        self.assertEqual(quality["decision"], "CAPTURAR")
        self.assertGreaterEqual(quality["confidence"], 72)

    def test_discards_generic_navigation_capture(self):
        quality = assess_job_capture(
            {
                "title": "Mais vagas",
                "company": "LinkedIn",
                "description": "Veja mais vagas e atualize suas preferencias.",
                "url": "https://linkedin.com/help",
            }
        )
        self.assertEqual(quality["decision"], "DESCARTAR")
        self.assertIn("cargo com baixa confianca", quality["reasons"])


if __name__ == "__main__":
    unittest.main()
