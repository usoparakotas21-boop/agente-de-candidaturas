import base64
import unittest

from app.gmail_monitor import _message_content
from app.job_quality import split_job_alert


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


class GmailMonitorContentTest(unittest.TestCase):
    def test_converts_html_cards_to_readable_text_with_positioned_links(self):
        rich = """
        <html><body>
          <div><b>Analista de RH</b><br>Empresa Alpha<br>
          <a href="https://example.com/jobs/101">Ver vaga</a></div>
          <div><b>Coordenador de RH</b><br>Empresa Beta<br>
          <a href="https://example.com/jobs/202">Ver vaga</a></div>
        </body></html>
        """
        message = {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Duas vagas para voce"},
                    {"name": "From", "value": "alertas@example.com"},
                ],
                "mimeType": "text/html",
                "body": {"data": _encoded(rich)},
            }
        }

        parsed = _message_content(message)
        blocks = split_job_alert(parsed["subject"], parsed["content"])

        self.assertNotIn("<div>", parsed["content"])
        self.assertEqual(len(blocks), 2)
        self.assertIn("/jobs/101", blocks[0])
        self.assertIn("/jobs/202", blocks[1])


if __name__ == "__main__":
    unittest.main()
