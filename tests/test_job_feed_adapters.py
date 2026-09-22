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


if __name__ == "__main__":
    unittest.main()
