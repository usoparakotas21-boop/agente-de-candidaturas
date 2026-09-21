import math
import unittest
from pathlib import Path

from app.main import _score_percent

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


class ScorePercentTests(unittest.TestCase):
    def test_score_percent_is_bounded_to_the_display_domain(self):
        self.assertEqual(_score_percent(-86), 0)
        self.assertEqual(_score_percent(142), 100)
        self.assertEqual(_score_percent(76.4), 76)

    def test_invalid_scores_are_not_exposed_as_percentages(self):
        for value in (None, "not-a-score", math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                self.assertIsNone(_score_percent(value))

    def test_vacancy_match_badges_use_semantic_score_bands(self):
        script = (STATIC / "jobs-enhance.js").read_text(encoding="utf-8")
        page = (STATIC / "vagas.html").read_text(encoding="utf-8")
        self.assertIn("rounded>=75?'match-badge-positive'", script)
        self.assertIn("rounded>=50?'match-badge-attention'", script)
        self.assertIn("match-badge-low", page)
        self.assertIn("match-badge-attention", page)
        self.assertIn("span+span:not(.match-badge):before", page)
        main = (STATIC.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn("/static/jobs-enhance.js?v=2", main)


if __name__ == "__main__":
    unittest.main()
