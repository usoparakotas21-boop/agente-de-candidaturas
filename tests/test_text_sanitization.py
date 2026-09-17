import unittest

from app.text_sanitization import sanitize_untrusted_text
from app.job_intake import parse_job_text


class TextSanitizationTest(unittest.TestCase):
    def test_removes_script_style_comments_and_markup(self):
        value = sanitize_untrusted_text(
            "Cargo: Analista<br><script>alert(1)</script><!--x-->"
            "<style>body{display:none}</style> Recursos Humanos"
        )
        self.assertNotIn("script", value.casefold())
        self.assertNotIn("alert", value.casefold())
        self.assertNotIn("style", value.casefold())
        self.assertNotIn("<", value)
        self.assertIn("Cargo: Analista", value)

    def test_job_parser_returns_plain_text_for_external_html(self):
        result = parse_job_text(
            "<b>Cargo: Analista de RH</b>\n"
            "<b>Empresa: Exemplo</b>\n"
            "Descricao completa da vaga com recrutamento, selecao, indicadores e gestao de equipes. "
            "<script>window.evil=1</script>"
        )
        self.assertNotIn("<", result["description"])
        self.assertNotIn("window.evil", result["description"])


if __name__ == "__main__":
    unittest.main()
