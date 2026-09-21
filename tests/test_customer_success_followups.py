import json
import unittest
from datetime import timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import main as main_module
from app.customer_success import (
    cleanup_followup_email_outbox,
    run_followup_digest_cycle,
    schedule_followup_digests,
    _verified_account_email,
)
from app.database import Base
from app.models import Application, ApplicationEvent, Candidate, FollowupEmailOutbox, Job, utc_now


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeHttpClient:
    responses = []
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers):
        self.calls.append((url, headers))
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse({"id": "owner-a", "email": "account@example.com", "email_confirmed_at": "verified"})


class FakeSMTP:
    messages = []
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
        if self.failures:
            type(self).failures -= 1
            raise OSError("transient SMTP failure")
        self.messages.append(message)


class CustomerSuccessFollowupTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=self.engine)
        self.factory = sessionmaker(bind=self.engine)
        FakeHttpClient.responses = []
        FakeHttpClient.calls = []
        FakeSMTP.messages = []
        FakeSMTP.failures = 0
        self.now = utc_now()
        db = self.factory()
        candidate = Candidate(
            owner_id="owner-a",
            name="Candidata",
            location="Salvador",
            email="resume-contact@example.com",
            phone="71999999999",
            linkedin="",
            target_roles="RH",
            summary="Profissional de RH",
            preferences_data=json.dumps({"notification_frequency": "immediate", "notify_followups": True, "notify_followups_consent_at": self.now.isoformat()}),
        )
        job = Job(
            owner_id="owner-a", source="manual", external_id="follow-a", company="Empresa A",
            title="Analista de RH", location="Salvador", modality="Híbrido", url="https://example.test/vaga",
            description="Vaga de RH",
        )
        db.add_all([candidate, job])
        db.flush()
        application = Application(job_id=job.id, candidate_id=candidate.id, status="CANDIDATURA_ENVIADA")
        db.add(application)
        db.flush()
        db.add(ApplicationEvent(
            application_id=application.id,
            status="CANDIDATURA_ENVIADA",
            created_at=self.now - timedelta(days=9),
        ))
        db.commit()
        self.application_id = application.id
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def smtp_env(self):
        return {
            "SMTP_HOST": "smtp.test",
            "SMTP_PORT": "587",
            "SMTP_FROM_EMAIL": "no-reply@example.com",
            "SMTP_USERNAME": "smtp-user",
            "SMTP_PASSWORD": "smtp-password",
            "SMTP_USE_TLS": "true",
            "SUPABASE_URL": "https://supabase.test",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key-test-only",
        }

    def test_confirmed_supabase_account_gets_one_digest_not_cv_contact(self):
        with patch.dict("os.environ", self.smtp_env(), clear=False):
            first = run_followup_digest_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient,
            )
            second = run_followup_digest_cycle(
                self.factory, now=self.now + timedelta(minutes=6), smtp_factory=FakeSMTP,
                http_client_factory=FakeHttpClient,
            )

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(len(FakeSMTP.messages), 1)
        message = FakeSMTP.messages[0]
        self.assertEqual(message["To"], "account@example.com")
        self.assertNotIn("resume-contact@example.com", message.as_string())
        self.assertEqual(len(FakeHttpClient.calls), 1)
        self.assertIn("/auth/v1/admin/users/owner-a", FakeHttpClient.calls[0][0])
        db = self.factory()
        try:
            application = db.get(Application, self.application_id)
            self.assertIsNotNone(application.followup_notified_at)
            self.assertIsNone(application.followup_notification_outbox_id)
            outbox = db.scalar(select(FollowupEmailOutbox))
            self.assertEqual(outbox.status, "SENT")
            self.assertNotIn("account@example.com", json.dumps(outbox.application_ids))
        finally:
            db.close()

    def test_unconfirmed_account_is_never_sent_and_rechecked_without_hot_loop(self):
        FakeHttpClient.responses = [
            FakeResponse({"id": "owner-a", "email": "account@example.com", "email_confirmed_at": None}),
        ]
        with patch.dict("os.environ", self.smtp_env(), clear=False), patch.object(FakeSMTP, "send_message") as send:
            result = run_followup_digest_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient,
            )
        self.assertEqual(result["skipped"], 1)
        send.assert_not_called()
        db = self.factory()
        try:
            row = db.scalar(select(FollowupEmailOutbox))
            application = db.get(Application, self.application_id)
            self.assertEqual(row.status, "WAITING_VERIFICATION")
            self.assertEqual(row.attempt_count, 0)
            self.assertEqual(application.followup_notification_outbox_id, row.id)
            next_attempt = row.next_attempt_at.replace(tzinfo=timezone.utc) if row.next_attempt_at.tzinfo is None else row.next_attempt_at
            self.assertGreater(next_attempt, self.now)
        finally:
            db.close()

    def test_missing_smtp_is_a_hard_no_network_gate(self):
        with patch.dict("os.environ", {}, clear=False):
            for key in self.smtp_env():
                # Keep Supabase configured to prove SMTP gates the Admin call too.
                if key not in {"SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"}:
                    __import__("os").environ.pop(key, None)
            result = run_followup_digest_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient,
            )
        self.assertFalse(result["smtp_configured"])
        self.assertEqual(FakeHttpClient.calls, [])
        self.assertEqual(FakeSMTP.messages, [])
        db = self.factory()
        try:
            self.assertEqual(db.query(FollowupEmailOutbox).count(), 0)
        finally:
            db.close()

    def test_opt_out_and_none_frequency_create_no_outbox(self):
        db = self.factory()
        candidate = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
        candidate.preferences_data = json.dumps({"notification_frequency": "none", "notify_followups": True})
        db.commit()
        self.assertEqual(schedule_followup_digests(db, self.now), 0)
        candidate.preferences_data = json.dumps({"notification_frequency": "immediate", "notify_followups": False})
        db.commit()
        self.assertEqual(schedule_followup_digests(db, self.now), 0)
        self.assertEqual(db.query(FollowupEmailOutbox).count(), 0)
        db.close()

    def test_legacy_true_without_explicit_consent_is_not_an_opt_in(self):
        db = self.factory()
        candidate = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
        candidate.preferences_data = json.dumps({"notification_frequency": "immediate", "notify_followups": True})
        db.commit()
        self.assertEqual(schedule_followup_digests(db, self.now), 0)
        self.assertEqual(db.query(FollowupEmailOutbox).count(), 0)
        db.close()

    def test_preferences_endpoint_records_explicit_followup_consent(self):
        request = main_module.CandidatePreferencesRequest(notify_followups=True)
        self.assertFalse(main_module.CandidatePreferencesRequest().notify_followups)
        with patch.object(main_module, "SessionLocal", self.factory):
            response = main_module.update_preferences(request, {"id": "owner-a"})
        db = self.factory()
        try:
            candidate = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            saved = json.loads(candidate.preferences_data)
            self.assertTrue(response["preferences"]["notify_followups"])
            self.assertTrue(saved["notify_followups_consent_at"])
        finally:
            db.close()

    def test_scheduler_is_idempotent_for_same_application(self):
        db = self.factory()
        self.assertEqual(schedule_followup_digests(db, self.now), 1)
        self.assertEqual(schedule_followup_digests(db, self.now), 0)
        self.assertEqual(db.query(FollowupEmailOutbox).count(), 1)
        row = db.scalar(select(FollowupEmailOutbox))
        self.assertEqual(row.application_ids, [self.application_id])
        db.close()

    def test_admin_service_key_is_never_sent_over_plain_http(self):
        with patch.dict("os.environ", {
            "SUPABASE_URL": "http://supabase.test",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key-test-only",
        }, clear=False):
            with self.assertRaises(RuntimeError):
                _verified_account_email("owner-a", FakeHttpClient)
        self.assertEqual(FakeHttpClient.calls, [])

    def test_daily_digest_waits_for_local_send_window_and_groups_by_owner_period(self):
        db = self.factory()
        candidate = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
        candidate.preferences_data = json.dumps({"notification_frequency": "daily", "notify_followups": True, "notify_followups_consent_at": self.now.isoformat()})
        db.commit()
        before_nine_brt = self.now.replace(hour=10, minute=0, second=0, microsecond=0)
        # The timestamp is UTC; 10:00 UTC is before the 09:00 America/Sao_Paulo slot.
        self.assertEqual(schedule_followup_digests(db, before_nine_brt), 1)
        row = db.scalar(select(FollowupEmailOutbox))
        self.assertTrue(row.period_key.startswith("daily:"))
        scheduled_at = row.scheduled_at.replace(tzinfo=timezone.utc) if row.scheduled_at.tzinfo is None else row.scheduled_at
        self.assertGreater(scheduled_at, before_nine_brt)
        self.assertEqual(row.application_ids, [self.application_id])
        db.close()

    def test_smtp_failure_retries_same_idempotency_key_then_sends_once(self):
        FakeSMTP.failures = 1
        with patch.dict("os.environ", self.smtp_env(), clear=False):
            failed = run_followup_digest_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient,
            )
            retry_at = self.now + timedelta(seconds=31)
            sent = run_followup_digest_cycle(
                self.factory, now=retry_at, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient,
            )
        self.assertEqual(failed["retried"], 1)
        self.assertEqual(sent["sent"], 1)
        self.assertEqual(len(FakeSMTP.messages), 1)
        db = self.factory()
        try:
            row = db.scalar(select(FollowupEmailOutbox))
            self.assertEqual(row.status, "SENT")
            self.assertEqual(row.attempt_count, 2)
        finally:
            db.close()

    def test_old_outbox_is_deleted_and_unfinished_assignment_is_released(self):
        db = self.factory()
        self.assertEqual(schedule_followup_digests(db, self.now), 1)
        row = db.scalar(select(FollowupEmailOutbox))
        row.created_at = self.now - timedelta(days=61)
        db.commit()
        removed = cleanup_followup_email_outbox(db, now=self.now, max_age_days=60)
        application = db.get(Application, self.application_id)
        self.assertEqual(removed, 1)
        self.assertIsNone(application.followup_notification_outbox_id)
        self.assertEqual(db.query(FollowupEmailOutbox).count(), 0)
        db.close()

    def test_account_deletion_removes_followup_outbox(self):
        db = self.factory()
        self.assertEqual(schedule_followup_digests(db, self.now), 1)
        main_module._delete_local_owner_data(db, "owner-a")
        self.assertEqual(db.query(FollowupEmailOutbox).count(), 0)
        self.assertEqual(db.query(Application).count(), 0)
        db.rollback()
        db.close()


if __name__ == "__main__":
    unittest.main()
