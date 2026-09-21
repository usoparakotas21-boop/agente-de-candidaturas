import json
import asyncio
import unittest
from types import SimpleNamespace
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app import main as main_module
from app.database import Base
from app.models import (
    Application,
    ApplicationEvent,
    BillingSubscription,
    Candidate,
    DocumentDelivery,
    DocumentExportPurchase,
    EmailIntegration,
    Experience,
    GeneratedDocument,
    Job,
    JobAnalysis,
    ProcessedEmailMessage,
    QueueItem,
    Skill,
    utc_now,
)


class PrivacyExportTest(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict("os.environ", {
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "SUPABASE_URL": "https://supabase.example.test",
        })
        self.env_patch.start()
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        db = self.session_factory()
        candidate = Candidate(
            owner_id="owner-a", name="Pessoa A", location="Salvador", email="a@example.test",
            phone="", linkedin="", target_roles="RH", summary="Resumo", profile_data="{}",
            preferences_data="{}",
        )
        other_candidate = Candidate(
            owner_id="owner-b", name="Pessoa B", location="Recife", email="b@example.test",
            phone="", linkedin="", target_roles="Financeiro", summary="Outro resumo", profile_data="{}",
            preferences_data="{}",
        )
        own_job = Job(owner_id="owner-a", source="manual", external_id="export-1", company="Empresa A", title="Analista", location="Salvador", modality="hibrido", url="https://example.test/a", description="Descrição")
        other_job = Job(owner_id="owner-b", source="manual", external_id="export-2", company="Empresa B", title="Coordenador", location="Recife", modality="remoto", url="https://example.test/b", description="Descrição")
        db.add_all([candidate, other_candidate, own_job, other_job])
        db.flush()
        own_application = Application(job_id=own_job.id, candidate_id=candidate.id, status="IDENTIFICADA")
        other_application = Application(job_id=other_job.id, candidate_id=other_candidate.id, status="ENTREVISTA")
        db.add_all([own_application, other_application])
        db.flush()
        db.add_all([
            Experience(candidate_id=candidate.id, company="Empresa A", role="Analista", start_date="2020", end_date="2024", description="Experiência privada A"),
            Experience(candidate_id=other_candidate.id, company="Empresa B", role="Coordenador", start_date="2020", end_date="2024", description="Experiência privada B"),
            Skill(candidate_id=candidate.id, name="Excel", category="Ferramentas", proficiency="Avançado"),
            Skill(candidate_id=other_candidate.id, name="SQL", category="Ferramentas", proficiency="Avançado"),
            JobAnalysis(job_id=own_job.id, overall_score=80, experience_score=8, skills_score=8, seniority_score=8, education_score=8, location_score=8, language_score=8, strengths="Força A", gaps="Gap A", recommendation="Capturar"),
            JobAnalysis(job_id=other_job.id, overall_score=70, experience_score=7, skills_score=7, seniority_score=7, education_score=7, location_score=7, language_score=7, strengths="Força B", gaps="Gap B", recommendation="Revisar"),
            ApplicationEvent(application_id=own_application.id, status="ANALISADA", note="Evento privado A"),
            ApplicationEvent(application_id=other_application.id, status="ENTREVISTA", note="Evento privado B"),
            BillingSubscription(owner_id="owner-a", plan_code="pro", external_reference="subscription-a", payer_email="a@example.test", monthly_amount=3490),
            BillingSubscription(owner_id="owner-b", plan_code="pro", external_reference="subscription-b", payer_email="b@example.test", monthly_amount=3490),
        ])
        own_integration = EmailIntegration(owner_id="owner-a", provider="gmail", email="a@example.test", encrypted_refresh_token="encrypted-a", scopes="readonly")
        other_integration = EmailIntegration(owner_id="owner-b", provider="outlook", email="b@example.test", encrypted_refresh_token="encrypted-b", scopes="readonly")
        db.add_all([own_integration, other_integration])
        db.flush()
        db.add_all([
            ProcessedEmailMessage(integration_id=own_integration.id, owner_id="owner-a", provider_message_id="message-a", subject="A", sender="jobs@example.test", status="PROCESSADO", job_id=own_job.id),
            ProcessedEmailMessage(integration_id=other_integration.id, owner_id="owner-b", provider_message_id="message-b", subject="B", sender="jobs@example.test", status="PROCESSADO", job_id=other_job.id),
            QueueItem(owner_id="owner-a", source="gmail", decision="REVISAR", decision_engine_version="test", job_id=own_job.id, dedup_hash="a" * 64),
            QueueItem(owner_id="owner-b", source="outlook", decision="REVISAR", decision_engine_version="test", job_id=other_job.id, dedup_hash="b" * 64),
        ])
        db.flush()
        own_resume = GeneratedDocument(owner_id="owner-a", application_id=own_application.id, kind="resume", version="v1", title="CV A", company="Empresa A", filename="cv-a.docx", content=b"PK resume a", expires_at=utc_now() + timedelta(days=30))
        own_letter = GeneratedDocument(owner_id="owner-a", application_id=own_application.id, kind="cover_letter", version="v1", title="Carta A", company="Empresa A", filename="carta-a.docx", content=b"PK letter a", expires_at=utc_now() + timedelta(days=30))
        other_resume = GeneratedDocument(owner_id="owner-b", application_id=other_application.id, kind="resume", version="v1", title="CV B", company="Empresa B", filename="cv-b.docx", content=b"PK resume b", expires_at=utc_now() + timedelta(days=30))
        other_letter = GeneratedDocument(owner_id="owner-b", application_id=other_application.id, kind="cover_letter", version="v1", title="Carta B", company="Empresa B", filename="carta-b.docx", content=b"PK letter b", expires_at=utc_now() + timedelta(days=30))
        db.add_all([own_resume, own_letter, other_resume, other_letter])
        db.flush()
        db.add_all([
            DocumentDelivery(owner_id="owner-a", application_id=own_application.id, resume_document_id=own_resume.id, cover_letter_document_id=own_letter.id, status="PENDING"),
            DocumentDelivery(owner_id="owner-b", application_id=other_application.id, resume_document_id=other_resume.id, cover_letter_document_id=other_letter.id, status="PENDING"),
        ])
        db.add_all([
            DocumentExportPurchase(
                owner_id="owner-a",
                order_nsu="export-purchase-a",
                amount=990,
                paid_amount=990,
                status="PAID",
            ),
            DocumentExportPurchase(
                owner_id="owner-b",
                order_nsu="export-purchase-b",
                amount=990,
                paid_amount=990,
                status="PAID",
            ),
        ])
        db.commit()
        db.close()

    def tearDown(self):
        self.engine.dispose()
        self.env_patch.stop()

    def test_export_is_owner_scoped_and_omits_secrets(self):
        with patch.object(main_module, "SessionLocal", self.session_factory):
            response = main_module.privacy_export({"id": "owner-a"})

        payload = json.loads(response.body)
        self.assertEqual(payload["profile"]["name"], "Pessoa A")
        self.assertEqual([item["company"] for item in payload["jobs"]], ["Empresa A"])
        self.assertEqual(len(payload["applications"]), 1)
        self.assertEqual([item["order_nsu"] for item in payload["purchases"]], ["export-purchase-a"])
        self.assertNotIn("access_token", payload)
        self.assertIn("attachment;", response.headers["content-disposition"])

    def test_delete_account_requires_exact_confirmation(self):
        request = Request({"type": "http", "method": "POST", "path": "/api/privacy/delete-account", "headers": [], "query_string": b"", "client": ("testclient", 50000), "server": ("testserver", 80), "scheme": "https"})
        with patch.object(main_module, "_delete_supabase_auth_user", new=AsyncMock()) as provider_delete:
            with self.assertRaises(main_module.HTTPException) as raised:
                asyncio.run(main_module.delete_account(main_module.AccountDeletionRequest(confirmation="excluir"), request, {"id": "owner-a"}))
        self.assertEqual(raised.exception.status_code, 422)
        provider_delete.assert_not_awaited()

    def test_delete_account_removes_local_owner_data_after_provider_confirmation(self):
        request = Request({"type": "http", "method": "POST", "path": "/api/privacy/delete-account", "headers": [], "query_string": b"", "client": ("testclient", 50000), "server": ("testserver", 80), "scheme": "https"})
        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_delete_supabase_auth_user", new=AsyncMock()) as provider_delete,
        ):
            response = asyncio.run(main_module.delete_account(main_module.AccountDeletionRequest(confirmation="EXCLUIR MINHA CONTA"), request, {"id": "owner-a"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["deleted"], True)
        provider_delete.assert_awaited_once()
        db = self.session_factory()
        self.assertEqual(db.query(Job).filter(Job.owner_id == "owner-a").count(), 0)
        self.assertEqual(db.query(Candidate).filter(Candidate.owner_id == "owner-a").count(), 0)
        self.assertEqual(db.query(DocumentExportPurchase).filter(DocumentExportPurchase.owner_id == "owner-a").count(), 0)
        self.assertEqual(db.query(BillingSubscription).filter(BillingSubscription.owner_id == "owner-a").count(), 0)
        self.assertEqual(db.query(EmailIntegration).filter(EmailIntegration.owner_id == "owner-a").count(), 0)
        self.assertEqual(db.query(ProcessedEmailMessage).filter(ProcessedEmailMessage.owner_id == "owner-a").count(), 0)
        self.assertEqual(db.query(QueueItem).filter(QueueItem.owner_id == "owner-a").count(), 0)
        self.assertEqual(db.query(GeneratedDocument).filter(GeneratedDocument.owner_id == "owner-a").count(), 0)
        self.assertEqual(db.query(DocumentDelivery).filter(DocumentDelivery.owner_id == "owner-a").count(), 0)
        self.assertEqual(db.query(ApplicationEvent).count(), 1)
        self.assertEqual(db.query(Experience).count(), 1)
        self.assertEqual(db.query(Skill).count(), 1)
        self.assertEqual(db.query(JobAnalysis).count(), 1)
        self.assertEqual(db.query(Application).count(), 1)
        self.assertEqual(db.query(Job).filter(Job.owner_id == "owner-b").count(), 1)
        self.assertEqual(db.query(Candidate).filter(Candidate.owner_id == "owner-b").count(), 1)
        self.assertEqual(db.query(BillingSubscription).filter(BillingSubscription.owner_id == "owner-b").count(), 1)
        self.assertEqual(db.query(EmailIntegration).filter(EmailIntegration.owner_id == "owner-b").count(), 1)
        self.assertEqual(db.query(ProcessedEmailMessage).filter(ProcessedEmailMessage.owner_id == "owner-b").count(), 1)
        self.assertEqual(db.query(QueueItem).filter(QueueItem.owner_id == "owner-b").count(), 1)
        self.assertEqual(db.query(GeneratedDocument).filter(GeneratedDocument.owner_id == "owner-b").count(), 2)
        self.assertEqual(db.query(DocumentDelivery).filter(DocumentDelivery.owner_id == "owner-b").count(), 1)
        self.assertEqual(db.query(DocumentExportPurchase).filter(DocumentExportPurchase.owner_id == "owner-b").count(), 1)
        db.close()

    def test_provider_failure_leaves_local_purge_committed_and_retryable(self):
        request = Request({"type": "http", "method": "POST", "path": "/api/privacy/delete-account", "headers": [], "query_string": b"", "client": ("testclient", 50000), "server": ("testserver", 80), "scheme": "https"})

        async def fail_after_check(_request, _user):
            check = self.session_factory()
            self.assertEqual(check.query(Job).filter(Job.owner_id == "owner-a").count(), 0)
            self.assertEqual(check.query(BillingSubscription).filter(BillingSubscription.owner_id == "owner-a").count(), 0)
            self.assertEqual(check.query(Candidate).filter(Candidate.owner_id == "owner-a").count(), 0)
            self.assertEqual(check.query(Job).filter(Job.owner_id == "owner-b").count(), 1)
            check.close()
            raise main_module.HTTPException(503, "provider unavailable")

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_delete_supabase_auth_user", new=AsyncMock(side_effect=fail_after_check)) as provider_delete,
        ):
            with self.assertRaises(main_module.HTTPException) as raised:
                asyncio.run(main_module.delete_account(main_module.AccountDeletionRequest(confirmation="EXCLUIR MINHA CONTA"), request, {"id": "owner-a"}))

        self.assertEqual(raised.exception.status_code, 503)
        provider_delete.assert_awaited_once()

    def test_local_commit_failure_does_not_delete_auth_or_local_records(self):
        class FailingCommitSession(Session):
            def commit(self):
                raise RuntimeError("simulated database commit failure")

        failing_factory = sessionmaker(bind=self.engine, class_=FailingCommitSession)
        request = Request({"type": "http", "method": "POST", "path": "/api/privacy/delete-account", "headers": [], "query_string": b"", "client": ("testclient", 50000), "server": ("testserver", 80), "scheme": "https"})
        with (
            patch.object(main_module, "SessionLocal", failing_factory),
            patch.object(main_module, "_delete_supabase_auth_user", new=AsyncMock()) as provider_delete,
        ):
            with self.assertRaises(main_module.HTTPException) as raised:
                asyncio.run(main_module.delete_account(main_module.AccountDeletionRequest(confirmation="EXCLUIR MINHA CONTA"), request, {"id": "owner-a"}))

        self.assertEqual(raised.exception.status_code, 503)
        provider_delete.assert_not_awaited()
        db = self.session_factory()
        self.assertEqual(db.query(Job).filter(Job.owner_id == "owner-a").count(), 1)
        self.assertEqual(db.query(Candidate).filter(Candidate.owner_id == "owner-a").count(), 1)
        self.assertEqual(db.query(BillingSubscription).filter(BillingSubscription.owner_id == "owner-a").count(), 1)
        self.assertEqual(db.query(Job).filter(Job.owner_id == "owner-b").count(), 1)
        db.close()

    def test_auth_user_already_missing_is_idempotent_success(self):
        client = AsyncMock()
        client.delete = AsyncMock(return_value=SimpleNamespace(status_code=404))
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        manager.__aexit__.return_value = False
        request = Request({"type": "http", "method": "POST", "path": "/api/privacy/delete-account", "headers": [], "query_string": b"", "client": ("testclient", 50000), "server": ("testserver", 80), "scheme": "https"})
        with (
            patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": "test-service-key", "SUPABASE_URL": "https://supabase.example.test"}),
            patch.object(main_module.httpx, "AsyncClient", return_value=manager),
        ):
            asyncio.run(main_module._delete_supabase_auth_user(request, {"id": "owner-a"}))

        client.delete.assert_awaited_once()

    def test_legacy_file_unlink_failure_rolls_back_and_preserves_auth(self):
        seed = self.session_factory()
        application = seed.query(Application).join(Job).filter(Job.owner_id == "owner-a").one()
        application.document_path = "legacy/private-resume.docx"
        seed.commit()
        seed.close()

        request = Request({"type": "http", "method": "POST", "path": "/api/privacy/delete-account", "headers": [], "query_string": b"", "client": ("testclient", 50000), "server": ("testserver", 80), "scheme": "https"})
        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "resolve_document_path", return_value=Path("legacy/private-resume.docx")),
            patch.object(Path, "unlink", autospec=True, side_effect=OSError("simulated file permission failure")) as unlink,
            patch.object(main_module, "_delete_supabase_auth_user", new=AsyncMock()) as provider_delete,
        ):
            with self.assertRaises(main_module.HTTPException) as raised:
                asyncio.run(main_module.delete_account(main_module.AccountDeletionRequest(confirmation="EXCLUIR MINHA CONTA"), request, {"id": "owner-a"}))

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("arquivos privados", raised.exception.detail)
        unlink.assert_called_once_with(Path("legacy/private-resume.docx"), missing_ok=True)
        provider_delete.assert_not_awaited()

        db = self.session_factory()
        self.assertEqual(db.query(Job).filter(Job.owner_id == "owner-a").count(), 1)
        self.assertEqual(db.query(Candidate).filter(Candidate.owner_id == "owner-a").count(), 1)
        self.assertEqual(db.query(BillingSubscription).filter(BillingSubscription.owner_id == "owner-a").count(), 1)
        self.assertEqual(db.query(Application).filter(Application.document_path == "legacy/private-resume.docx").count(), 1)
        self.assertEqual(db.query(Job).filter(Job.owner_id == "owner-b").count(), 1)
        db.close()


if __name__ == "__main__":
    unittest.main()
