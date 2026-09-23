import json
import os
import smtplib
import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import Base
from app.models import (
    Application,
    BillingSubscription,
    Candidate,
    DocumentDelivery,
    GeneratedDocument,
    Job,
    utc_now,
)
from scripts.migrate_rls import CHILD_POLICIES, DIRECT_OWNER_TABLES


class GeneratedDocumentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self._original_session_local = main_module.SessionLocal
        main_module.SessionLocal = self.session_factory
        self.users = {
            "owner-a": {
                "id": "owner-a",
                "email": "owner-a@example.com",
                "email_confirmed_at": "2026-09-20T00:00:00Z",
            },
            "owner-b": {
                "id": "owner-b",
                "email": "owner-b@example.com",
                "email_confirmed_at": "2026-09-20T00:00:00Z",
            },
        }
        self.application_ids = {}
        self.document_ids = {}
        self.delivery_ids = {}
        db = self.session_factory()
        try:
            for owner_id in self.users:
                db.add(BillingSubscription(
                    owner_id=owner_id, plan_code="pro",
                    external_reference=f"sub-{owner_id}", payer_email=f"{owner_id}@example.com",
                    monthly_amount=9900, currency="BRL", status="authorized",
                    access_until=utc_now() + timedelta(days=10),
                ))
                candidate = Candidate(
                    owner_id=owner_id,
                    name=f"Candidato {owner_id}",
                    location="Salvador/BA",
                    email=f"{owner_id}@example.com",
                    phone="71999999999",
                    linkedin="",
                    target_roles="Recursos Humanos",
                    summary="Experiência em recrutamento e seleção.",
                )
                db.add(candidate)
                db.flush()
                job = Job(
                    owner_id=owner_id,
                    source="teste",
                    external_id=f"vaga-{owner_id}",
                    company=f"Empresa {owner_id}",
                    title="Analista de Recursos Humanos",
                    location="Salvador/BA",
                    modality="Híbrido",
                    salary="",
                    url="https://example.com/vaga",
                    description="Atuação em recrutamento e seleção.",
                )
                db.add(job)
                db.flush()
                application = Application(
                    job_id=job.id,
                    candidate_id=candidate.id,
                    status="CURRICULO_GERADO",
                )
                db.add(application)
                db.flush()
                self.application_ids[owner_id] = application.id
                for version in ("v1", "v2"):
                    resume = self._document(
                        owner_id,
                        application.id,
                        "resume",
                        version,
                        "curriculo.docx",
                        b"PK\x03\x04" + f"resume {owner_id} {version}".encode(),
                    )
                    letter = self._document(
                        owner_id,
                        application.id,
                        "cover_letter",
                        version,
                        "carta.docx",
                        b"PK\x03\x04" + f"cover {owner_id} {version}".encode(),
                    )
                    db.add_all((resume, letter))
                    db.flush()
                    delivery = DocumentDelivery(
                        owner_id=owner_id,
                        application_id=application.id,
                        resume_document_id=resume.id,
                        cover_letter_document_id=letter.id,
                        status="PENDING",
                    )
                    db.add(delivery)
                    db.flush()
                    self.document_ids[(owner_id, version, "resume")] = resume.id
                    self.document_ids[(owner_id, version, "cover_letter")] = letter.id
                    self.delivery_ids[(owner_id, version)] = delivery.id
                # Legacy application columns point at the newest export. The
                # history table must continue to expose both saved versions.
                application.document_path = "latest-resume-v2.docx"
                application.cover_letter_path = "latest-letter-v2.docx"
            db.commit()
        finally:
            db.close()

    def tearDown(self):
        main_module.SessionLocal = self._original_session_local
        self.engine.dispose()

    @staticmethod
    def _document(owner_id, application_id, kind, version, filename, content, expires_at=None):
        return GeneratedDocument(
            owner_id=owner_id,
            application_id=application_id,
            kind=kind,
            version=version,
            title="Analista de Recursos Humanos",
            company=f"Empresa {owner_id}",
            filename=filename,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=content,
            expires_at=expires_at or utc_now() + timedelta(days=30),
        )

    def test_generated_document_tables_are_covered_by_rls_migration(self):
        configured = set(DIRECT_OWNER_TABLES) | set(CHILD_POLICIES)
        self.assertIn("generated_documents", configured)
        self.assertIn("document_deliveries", configured)

    def test_document_list_and_download_are_owner_scoped(self):
        owner_a_result = main_module.list_generated_documents(self.users["owner-a"])
        owner_b_result = main_module.list_generated_documents(self.users["owner-b"])
        owner_a_items = owner_a_result["items"]
        owner_b_items = owner_b_result["items"]

        # Each item is one resume/cover-letter version pair; no other user's
        # files or document identifiers may appear in the response.
        self.assertEqual(len(owner_a_items), 2)
        self.assertEqual(len(owner_b_items), 2)
        owner_a_json = json.dumps(owner_a_result, ensure_ascii=False)
        owner_b_json = json.dumps(owner_b_result, ensure_ascii=False)
        self.assertIn("Empresa owner-a", owner_a_json)
        self.assertIn("Empresa owner-b", owner_b_json)
        self.assertNotIn("owner-b", owner_a_json)
        self.assertNotIn("owner-a", owner_b_json)
        for item in owner_a_items:
            self.assertEqual(item["resume"]["version"], item["cover_letter"]["version"])

        document_id = self.document_ids[("owner-a", "v1", "resume")]
        response = main_module.download_generated_document(document_id, self.users["owner-a"])
        self.assertEqual(response.body, b"PK\x03\x04resume owner-a v1")
        self.assertIn("curriculo.docx", response.headers["content-disposition"])

        with self.assertRaises(HTTPException) as denied:
            main_module.download_generated_document(document_id, self.users["owner-b"])
        self.assertEqual(denied.exception.status_code, 404)

    def test_newest_application_path_does_not_overwrite_version_history(self):
        result = main_module.list_generated_documents(self.users["owner-a"])
        self.assertEqual(len(result["items"]), 2)
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertEqual(
            {(item["resume"]["version"], item["cover_letter"]["version"]) for item in result["items"]},
            {("v1", "v1"), ("v2", "v2")},
        )

        db = self.session_factory()
        try:
            self.assertEqual(db.query(GeneratedDocument).filter_by(owner_id="owner-a").count(), 4)
            self.assertEqual(db.query(DocumentDelivery).filter_by(owner_id="owner-a").count(), 2)
        finally:
            db.close()

    def test_failed_or_skipped_delivery_can_retry_and_sent_delivery_is_idempotent(self):
        messages = []
        failure_remaining = {"count": 1}

        class FakeSMTP:
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
                if failure_remaining["count"]:
                    failure_remaining["count"] -= 1
                    raise smtplib.SMTPException("temporary failure")
                messages.append(message)

        delivery_id = self.delivery_ids[("owner-a", "v1")]
        with patch.dict("os.environ", {}, clear=False):
            # With no SMTP configured, the initial attempt records SKIPPED.
            for key in ("SMTP_HOST", "SMTP_FROM_EMAIL", "SMTP_USERNAME", "SMTP_PASSWORD"):
                os.environ.pop(key, None)
            db = self.session_factory()
            try:
                delivery = db.get(DocumentDelivery, delivery_id)
                self.assertEqual(main_module._send_document_delivery(db, delivery, self.users["owner-a"]), "skipped")
                db.refresh(delivery)
                self.assertEqual(delivery.status, "SKIPPED")
            finally:
                db.close()

        smtp_settings = {
            "SMTP_HOST": "smtp.test",
            "SMTP_PORT": "587",
            "SMTP_FROM_EMAIL": "no-reply@example.com",
            "SMTP_USERNAME": "smtp-user",
            "SMTP_PASSWORD": "smtp-password",
            "SMTP_USE_TLS": "true",
        }
        with patch.dict("os.environ", smtp_settings, clear=False), patch.object(
            main_module.smtplib, "SMTP", FakeSMTP
        ):
            # First delivery attempt fails and retains a retryable state.
            with patch.object(main_module.logger, "warning") as smtp_warning:
                failed = main_module.retry_document_delivery(delivery_id, self.users["owner-a"])
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["email_status"], "FAILED")
            warning_format, _, stage, error_type, _smtp_code = smtp_warning.call_args.args
            warning_args = " ".join(str(value) for value in smtp_warning.call_args.args)
            self.assertIn("smtp_stage=%s", warning_format)
            self.assertEqual(stage, "send")
            self.assertEqual(error_type, "SMTPException")
            self.assertNotIn("temporary failure", warning_args)
            self.assertNotIn("smtp-password", warning_args)

            sent = main_module.retry_document_delivery(delivery_id, self.users["owner-a"])
            self.assertEqual(sent["status"], "sent")
            self.assertEqual(sent["email_status"], "SENT")
            sent_again = main_module.retry_document_delivery(delivery_id, self.users["owner-a"])
            self.assertEqual(sent_again["status"], "sent")
            self.assertEqual(sent_again["email_status"], "SENT")

        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(len(list(message.iter_attachments())), 2)
        self.assertEqual(
            {part.get_filename() for part in message.iter_attachments()},
            {"curriculo.docx", "carta.docx"},
        )
        self.assertEqual(
            {part.get_payload(decode=True) for part in message.iter_attachments()},
            {b"PK\x03\x04resume owner-a v1", b"PK\x03\x04cover owner-a v1"},
        )

        with self.assertRaises(HTTPException) as denied:
            main_module.retry_document_delivery(delivery_id, self.users["owner-b"])
        self.assertEqual(denied.exception.status_code, 404)

    def test_unconfirmed_account_is_skipped_without_contacting_smtp(self):
        unconfirmed_user = {"id": "owner-b", "email": "b@example.com"}
        smtp_settings = {
            "SMTP_HOST": "smtp.test",
            "SMTP_PORT": "587",
            "SMTP_FROM_EMAIL": "no-reply@example.com",
            "SMTP_USERNAME": "smtp-user",
            "SMTP_PASSWORD": "smtp-password",
            "SMTP_USE_TLS": "true",
        }
        delivery_id = self.delivery_ids[("owner-b", "v1")]
        with patch.dict("os.environ", smtp_settings, clear=False), patch.object(
            main_module.smtplib, "SMTP"
        ) as smtp:
            result = main_module.retry_document_delivery(delivery_id, unconfirmed_user)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["email_status"], "SKIPPED")
        smtp.assert_not_called()

    def test_document_email_retry_rate_limit_runs_before_database_access(self):
        request = object()
        with patch.object(
            main_module,
            "_enforce_rate_limit",
            side_effect=HTTPException(429, "Muitas tentativas."),
        ) as limiter, patch.object(main_module, "SessionLocal") as session_local:
            with self.assertRaises(HTTPException) as raised:
                main_module.retry_document_delivery(
                    self.delivery_ids[("owner-a", "v1")],
                    user=self.users["owner-a"],
                    request=request,
                )

        self.assertEqual(raised.exception.status_code, 429)
        limiter.assert_called_once_with(request, "document-email-retry", "owner-a")
        session_local.assert_not_called()

    def test_document_email_is_skipped_if_smtp_password_is_missing(self):
        delivery_id = self.delivery_ids[("owner-a", "v1")]
        with patch.dict(
            "os.environ",
            {
                "SMTP_HOST": "smtp.test",
                "SMTP_FROM_EMAIL": "no-reply@example.com",
                "SMTP_USERNAME": "smtp-user",
            },
            clear=True,
        ), patch.object(main_module.smtplib, "SMTP") as smtp:
            db = self.session_factory()
            try:
                delivery = db.get(DocumentDelivery, delivery_id)
                result = main_module._send_document_delivery(db, delivery, self.users["owner-a"])
                db.refresh(delivery)
                self.assertEqual(result, "skipped")
                self.assertEqual(delivery.status, "SKIPPED")
            finally:
                db.close()
        smtp.assert_not_called()

    def test_retention_deletes_expired_document_bytes_and_related_delivery(self):
        db = self.session_factory()
        try:
            application_id = self.application_ids["owner-a"]
            resume = self._document(
                "owner-a", application_id, "resume", "expired", "expired-resume.docx", b"expired resume",
                expires_at=utc_now() - timedelta(seconds=1),
            )
            letter = self._document(
                "owner-a", application_id, "cover_letter", "expired", "expired-letter.docx", b"expired letter",
                expires_at=utc_now() - timedelta(seconds=1),
            )
            db.add_all((resume, letter))
            db.flush()
            expired_delivery = DocumentDelivery(
                owner_id="owner-a",
                application_id=application_id,
                resume_document_id=resume.id,
                cover_letter_document_id=letter.id,
                status="SENT",
            )
            db.add(expired_delivery)
            expired_ids = (resume.id, letter.id)
            expired_delivery_id = None
            db.flush()
            expired_delivery_id = expired_delivery.id
            db.commit()
        finally:
            db.close()

        main_module._cleanup_generated_document_records()

        db = self.session_factory()
        try:
            self.assertTrue(all(db.get(GeneratedDocument, doc_id) is None for doc_id in expired_ids))
            self.assertIsNone(db.get(DocumentDelivery, expired_delivery_id))
            # Retention must leave unexpired versions intact.
            self.assertEqual(db.query(GeneratedDocument).filter_by(owner_id="owner-a").count(), 4)
        finally:
            db.close()

    def test_account_deletion_removes_only_that_owners_documents_and_deliveries(self):
        db = self.session_factory()
        try:
            main_module._delete_local_owner_data(db, "owner-a")
            db.commit()
            self.assertEqual(
                db.query(GeneratedDocument).filter_by(owner_id="owner-a").count(),
                0,
            )
            self.assertEqual(
                db.query(DocumentDelivery).filter_by(owner_id="owner-a").count(),
                0,
            )
            self.assertEqual(
                db.query(GeneratedDocument).filter_by(owner_id="owner-b").count(),
                4,
            )
            self.assertEqual(
                db.query(DocumentDelivery).filter_by(owner_id="owner-b").count(),
                2,
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
