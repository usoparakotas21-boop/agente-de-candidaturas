import unittest
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app import document_storage
from app.database import Base
from app.models import (
    Application,
    Candidate,
    DocumentDelivery,
    DocumentExportPurchase,
    GeneratedDocument,
    Job,
    utc_now,
)


class PaidDocumentGenerationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )
        self.original_session_local = main_module.SessionLocal
        main_module.SessionLocal = self.session_factory
        self.users = {
            "owner-a": {"id": "owner-a", "email": "a@example.com", "email_confirmed_at": "2026-09-20T00:00:00Z"},
            "owner-b": {"id": "owner-b", "email": "b@example.com", "email_confirmed_at": "2026-09-20T00:00:00Z"},
        }
        self.application_ids = {}
        self.purchase_ids = {}
        db = self.session_factory()
        try:
            for owner_id, user in self.users.items():
                candidate = Candidate(
                    owner_id=owner_id,
                    name=f"Candidato {owner_id}",
                    location="Salvador/BA",
                    email=user["email"],
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
                    external_id=f"vaga-paga-{owner_id}",
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
                    status="ANALISADA",
                )
                db.add(application)
                db.flush()
                self.application_ids[owner_id] = application.id
                if owner_id == "owner-a":
                    purchase = DocumentExportPurchase(
                        owner_id=owner_id,
                        application_id=application.id,
                        payer_email=user["email"],
                        payer_email_confirmed=True,
                        order_nsu="export-test-1",
                        amount=990,
                        status="PENDING",
                        document_generation_status="WAITING",
                    )
                    db.add(purchase)
                    db.flush()
                    self.purchase_ids[owner_id] = purchase.id
            db.commit()
        finally:
            db.close()

    def tearDown(self):
        main_module.SessionLocal = self.original_session_local
        self.engine.dispose()

    def _archive_pair(self, db, *, application, owner_id, user):
        resume = GeneratedDocument(
            owner_id=owner_id,
            application_id=application.id,
            kind="resume",
            version="cv-test-version",
            title=application.job.title,
            company=application.job.company,
            filename="curriculo.docx",
            content_type=main_module.DOCUMENT_MIME_TYPE,
            content=b"PK\x03\x04resume",
            expires_at=utc_now() + timedelta(days=30),
        )
        letter = GeneratedDocument(
            owner_id=owner_id,
            application_id=application.id,
            kind="cover_letter",
            version="letter-test-version",
            title=application.job.title,
            company=application.job.company,
            filename="carta.docx",
            content_type=main_module.DOCUMENT_MIME_TYPE,
            content=b"PK\x03\x04letter",
            expires_at=utc_now() + timedelta(days=30),
        )
        db.add_all((resume, letter))
        db.flush()
        delivery = main_module._ensure_document_delivery(
            db,
            owner_id=owner_id,
            application_id=application.id,
            resume_document=resume,
            cover_letter_document=letter,
        )
        return application, delivery

    def _confirm_purchase(self):
        db = self.session_factory()
        try:
            purchase = db.get(DocumentExportPurchase, self.purchase_ids["owner-a"])
            result = main_module._mark_purchase_paid(
                db,
                purchase,
                transaction_nsu="mp-payment-123",
                paid_amount=990,
            )
            return result
        finally:
            db.close()

    def test_paid_purchase_is_processed_into_private_downloadable_history(self):
        self.assertEqual(self._confirm_purchase(), "paid")
        self.assertEqual(self._confirm_purchase(), "idempotent")
        with patch.object(main_module, "_generate_and_archive_application_documents", self._archive_pair), patch.object(
            main_module, "_send_document_delivery", return_value="skipped"
        ):
            self.assertEqual(main_module._process_pending_document_export_purchases(), 1)

        state = main_module.document_export_status(
            self.application_ids["owner-a"], self.users["owner-a"]
        )
        self.assertEqual(state["purchase_status"], "PAID")
        self.assertEqual(state["generation_status"], "READY")
        self.assertEqual(state["resume_url"], f"/applications/{self.application_ids['owner-a']}/document")
        self.assertEqual(state["letter_url"], f"/applications/{self.application_ids['owner-a']}/cover-letter/document")

        db = self.session_factory()
        try:
            self.assertEqual(db.query(GeneratedDocument).filter_by(owner_id="owner-a").count(), 2)
            self.assertEqual(db.query(DocumentDelivery).filter_by(owner_id="owner-a").count(), 1)
        finally:
            db.close()

        documents = main_module.list_generated_documents(self.users["owner-a"])["items"]
        self.assertEqual(len(documents), 1)
        resume_id = documents[0]["resume"]["id"]
        downloaded = main_module.download_generated_document(resume_id, self.users["owner-a"])
        self.assertEqual(downloaded.body, b"PK\x03\x04resume")

        claim_status, _ = main_module._claim_paid_document_purchase(
            purchase_id=self.purchase_ids["owner-a"],
            owner_id="owner-a",
            application_id=self.application_ids["owner-a"],
            allow_failed=True,
        )
        self.assertEqual(claim_status, "ready")

    def test_generation_helper_archives_valid_docx_files_to_owner_library(self):
        with tempfile.TemporaryDirectory() as directory:
            private_dir = Path(directory)
            resume_path = private_dir / "resume.docx"
            letter_path = private_dir / "letter.docx"
            resume_path.write_bytes(b"PK\x03\x04resume bytes")
            letter_path.write_bytes(b"PK\x03\x04letter bytes")

            def save_analysis(application, analysis, candidate):
                application.analysis_score = analysis["score"]
                application.recommendation = analysis["recommendation"]

            db = self.session_factory()
            try:
                application = db.get(Application, self.application_ids["owner-a"])
                result = self._confirm_purchase()
                self.assertEqual(result, "paid")
                user = self.users["owner-a"]
                with patch.object(document_storage, "OUTPUT_DIR", private_dir), patch.object(
                    main_module, "_build_application", return_value={
                        "profile": {},
                        "analysis": {"score": 80, "recommendation": "Boa oportunidade"},
                        "personalization": {"personalization_score": 84},
                        "resume": {"candidate": {"name": "Candidato owner-a"}},
                    }
                ), patch.object(main_module, "_save_analysis", side_effect=save_analysis), patch.object(
                    main_module, "generate_cover_letter", return_value="Carta personalizada."
                ), patch.object(main_module, "generate_docx", return_value=str(resume_path)), patch.object(
                    main_module, "generate_cover_letter_docx", return_value=str(letter_path)
                ):
                    application, delivery = main_module._generate_and_archive_application_documents(
                        db,
                        application=application,
                        owner_id="owner-a",
                        user=user,
                    )
                db.commit()
                self.assertEqual(application.status, "CURRICULO_GERADO")
                self.assertEqual(application.personalization_score, 84)
                self.assertEqual(delivery.status, "PENDING")
                self.assertEqual(db.query(GeneratedDocument).filter_by(owner_id="owner-a").count(), 2)
                self.assertEqual(db.query(DocumentDelivery).filter_by(owner_id="owner-a").count(), 1)
                versions = {document.kind: document.version for document in db.query(GeneratedDocument).filter_by(owner_id="owner-a")}
                self.assertTrue(versions["resume"].startswith("cv-"))
                self.assertTrue(versions["cover_letter"].startswith("carta-"))
            finally:
                db.close()

    def test_failed_generation_is_retried_without_losing_paid_purchase(self):
        self._confirm_purchase()
        calls = {"count": 0}

        def fail_once(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("sensitive internal failure")
            return self._archive_pair(*args, **kwargs)

        with patch.object(main_module, "_generate_and_archive_application_documents", side_effect=fail_once), patch.object(
            main_module, "_send_document_delivery", return_value="skipped"
        ):
            first_claim, purchase_id = main_module._claim_paid_document_purchase()
            self.assertEqual(first_claim, "claimed")
            first = main_module._finish_paid_document_purchase(purchase_id)
            self.assertEqual(first["generation_status"], "RETRY")
            self.assertNotIn("sensitive internal failure", str(first))

            db = self.session_factory()
            try:
                purchase = db.get(DocumentExportPurchase, purchase_id)
                self.assertEqual(purchase.status, "PAID")
                self.assertEqual(purchase.document_generation_attempts, 1)
                purchase.document_generation_next_attempt_at = utc_now() - timedelta(seconds=1)
                db.commit()
            finally:
                db.close()

            second_claim, second_purchase_id = main_module._claim_paid_document_purchase()
            self.assertEqual(second_claim, "claimed")
            self.assertEqual(second_purchase_id, purchase_id)
            second = main_module._finish_paid_document_purchase(purchase_id)
            self.assertEqual(second["generation_status"], "READY")

        self.assertEqual(calls["count"], 2)
        db = self.session_factory()
        try:
            purchase = db.get(DocumentExportPurchase, self.purchase_ids["owner-a"])
            self.assertEqual(purchase.status, "PAID")
            self.assertEqual(purchase.document_generation_attempts, 2)
            self.assertEqual(purchase.document_generation_status, "READY")
            self.assertEqual(db.query(GeneratedDocument).filter_by(owner_id="owner-a").count(), 2)
        finally:
            db.close()

    def test_purchase_status_and_claim_are_scoped_to_authenticated_owner(self):
        self._confirm_purchase()
        self.assertEqual(
            main_module._claim_paid_document_purchase(
                purchase_id=self.purchase_ids["owner-a"], owner_id="owner-b"
            ),
            ("missing", None),
        )
        with self.assertRaises(HTTPException) as denied:
            main_module.document_export_status(
                self.application_ids["owner-a"], self.users["owner-b"]
            )
        self.assertEqual(denied.exception.status_code, 404)

        state = main_module.document_export_status(
            self.application_ids["owner-b"], self.users["owner-b"]
        )
        self.assertEqual(state["purchase_status"], "NONE")
        self.assertEqual(state["generation_status"], "NOT_APPLICABLE")


if __name__ == "__main__":
    unittest.main()
