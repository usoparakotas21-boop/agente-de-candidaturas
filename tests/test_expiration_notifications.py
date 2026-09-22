import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import expiration_notifications as notifications
from app import main as main_module
from app.database import Base
from app.models import Candidate, ExpiringJobEmailOutbox, Job


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
        if type(self).failures:
            type(self).failures -= 1
            raise OSError("temporary fake SMTP failure")
        type(self).messages.append(message)


class ExpirationNotificationsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=self.engine)
        self.factory = sessionmaker(bind=self.engine)
        self.now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        FakeHttpClient.calls = 0
        FakeSMTP.messages = []
        FakeSMTP.failures = 0
        db = self.factory()
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
        db.add(self.candidate)
        db.flush()
        self.jobs = []
        for index in range(2):
            job = Job(
                owner_id="owner-a",
                source="manual",
                external_id=f"expiration-{index}",
                company=f"Empresa {index + 1}",
                title=f"Analista de RH {index + 1}",
                location="Salvador",
                modality="Híbrido",
                url=f"https://example.test/jobs/{index + 1}",
                description="A descrição não contém uma data confiável.",
                valid_through=self.now + timedelta(days=3),
            )
            db.add(job)
            self.jobs.append(job)
        db.commit()
        self.job_ids = [job.id for job in self.jobs]
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def preferences(self, **overrides):
        value = {
            "notification_frequency": "immediate",
            "notify_expiring": True,
            "notify_expiring_consent_at": (self.now - timedelta(days=1)).isoformat(),
        }
        value.update(overrides)
        return value

    def smtp_env(self):
        return {
            "SMTP_HOST": "smtp.test",
            "SMTP_PORT": "587",
            "SMTP_FROM_EMAIL": "no-reply@example.com",
            "SMTP_USERNAME": "smtp-user",
            "SMTP_PASSWORD": "smtp-password",
            "SMTP_USE_TLS": "true",
            "SUPABASE_URL": "https://supabase.test",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
            "APP_BASE_URL": "https://candidaturacerta.com.br",
        }

    def outbox(self):
        db = self.factory()
        try:
            return db.scalars(select(ExpiringJobEmailOutbox).order_by(ExpiringJobEmailOutbox.id)).all()
        finally:
            db.close()

    def test_only_explicit_dates_with_strict_opt_in_are_scheduled_and_deduplicated(self):
        db = self.factory()
        try:
            self.assertEqual(notifications.schedule_expiration_alerts(db, self.now), 2)
            self.assertEqual(notifications.schedule_expiration_alerts(db, self.now), 0)
            self.assertEqual(db.query(ExpiringJobEmailOutbox).count(), 2)
            # A date found only in free text never qualifies.
            no_date = Job(
                owner_id="owner-a", source="manual", external_id="no-expiry-date",
                company="Empresa 3", title="Assistente", location="Salvador",
                modality="Remoto", url="https://example.test/jobs/3",
                description="Inscrições até 23/09/2026", valid_through=None,
            )
            db.add(no_date)
            candidate = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            candidate.preferences_data = json.dumps(self.preferences(notify_expiring_consent_at=None))
            db.commit()
            self.assertEqual(notifications.schedule_expiration_alerts(db, self.now), 0)
            self.assertEqual(db.query(ExpiringJobEmailOutbox).count(), 2)
        finally:
            db.close()

    def test_dates_outside_the_seven_day_window_are_not_scheduled(self):
        db = self.factory()
        try:
            for job_id in self.job_ids:
                job = db.get(Job, job_id)
                job.valid_through = self.now + timedelta(days=8)
            db.commit()
            self.assertEqual(notifications.schedule_expiration_alerts(db, self.now), 0)
        finally:
            db.close()

    def test_future_dated_consent_timestamp_is_not_valid_opt_in(self):
        db = self.factory()
        try:
            candidate = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            candidate.preferences_data = json.dumps(
                self.preferences(notify_expiring_consent_at=(self.now + timedelta(days=1)).isoformat())
            )
            db.commit()
            self.assertEqual(notifications.schedule_expiration_alerts(db, self.now), 0)
        finally:
            db.close()

    def test_digest_goes_only_to_confirmed_account_and_is_idempotent(self):
        with patch.dict("os.environ", self.smtp_env(), clear=True):
            first = notifications.run_expiration_notification_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient
            )
            second = notifications.run_expiration_notification_cycle(
                self.factory, now=self.now + timedelta(minutes=6), smtp_factory=FakeSMTP,
                http_client_factory=FakeHttpClient,
            )
        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(len(FakeSMTP.messages), 1)
        message = FakeSMTP.messages[0]
        self.assertEqual(message["To"], "confirmed-account@example.com")
        self.assertNotIn("cv-contact@example.com", message.as_string())
        self.assertIn("Analista de RH 1", message.get_content())
        self.assertIn("23/09/2026", message.get_content())
        self.assertIn("/vagas", message.get_content())
        self.assertEqual([row.status for row in self.outbox()], ["SENT", "SENT"])

    def test_brevo_can_deliver_expiration_alert_without_smtp_credentials(self):
        env = {key: value for key, value in self.smtp_env().items() if not key.startswith("SMTP_")}
        env["BREVO_API_KEY"] = "test-api-key"
        with patch.dict("os.environ", env, clear=True), patch.object(
            notifications, "send_email_message"
        ) as send:
            result = notifications.run_expiration_notification_cycle(
                self.factory, now=self.now, http_client_factory=FakeHttpClient
            )

        self.assertTrue(result["email_transport_configured"])
        self.assertFalse(result["smtp_configured"])
        self.assertEqual(result["sent"], 1)
        self.assertEqual(send.call_args.args[1]["transport"], "brevo_api")
        self.assertEqual(send.call_args.args[0]["To"], "confirmed-account@example.com")

    def test_opt_out_or_changed_deadline_before_send_skips_pending_alert(self):
        db = self.factory()
        try:
            self.assertEqual(notifications.schedule_expiration_alerts(db, self.now), 2)
            candidate = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            candidate.preferences_data = json.dumps(self.preferences(notify_expiring=False))
            db.commit()
        finally:
            db.close()
        with patch.dict("os.environ", self.smtp_env(), clear=True):
            result = notifications.run_expiration_notification_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient
            )
        self.assertEqual(result["sent"], 0)
        self.assertEqual(FakeHttpClient.calls, 0)
        self.assertEqual(FakeSMTP.messages, [])
        self.assertEqual([row.status for row in self.outbox()], ["SKIPPED", "SKIPPED"])

        # A revised explicit validThrough creates a distinct deduplication key.
        db = self.factory()
        try:
            candidate = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            candidate.preferences_data = json.dumps(self.preferences())
            job = db.get(Job, self.job_ids[0])
            job.valid_through = self.now + timedelta(days=4)
            db.commit()
            self.assertEqual(notifications.schedule_expiration_alerts(db, self.now), 1)
        finally:
            db.close()
        self.assertEqual(len(self.outbox()), 3)

    def test_changed_deadline_skips_old_alert_and_queues_the_new_deadline(self):
        db = self.factory()
        try:
            notifications.schedule_expiration_alerts(db, self.now)
            job = db.get(Job, self.job_ids[0])
            job.valid_through = self.now + timedelta(days=4)
            db.commit()
        finally:
            db.close()
        with patch.dict("os.environ", self.smtp_env(), clear=True):
            result = notifications.run_expiration_notification_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient
            )
        self.assertEqual(result["sent"], 1)
        statuses = [row.status for row in self.outbox()]
        self.assertEqual(statuses, ["SKIPPED", "SENT", "SENT"])
        body = FakeSMTP.messages[0].get_content()
        self.assertIn("Analista de RH 1", body)
        self.assertIn("Analista de RH 2", body)

    def test_missing_smtp_prevents_scheduling_and_network(self):
        with patch.dict("os.environ", {}, clear=True):
            result = notifications.run_expiration_notification_cycle(
                self.factory,
                now=self.now,
                smtp_factory=FakeSMTP,
                http_client_factory=FakeHttpClient,
            )
        self.assertFalse(result["smtp_configured"])
        self.assertEqual(result["scheduled"], 0)
        self.assertEqual(FakeHttpClient.calls, 0)
        self.assertEqual(FakeSMTP.messages, [])
        self.assertEqual(self.outbox(), [])

    def test_unverified_account_waits_and_transient_smtp_failure_retries(self):
        class UnverifiedResponse(FakeResponse):
            def json(self):
                return {"id": "owner-a", "email": "x@example.com"}

        class UnverifiedClient(FakeHttpClient):
            def get(self, *args, **kwargs):
                type(self).calls += 1
                return UnverifiedResponse()

        with patch.dict("os.environ", self.smtp_env(), clear=True):
            first = notifications.run_expiration_notification_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=UnverifiedClient
            )
        self.assertEqual(first["sent"], 0)
        self.assertEqual([row.status for row in self.outbox()], ["WAITING_VERIFICATION", "WAITING_VERIFICATION"])
        self.assertTrue(all(row.attempt_count == 0 for row in self.outbox()))

        # Re-claim immediately for a controlled retry-path test.
        db = self.factory()
        try:
            for row in db.scalars(select(ExpiringJobEmailOutbox)).all():
                row.status = "PENDING"
                row.next_attempt_at = None
            db.commit()
        finally:
            db.close()
        FakeSMTP.failures = 1
        with patch.dict("os.environ", self.smtp_env(), clear=True):
            retry = notifications.run_expiration_notification_cycle(
                self.factory, now=self.now, smtp_factory=FakeSMTP, http_client_factory=FakeHttpClient
            )
            recovered = notifications.run_expiration_notification_cycle(
                self.factory, now=self.now + timedelta(seconds=31), smtp_factory=FakeSMTP,
                http_client_factory=FakeHttpClient,
            )
        self.assertEqual(retry["retried"], 2)
        self.assertEqual(recovered["sent"], 1)
        self.assertEqual([row.status for row in self.outbox()], ["SENT", "SENT"])

    def test_outbox_cleanup_observes_sixty_day_retention(self):
        db = self.factory()
        try:
            notifications.schedule_expiration_alerts(db, self.now)
            rows = db.scalars(select(ExpiringJobEmailOutbox)).all()
            rows[0].created_at = self.now - timedelta(days=61)
            rows[1].created_at = self.now - timedelta(days=59)
            db.commit()
            self.assertEqual(notifications.cleanup_expiration_email_outbox(db, self.now), 1)
            self.assertEqual(db.query(ExpiringJobEmailOutbox).count(), 1)
        finally:
            db.close()

    def test_preferences_endpoint_requires_explicit_expiration_opt_in(self):
        db = self.factory()
        try:
            candidate = db.scalar(select(Candidate).where(Candidate.owner_id == "owner-a"))
            candidate.preferences_data = json.dumps({"notification_frequency": "immediate"})
            db.commit()
        finally:
            db.close()

        user = {"id": "owner-a"}
        with patch.object(main_module, "SessionLocal", self.factory), patch.dict("os.environ", {}, clear=True):
            disabled = main_module.update_preferences(
                main_module.CandidatePreferencesRequest(notify_expiring=True), user
            )
            self.assertFalse(disabled["preferences"]["notify_expiring"])
            enabled = main_module.update_preferences(
                main_module.CandidatePreferencesRequest(
                    notify_expiring=True,
                    notify_expiring_consent=True,
                    notification_frequency="immediate",
                ),
                user,
            )
            self.assertTrue(enabled["preferences"]["notify_expiring"])
            stored = main_module.get_preferences(user)
            self.assertTrue(stored["notify_expiring"])
            self.assertFalse(stored["lifecycle_email_configured"])
            opted_out = main_module.update_preferences(
                main_module.CandidatePreferencesRequest(
                    notify_expiring=False,
                    notification_frequency="immediate",
                ),
                user,
            )
            self.assertFalse(opted_out["preferences"]["notify_expiring"])
            self.assertIsNone(opted_out["preferences"]["notify_expiring_consent_at"])

    def test_privacy_export_includes_expiration_status_and_structured_deadline(self):
        db = self.factory()
        try:
            notifications.schedule_expiration_alerts(db, self.now)
        finally:
            db.close()
        with patch.object(main_module, "SessionLocal", self.factory):
            response = main_module.privacy_export({"id": "owner-a"})
        payload = json.loads(response.body)
        self.assertEqual(len(payload["expiring_job_email_notifications"]), 2)
        self.assertTrue(payload["expiring_job_email_notifications"][0]["deadline"])
        self.assertTrue(payload["jobs"][0]["valid_through"])

    def test_account_deletion_removes_expiration_outbox_rows(self):
        db = self.factory()
        try:
            notifications.schedule_expiration_alerts(db, self.now)
            self.assertEqual(db.query(ExpiringJobEmailOutbox).count(), 2)
            main_module._delete_local_owner_data(db, "owner-a")
            self.assertEqual(db.query(ExpiringJobEmailOutbox).count(), 0)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
