import unittest

from app.job_source_fetcher import (
    extract_job_posting_html,
    infer_from_public_url,
)


class JobSourceFetcherTest(unittest.TestCase):
    def test_extracts_jobposting_jsonld(self):
        page = """
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Coordenador de Recursos Humanos Generalista",
          "hiringOrganization": {"@type": "Organization", "name": "Canil Palazzo"},
          "jobLocation": {"address": {
            "addressLocality": "Lauro de Freitas",
            "addressRegion": "BA",
            "addressCountry": "BR"
          }},
          "description": "<p>Responsavel pela area de Recursos Humanos.</p><p>Atuacao com recrutamento, indicadores, gestao de pessoas, treinamento e legislacao trabalhista.</p>"
        }
        </script>
        """
        result = extract_job_posting_html(page, "https://example.com/jobs/1")
        self.assertEqual(result["company"], "Canil Palazzo")
        self.assertEqual(result["title"], "Coordenador de Recursos Humanos Generalista")
        self.assertIn("Lauro de Freitas", result["location"])

    def test_infers_bebee_company_from_public_url(self):
        result = infer_from_public_url(
            {
                "title": "Coordenador de Recursos Humanos",
                "company": "Descricao da vaga",
                "location": "Lauro de Freitas, Brasil",
                "modality": "Presencial",
                "salary": "",
                "url": (
                    "https://bebee.com/br/jobs/coordenador-de-recursos-humanos-"
                    "generalista-canil-palazzo-lauro-de-freitas-ba--theirstack-735646466"
                ),
                "description": "Descricao completa da oportunidade " * 20,
            }
        )
        self.assertEqual(result["company"], "Canil Palazzo")
        self.assertEqual(
            result["title"],
            "Coordenador de Recursos Humanos Generalista",
        )
        self.assertGreaterEqual(result["confidence"], 85)


if __name__ == "__main__":
    unittest.main()
