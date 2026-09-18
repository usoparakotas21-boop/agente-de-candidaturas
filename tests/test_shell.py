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
        self.assertNotIn('<header class="top">', html)

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

    def test_global_fetch_feedback_preserves_http_error_responses(self):
        script = (Path(main_module.STATIC_DIR) / "ui-feedback.js").read_text(encoding="utf-8")
        self.assertNotIn("if(!r.ok)throw r", script)
        self.assertIn("if(!r.ok){hide();return r}", script)
        self.assertIn("bar.setAttribute('aria-hidden','true')", script)
        self.assertIn("return r", script)

    def test_resume_upload_dropzone_selector_is_valid(self):
        html = (Path(main_module.STATIC_DIR) / "curriculos.html").read_text(encoding="utf-8")
        self.assertIn(".upload{", html)
        self.assertNotIn("..upload{", html)
        self.assertIn('id="status" role="status" aria-live="polite"', html)

    def test_document_studio_clear_action_protects_filled_draft(self):
        html = (Path(main_module.STATIC_DIR) / "document-studio.html").read_text(encoding="utf-8")
        self.assertIn('class="clear-action" id="clear"', html)
        self.assertIn("Limpar formulário", html)
        self.assertIn("const hasDraft=", html)
        self.assertIn("window.confirm('Limpar os dados preenchidos e a prévia gerada?')", html)
        self.assertIn("current=null", html)
        self.assertIn("$('title').focus()", html)


if __name__ == "__main__":
    unittest.main()
