import unittest
import re
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

    def test_active_templates_do_not_require_inline_style_attributes(self):
        templates = [
            path for path in Path(main_module.STATIC_DIR).glob("*.html")
            if "_backup" not in path.name
        ]
        for path in templates:
            html = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"\sstyle\s*=", html, re.IGNORECASE),
                msg=f"template ainda contém atributo style inline: {path.name}",
            )


if __name__ == "__main__":
    unittest.main()
