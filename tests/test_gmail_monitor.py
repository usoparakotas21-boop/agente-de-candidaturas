import base64
import unittest

from app.gmail_monitor import (
    _capture_source,
    _message_content,
    _message_source_ref,
    _source_for,
)
from app.job_quality import split_job_alert


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


class GmailMonitorContentTest(unittest.TestCase):
    # The sender and email body below are synthetic fixtures, not collected
    # messages from any job provider.

    def test_source_uses_declared_sender_domain_before_display_name(self):
        self.assertEqual(
            _source_for(
                "LinkedIn Alerts <jobs@notifications.linkedin.com>",
                "Resumo de vagas sem URL individual.",
            ),
            "linkedin",
        )

    def test_plain_brand_mention_does_not_claim_provider_provenance(self):
        self.assertEqual(
            _source_for(
                "LinkedIn Alerts <jobs@alerts.example.test>",
                "Veja vagas no LinkedIn e atualize suas preferências.",
            ),
            "gmail",
        )

    def test_forwarded_alert_uses_known_individual_job_url(self):
        self.assertEqual(
            _source_for(
                "Pessoa <pessoa@example.test>",
                "Analista de RH\nhttps://www.glassdoor.com.br/partner/jobListing.htm?pos=1",
            ),
            "glassdoor",
        )

    def test_queue_reference_preserves_arrival_channel(self):
        self.assertEqual(_message_source_ref("outlook", "msg-123"), "outlook:msg-123")

    def test_keeps_detected_platform_as_queue_source(self):
        self.assertEqual(_capture_source("gmail", "linkedin"), "linkedin")
        self.assertEqual(_capture_source("outlook", "indeed"), "indeed")

    def test_keeps_mail_channel_when_platform_is_unknown(self):
        self.assertEqual(_capture_source("gmail", "gmail"), "gmail")
        self.assertEqual(_capture_source("outlook", "gmail"), "outlook")

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

    def test_drops_style_content_before_job_intake(self):
        rich = """
        <style>.mj-outlook-group-fix { width:100% !important; }</style>
        <p>Analista de Recursos Humanos</p><p>Empresa Alpha</p>
        """
        message = {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Nova vaga"},
                    {"name": "From", "value": "alertas@example.com"},
                ],
                "mimeType": "text/html",
                "body": {"data": _encoded(rich)},
            }
        }
        parsed = _message_content(message)
        self.assertNotIn("mj-outlook", parsed["content"])
        self.assertIn("Analista de Recursos Humanos", parsed["content"])


if __name__ == "__main__":
    unittest.main()
