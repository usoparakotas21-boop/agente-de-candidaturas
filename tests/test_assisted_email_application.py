import unittest
from datetime import timedelta
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import Base
from app.models import (
    Application,
    ApplicationEvent,
    Candidate,
    EmailApplicationSubmission,
    Job,
    utc_now,
)


class _FakeSMTP:
    sent_messages = []

    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self):
        return None

    def login(self, *_args):
        return None

    def send_message(self, message):
        type(self).sent_messages.append(message)
        return {}


class AssistedEmailApplicationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.user = {
            "id": "owner-email-test",
            "email": "candidate@example.com",
            "email_confirmed_at": "2026-09-20T00:00:00Z",
        }
        db = self.session_factory()
        try:
            candidate = Candidate(
                owner_id=self.user["id"], name="Ana Candidata", location="Salvador/BA",
                email=self.user["email"], phone="71999990000", linkedin="",
                target_roles="Analista de RH", summary="Experiência em recrutamento.",
            )
            db.add(candidate)
            db.flush()
            job = Job(
                owner_id=self.user["id"], source="manual", external_id="email-test-job",
                company="Empresa Exemplo", title="Analista de RH", location="Remoto",
                modality="Remoto", salary="", url="https://example.com/jobs/1",
                description="Envie currículo e carta para selecao@example.com.",
            )
            db.add(job)
            db.flush()
            application = Application(
                job_id=job.id, candidate_id=candidate.id, status="ANALISADA",
                cover_letter_text="Tenho interesse na vaga e experiência em recrutamento e seleção.",
                resume_version="resume-v1", cover_letter_version="letter-v1",
            )
            db.add(application)
            db.commit()
            self.application_id = application.id
            self.job_id = job.id
            self.resume = SimpleNamespace(filename="curriculo.docx")
            self.letter = SimpleNamespace(filename="carta.docx")
        finally:
            db.close()
        _FakeSMTP.sent_messages = []

    def tearDown(self):
        self.engine.dispose()

    def test_recipient_is_only_from_the_job_and_excludes_candidate_addresses(self):
        db = self.session_factory()
        try:
            application = db.get(Application, self.application_id)
            application.job.description += " Perfil: candidate@example.com; contato alternativo candidate@example.com."
            self.assertEqual(
                main_module._application_recipient_emails(application, self.user, "candidate@example.com"),
                ["selecao@example.com"],
            )
        finally:
            db.close()

    def test_confirmed_send_adds_reply_to_and_duplicate_is_never_sent_twice(self):
        smtp_config = {
            "host": "smtp.example.com", "port": 587, "use_tls": True,
            "username": "sender@example.com", "password": "not-a-real-secret",
            "sender": "Candidatura Certa <sender@example.com>",
        }
        payload = {
            "_resume_pdf": b"%PDF-resume",
            "_letter_pdf": b"%PDF-letter",
            "resume_version": "resume-v1",
            "cover_letter_version": "letter-v1",
        }
        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_enforce_rate_limit"),
            patch.object(main_module, "_refresh_application_risk"),
            patch.object(main_module, "_enforce_application_risk_gate"),
            patch.object(main_module, "_application_email_payload", side_effect=lambda *_args: dict(payload)),
            patch.object(main_module, "_current_application_documents", return_value=(self.resume, self.letter)),
            patch.object(main_module, "smtp_settings", return_value=smtp_config),
            patch.object(main_module.smtplib, "SMTP", _FakeSMTP),
        ):
            request = main_module.EmailApplicationSubmissionRequest(
                recipient="selecao@example.com",
                body="Tenho interesse nesta oportunidade e gostaria de apresentar minha experiência.",
                resume_version="resume-v1",
                cover_letter_version="letter-v1",
                consent=True,
            )
            result = main_module.send_application_by_email(self.application_id, request, self.user)
            self.assertEqual(result["status"], "SENT")
            self.assertEqual(_FakeSMTP.sent_messages[0]["Reply-To"], "candidate@example.com")
            with self.assertRaises(HTTPException) as duplicate:
                main_module.send_application_by_email(self.application_id, request, self.user)
            self.assertEqual(duplicate.exception.status_code, 409)

        self.assertEqual(len(_FakeSMTP.sent_messages), 1)
        db = self.session_factory()
        try:
            submission = db.scalar(select(EmailApplicationSubmission))
            self.assertEqual(submission.status, "SENT")
            self.assertEqual(submission.recipient_hash, main_module.hashlib.sha256(b"selecao@example.com").hexdigest())
            self.assertIsNotNone(submission.consented_at)
            self.assertEqual(db.scalar(select(ApplicationEvent).where(ApplicationEvent.application_id == self.application_id)).status, "CANDIDATURA_ENVIADA")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
