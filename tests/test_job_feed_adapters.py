import unittest

from app.job_feed_adapters import adapt_feed_records


class JobFeedAdapterTests(unittest.TestCase):
    def test_lever_payload_is_flattened_without_network_access(self):
        records = adapt_feed_records(
            "lever-postings",
            [
                {
                    "id": "lever-1",
                    "text": "Analista de Pessoas",
                    "categories": {"location": "Salvador/BA", "commitment": "full-time"},
                    "descriptionPlain": "Atuação remota.",
                    "hostedUrl": "https://jobs.example.com/lever-1",
                }
            ],
        )
        self.assertEqual(
            records[0],
            {
                "external_id": "lever-1",
                "title": "Analista de Pessoas",
                "company": "",
                "location": "Salvador/BA",
                "description": "Atuação remota.",
                "apply_url": "https://jobs.example.com/lever-1",
                "salary_range": "",
                "work_mode": "",
                "contract_type": "full-time",
            },
        )

    def test_greenhouse_payload_uses_nested_location_and_absolute_url(self):
        records = adapt_feed_records(
            "greenhouse-job-board",
            [
                {
                    "id": 42,
                    "title": "People Partner",
                    "location": {"name": "Remoto"},
                    "content": "Descrição da vaga.",
                    "absolute_url": "https://boards.example.com/jobs/42",
                }
            ],
        )
        self.assertEqual(records[0]["external_id"], "42")
        self.assertEqual(records[0]["location"], "Remoto")
        self.assertEqual(records[0]["apply_url"], "https://boards.example.com/jobs/42")

    def test_unknown_source_is_left_unchanged(self):
        original = [{"title": "Vaga", "apply_url": "https://jobs.example.com/1"}]
        adapted = adapt_feed_records("authorized-custom-feed", original)
        self.assertEqual(adapted, original)
        self.assertIsNot(adapted, original)

    def test_adzuna_flattens_nested_company_location_and_salary(self):
        records = adapt_feed_records(
            "adzuna-api",
            [
                {
                    "id": "a-123",
                    "title": "Analista de dados",
                    "company": {"display_name": "Empresa A"},
                    "location": {"display_name": "Salvador, BA"},
                    "description": "Analise indicadores.",
                    "redirect_url": "https://jobs.example.com/a-123",
                    "salary_min": 5000,
                    "salary_max": 7000,
                }
            ],
        )
        self.assertEqual(records[0]["external_id"], "a-123")
        self.assertEqual(records[0]["company"], "Empresa A")
        self.assertEqual(records[0]["location"], "Salvador, BA")
        self.assertEqual(records[0]["salary_range"], "5000 - 7000")

    def test_jooble_maps_snippet_and_link_without_network(self):
        records = adapt_feed_records(
            "jooble",
            [
                {
                    "job_id": "j-123",
                    "title": "Pessoa recrutadora",
                    "company": "Empresa B",
                    "location": "Remoto",
                    "snippet": "Conduza entrevistas.",
                    "link": "https://jobs.example.com/j-123",
                    "salary": "R$ 4.000",
                    "type": "CLT",
                }
            ],
        )
        self.assertEqual(records[0]["external_id"], "j-123")
        self.assertEqual(records[0]["description"], "Conduza entrevistas.")
        self.assertEqual(records[0]["apply_url"], "https://jobs.example.com/j-123")
        self.assertEqual(records[0]["contract_type"], "CLT")


if __name__ == "__main__":
    unittest.main()
