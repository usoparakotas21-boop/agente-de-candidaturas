import unittest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.data_retention import cleanup_expired_raw_data
from app.database import Base
from app.models import EmailIntegration, ProcessedEmailMessage, QueueItem


class RawDataRetentionTest(unittest.TestCase):
    def test_old_raw_payloads_are_removed_or_redacted(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        now = datetime.now(timezone.utc)
        integration = EmailIntegration(
            owner_id="owner-a",
            provider="gmail",
            email="person@example.com",
            encrypted_refresh_token="encrypted",
            scopes="gmail.readonly",
        )
        session.add(integration)
        session.flush()
        session.add_all(
            [
                ProcessedEmailMessage(
                    integration_id=integration.id,
                    owner_id="owner-a",
                    provider_message_id="old-message",
                    subject="Vaga antiga",
                    sender="jobs@example.com",
                    status="processed",
                    processed_at=now - timedelta(days=61),
                ),
                ProcessedEmailMessage(
                    integration_id=integration.id,
                    owner_id="owner-a",
                    provider_message_id="new-message",
                    subject="Vaga recente",
                    sender="jobs@example.com",
                    status="processed",
                    processed_at=now - timedelta(days=2),
                ),
                QueueItem(
                    owner_id="owner-a",
                    source="gmail",
                    title="Vaga antiga",
                    decision="REVISAR",
                    decision_engine_version="br-rh-1",
                    captured_at=now - timedelta(days=61),
                    raw_excerpt="conteúdo bruto antigo",
                ),
                QueueItem(
                    owner_id="owner-a",
                    source="gmail",
                    title="Vaga recente",
                    decision="REVISAR",
                    decision_engine_version="br-rh-1",
                    captured_at=now - timedelta(days=2),
                    raw_excerpt="conteúdo bruto recente",
                ),
            ]
        )
        session.commit()

        result = cleanup_expired_raw_data(session, max_age_days=60)

        self.assertEqual(result, {"processed_email_messages": 1, "queue_excerpts": 1})
        messages = session.scalars(select(ProcessedEmailMessage)).all()
        self.assertEqual([item.provider_message_id for item in messages], ["new-message"])
        queue_items = session.scalars(select(QueueItem).order_by(QueueItem.id)).all()
        self.assertIsNone(queue_items[0].raw_excerpt)
        self.assertEqual(queue_items[1].raw_excerpt, "conteúdo bruto recente")
        session.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
