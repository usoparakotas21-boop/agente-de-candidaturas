import json
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import main as main_module
from app.database import Base
from app.models import Application, Candidate, DocumentExportPurchase, Job


class PrivacyExportTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        db = self.session_factory()
        candidate = Candidate(
            owner_id="owner-a", name="Pessoa A", location="Salvador", email="a@example.test",
            phone="", linkedin="", target_roles="RH", summary="Resumo", profile_data="{}",
            preferences_data="{}",
        )
        own_job = Job(owner_id="owner-a", source="manual", external_id="export-1", company="Empresa A", title="Analista", location="Salvador", modality="hibrido", url="https://example.test/a", description="Descrição")
        other_job = Job(owner_id="owner-b", source="manual", external_id="export-2", company="Empresa B", title="Coordenador", location="Recife", modality="remoto", url="https://example.test/b", description="Descrição")
        db.add_all([candidate, own_job, other_job])
        db.flush()
        db.add(Application(job_id=own_job.id, candidate_id=candidate.id, status="IDENTIFICADA"))
        db.add(Application(job_id=other_job.id, status="ENTREVISTA"))
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
        self.assertEqual(db.query(Job).filter(Job.owner_id == "owner-b").count(), 1)
        db.close()


if __name__ == "__main__":
    unittest.main()
