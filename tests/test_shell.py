import unittest
from pathlib import Path

from app import main as main_module


class ShellLayoutTest(unittest.TestCase):
    def test_dashboard_keeps_its_own_header_without_global_duplicate(self):
        response = main_module._page(Path(main_module.DASHBOARD_PATH))
        html = response.body.decode("utf-8")
        self.assertEqual(html.count('<nav class="global-nav">'), 0)
        self.assertIn('<header class="topbar">', html)
        self.assertIn('id="userEmail"', html)

    def test_subpages_keep_the_single_global_navigation_shell(self):
        response = main_module._page(Path(main_module.SECURITY_PAGE_PATH))
        html = response.body.decode("utf-8")
        self.assertEqual(html.count('<nav class="global-nav">'), 1)


if __name__ == "__main__":
    unittest.main()
