import unittest

from app.job_intake import parse_job_text
from app.job_quality import (
    assess_job_capture,
    is_grouped_job_summary,
    is_probable_job_url,
    job_source_from_url,
    split_job_alert,
)


# All inline job/email content in this module is synthetic test data, not a
# sample collected from a provider.
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

    def test_recognizes_provider_specific_job_urls(self):
        self.assertTrue(is_probable_job_url("https://www.glassdoor.com.br/partner/jobListing.htm?pos=1"))
        self.assertTrue(is_probable_job_url("https://www.jobbol.com.br/cargos/analista-administrativo"))
        self.assertTrue(is_probable_job_url("https://www.linkedin.com/jobs/view/123"))
        self.assertTrue(is_probable_job_url("https://br.indeed.com/rc/clk?jk=abc123"))
        self.assertTrue(is_probable_job_url("https://empresa.gupy.io/jobs/123"))
        self.assertTrue(is_probable_job_url("https://empresa.test/carreiras/jobs/123"))
        self.assertFalse(is_probable_job_url("https://www.linkedin.com/jobs/collections/recommended/"))
        self.assertFalse(is_probable_job_url("https://linkedin.com@evil.test/jobs/view/123"))

    def test_attributes_only_valid_provider_hosts(self):
        self.assertEqual(job_source_from_url("https://www.linkedin.com/jobs/view/123"), "linkedin")
        self.assertEqual(job_source_from_url("https://br.indeed.com/rc/clk?jk=123"), "indeed")
        self.assertEqual(job_source_from_url("https://empresa.gupy.io/jobs/123"), "gupy")
        self.assertEqual(job_source_from_url("https://glassdoor.com.br/partner/jobListing.htm"), "glassdoor")
        self.assertEqual(job_source_from_url("https://www.jobbol.com.br/cargos/analista"), "jobbol")
        self.assertIsNone(job_source_from_url("https://linkedin.com.evil.test/jobs/view/123"))
        self.assertIsNone(job_source_from_url("https://linkedin.com@evil.test/jobs/view/123"))

    def test_marks_multi_vacancy_summary_without_individual_cards(self):
        content = "27 vagas abertas de coordenador de recursos humanos - Brasil\nVeja as oportunidades no portal."
        self.assertTrue(is_grouped_job_summary("Novas vagas para você", content))
        self.assertFalse(is_grouped_job_summary("1 vaga aberta", "Analista de RH\nEmpresa Alpha"))

    def test_splits_synthetic_individual_cards_without_job_links(self):
        content = """Resumo de oportunidades
Analista de Recursos Humanos
Empresa Alpha
Salvador/BA
Responsabilidades: conduzir recrutamento e seleção e acompanhar indicadores.
Requisitos: experiência com entrevistas, folha de pagamento e comunicação com equipes.
Coordenador de Departamento Pessoal
Empresa Beta
Recife/PE
Responsabilidades: liderar folha de pagamento, benefícios e rotina trabalhista.
Requisitos: experiência com legislação, sistemas e gestão de pessoas.
"""
        blocks = split_job_alert("Duas oportunidades", content)
        self.assertEqual(len(blocks), 2)
        self.assertIn("Analista de Recursos Humanos", blocks[0])
        self.assertNotIn("Coordenador de Departamento Pessoal", blocks[0])
        self.assertIn("Coordenador de Departamento Pessoal", blocks[1])

    def test_role_mentioned_inside_prose_does_not_create_a_fake_card(self):
        content = """Resumo profissional
Responsabilidades: apoiar analistas de RH e coordenadores em processos internos.
Requisitos: experiência com recrutamento, seleção e comunicação com equipes.
"""
        blocks = split_job_alert("Oportunidade de RH", content)
        self.assertEqual(len(blocks), 1)
        self.assertIn("Responsabilidades", blocks[0])

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

    def test_nonfraud_suspicious_health_band_requires_review_not_discard(self):
        quality = assess_job_capture({
            "title": "Banco de talentos",
            "company": "Empresa confidencial",
            "description": "",
            "salary": "",
            "url": "",
        })

        self.assertEqual(quality["health"]["band"], "SUSPEITA")
        self.assertFalse(quality["health"]["fraud_suspected"])
        self.assertEqual(quality["decision"], "REVISAR")

    def test_cleans_tracking_parameters_from_all_8_portals(self):
        from app.job_intake import clean_tracking_url
        linkedin = "https://br.linkedin.com/jobs/view/4123456789/?trk=eml-email_job_alert-job_card-0-job_title&eType=EMAIL_JOB_ALERT&refId=abc"
        self.assertEqual(clean_tracking_url(linkedin), "https://br.linkedin.com/jobs/view/4123456789")

        indeed = "https://br.indeed.com/rc/clk?jk=1234567890abcdef&from=vj&pos=top&cmp=Company"
        self.assertEqual(clean_tracking_url(indeed), "https://br.indeed.com/rc/clk?jk=1234567890abcdef&pos=top")

        gupy = "https://empresa.gupy.io/jobs/1234567?jobBoardSource=gupy_portal&utm_source=gupy"
        self.assertEqual(clean_tracking_url(gupy), "https://empresa.gupy.io/jobs/1234567")

        catho = "https://www.catho.com.br/vagas/analista-de-rh/12345/?utm_source=email&utm_campaign=alert"
        self.assertEqual(clean_tracking_url(catho), "https://www.catho.com.br/vagas/analista-de-rh/12345")

        infojobs = "https://www.infojobs.com.br/vaga-de-analista__12345.aspx?utm_medium=email"
        self.assertEqual(clean_tracking_url(infojobs), "https://www.infojobs.com.br/vaga-de-analista__12345.aspx")

    def test_recognizes_all_8_portal_sources(self):
        self.assertEqual(job_source_from_url("https://www.linkedin.com/jobs/view/123"), "linkedin")
        self.assertEqual(job_source_from_url("https://br.indeed.com/rc/clk?jk=123"), "indeed")
        self.assertEqual(job_source_from_url("https://empresa.gupy.io/jobs/123"), "gupy")
        self.assertEqual(job_source_from_url("https://www.vagas.com.br/vagas/v123"), "vagas.com")
        self.assertEqual(job_source_from_url("https://www.infojobs.com.br/vagas/123"), "infojobs")
        self.assertEqual(job_source_from_url("https://www.catho.com.br/vagas/123"), "catho")
        self.assertEqual(job_source_from_url("https://www.empregos.com.br/vagas/123"), "empregos")
        self.assertEqual(job_source_from_url("https://vagas.solides.com.br/vaga/123"), "solides")


if __name__ == "__main__":
    unittest.main()

