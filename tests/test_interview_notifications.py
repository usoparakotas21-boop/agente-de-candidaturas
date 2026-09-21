import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import interview_notifications as notifications
from app.database import Base
from app.models import (
    Application,
    ApplicationEvent,
    Candidate,
    InterviewEmailOutbox,
    Job,
)


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "id": "owner-a",
            "email": "confirmed-account@example.com",
            "email_confirmed_at": "2026-09-01T12:00:00Z",
        }


class FakeHttpClient:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        type(self).calls += 1
        return FakeResponse()


class FakeSMTP:
    messages = []
    attempted_messages = []
    failures = 0

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, *args):
        pass

    def send_message(self, message):
        type(self).attempted_messages.append(message)
        if type(self).failures:
            type(self).failures -= 1
            raise OSError("temporary fake SMTP failure")
        type(self).messages.append(message)


class InterviewNotificationsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=self.engine)
        self.factory = sessionmaker(bind=self.engine)
        self.now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        FakeHttpClient.calls = 0
        FakeSMTP.messages = []
        FakeSMTP.attempted_messages = []
        FakeSMTP.failures = 0
        self.db = self.factory()
        self.candidate = Candidate(
            owner_id="owner-a",
            name="Pessoa candidata",
            location="Salvador",
            email="cv-contact@example.com",
            phone="71999999999",
            linkedin="",
            target_roles="RH",
            summary="",
            preferences_data=json.dumps(self.preferences()),
        )
        self.job = Job(
            owner_id="owner-a",
            source="manual",
            external_id="interview-1",
            company="Empresa A",
            title="Analista de RH",
            location="Salvador",
            modality="Híbrido",
            url="https://example.test/jobs/1",
            description="Descrição da vaga",
        )
        self.db.add_all([self.candidate, self.job])
        self.db.flush()
        self.application = Application(job_id=self.job.id, candidate_id=self.candidate.id, status="ENTREVISTA")
        self.db.add(self.application)
        self.db.flush()
        self.event = ApplicationEvent(
            application_id=self.application.id,
            status="ENTREVISTA",
            note="Atualização manual pelo usuário",
            created_at=self.now,
        )
        self.db.add(self.event)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def preferences(self, **overrides):
        value = {
            "notification_frequency": "immediate",
            "notify_interviews": True,
            "notify_interviews_consent_at": (self.now - timedelta(days=1)).isoformat(),
        }
        value.update(overrides)
        return value

    def enqueue(self):
        return notifications.enqueue_interview_notification(
            self.db,
            "owner-a",
            self.application.id,
            self.event.id,
            "immediate",
            self.now,
        )

    def smtp_config(self):
        return {
            "host": "smtp.test",
            "port": 587,
            "sender": "no-reply@example.test",
            "username": "test-user",
            "password": "test-password",
            "use_tls": True,
        }

    def supabase_env(self):
        return {
            "SUPABASE_URL": "https://supabase.test",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
        }

    def test_enqueue_is_idempotent_for_owner_and_event(self):
        first = self.enqueue()
        second = self.enqueue()
        self.db.commit()
        self.assertIsNotNone(first)
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(InterviewEmailOutbox).count(), 1)

    def test_only_normalized_preferences_with_explicit_consent_enqueue(self):
        self.candidate.preferences_data = json.dumps(self.preferences(notify_interviews_consent_at=None))
        self.assertIsNone(self.enqueue())
        self.candidate.preferences_data = json.dumps(self.preferences(notify_interviews=False))
        self.assertIsNone(self.enqueue())
        self.candidate.preferences_data = json.dumps(self.preferences())
        normalized, has_consent = notifications._parse_preferences(self.candidate)
        self.assertTrue(has_consent)
        self.assertTrue(normalized["notify_interviews"])
        self.assertIsNotNone(self.enqueue())

    def test_missing_smtp_performs_no_supabase_or_smtp_network(self):
        self.enqueue()
        self.db.commit()
        with patch.object(notifications, "smtp_settings", return_value=None), patch.object(FakeSMTP, "send_message") as send:
            result = notifications.run_interview_notification_cycle(
                self.factory,
                now=self.now,
                smtp_factory=FakeSMTP,
                http_client_factory=FakeHttpClient,
            )
        self.assertFalse(result["smtp_configured"])
        self.assertEqual(FakeHttpClient.calls, 0)
        send.assert_not_called()
        self.assertEqual(self.db.query(InterviewEmailOutbox).one().status, "PENDING")

    def test_dispatch_revalidates_consent_and_current_status(self):
        for change in ("consent", "status", "frequency"):
            with self.subTest(change=change):
                self.db.query(InterviewEmailOutbox).delete(synchronize_session=False)
                self.application.status = "ENTREVISTA"
                self.candidate.preferences_data = json.dumps(self.preferences())
                row = self.enqueue()
                self.db.commit()
                if change == "consent":
                    self.candidate.preferences_data = json.dumps(self.preferences(notify_interviews=False))
                elif change == "frequency":
                    self.candidate.preferences_data = json.dumps(self.preferences(notification_frequency="weekly"))
                else:
                    self.application.status = "APROVADO"
                self.db.commit()
                FakeHttpClient.calls = 0
                with patch.object(notifications, "smtp_settings", return_value=self.smtp_config()), patch.object(FakeSMTP, "send_message") as send:
                    result = notifications.run_interview_notification_cycle(
                        self.factory,
                        now=self.now,
                        smtp_factory=FakeSMTP,
                        http_client_factory=FakeHttpClient,
                    )
                self.assertEqual(result["skipped"], 1)
                self.assertEqual(FakeHttpClient.calls, 0)
                send.assert_not_called()
                self.db.refresh(row)
                self.assertEqual(row.status, "SKIPPED")

    def test_sends_only_to_confirmed_supabase_account_with_deterministic_message_id(self):
        row = self.enqueue()
        self.db.commit()
        with patch.object(notifications, "smtp_settings", return_value=self.smtp_config()), patch.dict(os.environ, self.supabase_env(), clear=False):
            result = notifications.run_interview_notification_cycle(
                self.factory,
                now=self.now,
                smtp_factory=FakeSMTP,
                http_client_factory=FakeHttpClient,
            )
        self.assertEqual(result["sent"], 1)
        self.assertEqual(FakeHttpClient.calls, 1)
        self.assertEqual(len(FakeSMTP.messages), 1)
        message = FakeSMTP.messages[0]
        self.assertEqual(message["To"], "confirmed-account@example.com")
        self.assertNotIn("cv-contact@example.com", message.as_string())
        self.assertIn("atualizou manualmente", message.get_content())
        self.assertEqual(message["Message-ID"], notifications._message(
            "no-reply@example.test", "confirmed-account@example.com", "owner-a", [{
                "event_id": self.event.id,
                "title": self.job.title,
                "company": self.job.company,
            }],
        )["Message-ID"])
        self.db.refresh(row)
        self.assertEqual(row.status, "SENT")

    def test_daily_interviews_in_the_same_window_are_sent_as_one_summary(self):
        self.candidate.preferences_data = json.dumps(self.preferences(notification_frequency="daily"))
        second_job = Job(
            owner_id="owner-a",
            source="manual",
            external_id="interview-2",
            company="Empresa B",
            title="Business Partner",
            location="Salvador",
            modality="Remoto",
            url="https://example.test/jobs/2",
            description="Descrição da vaga",
        )
        self.db.add(second_job)
        self.db.flush()
        second_application = Application(
            job_id=second_job.id,
            candidate_id=self.candidate.id,
            status="ENTREVISTA",
        )
        self.db.add(second_application)
        self.db.flush()
        second_event = ApplicationEvent(
            application_id=second_application.id,
            status="ENTREVISTA",
            note="Atualização manual pelo usuário",
            created_at=self.now,
        )
        self.db.add(second_event)
        first_row = notifications.enqueue_interview_notification(
            self.db, "owner-a", self.application.id, self.event.id, "daily", self.now
        )
        second_row = notifications.enqueue_interview_notification(
            self.db, "owner-a", second_application.id, second_event.id, "daily", self.now
        )
        self.db.commit()

        with patch.object(notifications, "smtp_settings", return_value=self.smtp_config()), patch.dict(os.environ, self.supabase_env(), clear=False):
            result = notifications.run_interview_notification_cycle(
                self.factory,
                now=self.now,
                smtp_factory=FakeSMTP,
                http_client_factory=FakeHttpClient,
            )

        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(FakeSMTP.messages), 1)
        body = FakeSMTP.messages[0].get_content()
        self.assertIn("Analista de RH — Empresa A", body)
        self.assertIn("Business Partner — Empresa B", body)
        self.db.refresh(first_row)
        self.db.refresh(second_row)
        self.assertEqual(first_row.status, "SENT")
        self.assertEqual(second_row.status, "SENT")

    def test_unverified_account_waits_then_sends_after_confirmation(self):
        row = self.enqueue()
        self.db.commit()
        with patch.object(notifications, "smtp_settings", return_value=self.smtp_config()), patch.object(
            notifications, "_verified_account_email", return_value=None
        ), patch.object(FakeSMTP, "send_message") as send:
            waiting = notifications.run_interview_notification_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP
            )
        self.assertEqual(waiting["skipped"], 1)
        self.db.refresh(row)
        self.assertEqual(row.status, "WAITING_VERIFICATION")
        self.assertEqual(row.attempt_count, 0)
        self.assertEqual(row.next_attempt_at, (self.now + timedelta(days=1)).replace(tzinfo=None))
        send.assert_not_called()

        with patch.object(notifications, "smtp_settings", return_value=self.smtp_config()), patch.object(
            notifications, "_verified_account_email", return_value="confirmed-account@example.com"
        ):
            delivered = notifications.run_interview_notification_cycle(
                self.factory,
                now=self.now + timedelta(days=1),
                smtp_factory=FakeSMTP,
            )
        self.assertEqual(delivered["sent"], 1)
        self.db.refresh(row)
        self.assertEqual(row.status, "SENT")

    def test_abandoned_worker_at_attempt_limit_is_marked_failed(self):
        row = self.enqueue()
        row.status = "SENDING"
        row.attempt_count = notifications.FOLLOWUP_MAX_ATTEMPTS
        row.started_at = self.now - notifications.FOLLOWUP_STALE_AFTER - timedelta(seconds=1)
        self.db.commit()

        claimed = notifications._claim_due_group(self.factory, self.now)

        self.assertEqual(claimed, [])
        self.db.refresh(row)
        self.assertEqual(row.status, "FAILED")
        self.assertIsNone(row.started_at)

    def test_smtp_failure_retries_with_same_message_id_then_sends(self):
        self.enqueue()
        self.db.commit()
        FakeSMTP.failures = 1
        with patch.object(notifications, "smtp_settings", return_value=self.smtp_config()), patch.dict(os.environ, self.supabase_env(), clear=False):
            failed = notifications.run_interview_notification_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient,
            )
            retry = notifications.run_interview_notification_cycle(
                self.factory,
                now=self.now + timedelta(seconds=31),
                smtp_factory=FakeSMTP,
                http_client_factory=FakeHttpClient,
            )
        self.assertEqual(failed["retried"], 1)
        self.assertEqual(retry["sent"], 1)
        self.assertEqual(len(FakeSMTP.messages), 1)
        self.assertEqual(len(FakeSMTP.attempted_messages), 2)
        self.assertEqual(
            FakeSMTP.attempted_messages[0]["Message-ID"],
            FakeSMTP.attempted_messages[1]["Message-ID"],
        )
        row = self.db.scalar(select(InterviewEmailOutbox))
        self.assertEqual(row.status, "SENT")
        self.assertEqual(row.attempt_count, 2)

    def test_cleanup_removes_rows_older_than_sixty_days(self):
        row = self.enqueue()
        self.db.commit()
        row.created_at = self.now - timedelta(days=61)
        self.db.commit()
        removed = notifications.cleanup_interview_email_outbox(self.db, now=self.now)
        self.assertEqual(removed, 1)
        self.assertEqual(self.db.query(InterviewEmailOutbox).count(), 0)


if __name__ == "__main__":
    unittest.main()
