import base64
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.gmail_monitor import (
    _capture_source,
    _message_content,
    _message_source_ref,
    _source_for,
    sync_integration,
)
from app.database import Base
from app.models import EmailIntegration, ProcessedEmailMessage, QueueItem
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


class GmailQuotaGateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False)
        with self.session_factory() as db:
            for index in range(50):
                db.add(
                    QueueItem(
                        owner_id="free-owner",
                        source="gmail",
                        decision="REVISAR",
                        decision_engine_version="test",
                        dedup_hash=f"{index:064x}",
                    )
                )
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    async def test_full_monthly_allowance_defers_mail_without_marking_it_processed(self):
        integration = EmailIntegration(
            id=1,
            owner_id="free-owner",
            provider="gmail",
            email="candidate@example.com",
            encrypted_refresh_token="encrypted",
            scopes="gmail.readonly",
        )
        fetched = False

        async def list_ids(_access_token):
            return ["message-pending-for-next-month"]

        async def get_message(_access_token, _message_id):
            nonlocal fetched
            fetched = True
            return {}

        with patch("app.gmail_monitor.SessionLocal", self.session_factory):
            result = await sync_integration(
                integration,
                access_token="test-token",
                list_message_ids=list_ids,
                get_message=get_message,
            )

        self.assertEqual(result["limit_reached"], 1)
        self.assertFalse(fetched)
        with self.session_factory() as db:
            self.assertIsNone(
                db.scalar(
                    select(ProcessedEmailMessage).where(
                        ProcessedEmailMessage.provider_message_id
                        == "message-pending-for-next-month"
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()
