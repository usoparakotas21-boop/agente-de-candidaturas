import json
import base64
import unittest
import uuid
import asyncio
from starlette.responses import Response
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app import main as main_module
from app import auth as auth_module
from app.database import Base
from app.models import Application, BillingSubscription, Candidate, CopilotPreparation, Experience, Job, Skill, utc_now


def make_request(path="/api/copilot/prepare"):
    return Request({
        "type": "http", "method": "POST", "path": path,
        "headers": [], "query_string": b"",
        "client": ("testclient", 50000), "server": ("testserver", 443),
        "scheme": "https",
    })


def response_json(value):
    if isinstance(value, Response):
        return json.loads(value.body)
    return value


class CopilotRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        db = self.factory()
        candidate = Candidate(
            owner_id="user-a", name="Ana Souza", location="Salvador, BA",
            email="ana@example.com", phone="71999990000", linkedin="https://linkedin.com/in/ana",
            target_roles="Analista de RH", summary="Profissional de RH com experiência em seleção.",
            profile_data=json.dumps({"headline": "Analista de RH", "education": [{"course": "Administração", "institution": "Universidade A", "period": "2020"}], "languages": ["Português"]}),
        )
        candidate.experiences.append(Experience(
            company="Empresa A", role="Analista", start_date="2022", end_date="2025", description="Recrutamento e seleção.",
        ))
        candidate.skills.append(Skill(name="Excel", category="", proficiency=""))
        db.add(candidate)
        db.commit()
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def test_status_uses_separate_monthly_usage_and_limits(self):
        with patch.object(main_module, "SessionLocal", self.factory):
            with patch.object(main_module, "_enforce_rate_limit"):
                status = response_json(main_module.copilot_status(make_request("/api/copilot/status"), {"id": "user-a"}))
        self.assertEqual(status["plan_code"], "essential")
        self.assertEqual(status["limit"], 30)
        self.assertEqual(status["used"], 0)

    def test_prepare_returns_only_owners_profile_and_counts_once(self):
        request_id = str(uuid.uuid4())
        payload = main_module.CopilotPrepareRequest(
            request_id=request_id, portal_host="jobs.gupy.io", portal_allowed=True,
        )
        with patch.object(main_module, "SessionLocal", self.factory), patch.object(main_module, "_enforce_rate_limit"):
            result = response_json(main_module.copilot_prepare(payload, make_request(), {"id": "user-a", "email": "ana@example.com"}))
            complete = response_json(main_module.copilot_complete(
                main_module.CopilotCompleteRequest(request_id=request_id, filled_count=3),
                make_request("/api/copilot/complete"), {"id": "user-a"},
            ))
            status = response_json(main_module.copilot_status(make_request("/api/copilot/status"), {"id": "user-a"}))
        self.assertEqual(result["profile"]["name"], "Ana Souza")
        self.assertEqual(result["profile"]["experiences"][0]["company"], "Empresa A")
        self.assertEqual(result["profile"]["skills"], ["Excel"])
        self.assertEqual(result["usage"]["used"], 1)
        self.assertEqual(complete, {"status": "FILLED", "filled_count": 3})
        self.assertEqual(status["used"], 1)

    def test_prepare_requires_page_consent_and_supported_portal(self):
        with patch.object(main_module, "SessionLocal", self.factory), patch.object(main_module, "_enforce_rate_limit"):
            with self.assertRaises(HTTPException) as no_consent:
                main_module.copilot_prepare(
                    main_module.CopilotPrepareRequest(request_id=str(uuid.uuid4()), portal_host="jobs.gupy.io"),
                    make_request(), {"id": "user-a"},
                )
            with self.assertRaises(HTTPException) as unsupported:
                main_module.copilot_prepare(
                    main_module.CopilotPrepareRequest(request_id=str(uuid.uuid4()), portal_host="www.linkedin.com", portal_allowed=True),
                    make_request(), {"id": "user-a"},
                )
        self.assertEqual(no_consent.exception.status_code, 403)
        self.assertEqual(unsupported.exception.status_code, 403)

    def test_paid_plan_uses_its_own_allowance_and_quota_is_enforced(self):
        db = self.factory()
        db.add(BillingSubscription(
            owner_id="user-a", plan_code="start", external_reference="sub-user-a",
            payer_email="ana@example.com", monthly_amount=3490, status="authorized",
            access_until=utc_now() + timedelta(days=20),
        ))
        db.commit()
        now = utc_now()
        db.add_all([
            CopilotPreparation(
                owner_id="user-a", request_id=str(uuid.uuid4()), portal_host="gupy.io",
                status="FILLED", filled_count=1, consented_at=now, created_at=now,
            ) for _ in range(150)
        ])
        db.commit()
        db.close()
        with patch.object(main_module, "SessionLocal", self.factory), patch.object(main_module, "_enforce_rate_limit"):
            status = response_json(main_module.copilot_status(make_request("/api/copilot/status"), {"id": "user-a"}))
            with self.assertRaises(HTTPException) as reached:
                main_module.copilot_prepare(
                    main_module.CopilotPrepareRequest(request_id=str(uuid.uuid4()), portal_host="gupy.io", portal_allowed=True),
                    make_request(), {"id": "user-a"},
                )
        self.assertEqual(status["plan_code"], "start")
        self.assertEqual(status["limit"], 150)
        self.assertEqual(status["used"], 150)
        self.assertEqual(reached.exception.status_code, 403)

    def test_document_library_is_private_uncached_and_returns_only_complete_pairs(self):
        result = {"items": [
            {"application_id": 7, "title": "Analista", "company": "A", "created_at": "2026-09-20", "expires_at": "2026-10-20", "resume": {"id": 1}, "cover_letter": {"id": 2}},
            {"application_id": 8, "title": "Coordenação", "company": "B", "created_at": "2026-09-19", "expires_at": "2026-10-19", "resume": {"id": 3}, "cover_letter": None},
            {"application_id": None, "title": "Rascunho", "company": "C", "created_at": "2026-09-18", "expires_at": "2026-10-18", "resume": {"id": 4}, "cover_letter": {"id": 5}},
        ]}
        with patch.object(main_module, "list_generated_documents", return_value=result), patch.object(main_module, "_enforce_rate_limit"):
            response = main_module.copilot_documents(make_request("/api/copilot/documents"), {"id": "user-a"})
        payload = response_json(response)
        self.assertEqual([item["application_id"] for item in payload["items"]], [7])
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_pdf_attachment_endpoint_rejects_another_or_missing_account_application(self):
        with patch.object(main_module, "SessionLocal", self.factory), patch.object(main_module, "_enforce_rate_limit"):
            with self.assertRaises(HTTPException) as missing:
                main_module.copilot_application_pdfs(999, make_request("/api/copilot/documents/999/pdfs"), {"id": "user-a"})
        self.assertEqual(missing.exception.status_code, 404)

    def test_pdf_attachment_endpoint_returns_only_current_owner_documents_without_cache(self):
        db = self.factory()
        job = Job(
            owner_id="user-a", source="manual", external_id="copilot-doc-job",
            company="Empresa A", title="Analista de RH", location="Salvador, BA",
            modality="remote", contract_type="", salary="", url="https://jobs.gupy.io/job/1",
            description="Vaga de analista de RH.",
        )
        application = Application(job=job)
        db.add(application)
        db.commit()
        application_id = application.id
        db.close()
        resume = type("Doc", (), {"content": b"docx-resume", "title": "Currículo", "filename": "cv.docx"})()
        letter = type("Doc", (), {"content": b"docx-letter", "title": "Carta", "filename": "letter.docx"})()
        with patch.object(main_module, "SessionLocal", self.factory), patch.object(main_module, "_enforce_rate_limit"), patch.object(
            main_module, "_current_application_documents", return_value=(resume, letter)
        ), patch.object(main_module, "docx_to_pdf", side_effect=[b"%PDF-resume", b"%PDF-letter"]):
            response = main_module.copilot_application_pdfs(
                application_id, make_request(f"/api/copilot/documents/{application_id}/pdfs"), {"id": "user-a"}
            )
        payload = response_json(response)
        self.assertEqual(payload["title"], "Analista de RH")
        self.assertEqual(base64.b64decode(payload["resume"]["base64"]), b"%PDF-resume")
        self.assertEqual(base64.b64decode(payload["letter"]["base64"]), b"%PDF-letter")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_preparation_completion_is_owner_scoped(self):
        db = self.factory()
        request_id = str(uuid.uuid4())
        now = utc_now()
        db.add(CopilotPreparation(
            owner_id="user-a", request_id=request_id, portal_host="gupy.io",
            status="PREPARED", consented_at=now, created_at=now,
        ))
        db.commit()
        db.close()
        with patch.object(main_module, "SessionLocal", self.factory), patch.object(main_module, "_enforce_rate_limit"):
            with self.assertRaises(HTTPException) as denied:
                main_module.copilot_complete(
                    main_module.CopilotCompleteRequest(request_id=request_id, filled_count=2),
                    make_request("/api/copilot/complete"), {"id": "user-b"},
                )
        self.assertEqual(denied.exception.status_code, 404)

    def test_usage_audit_cleanup_observes_sixty_day_retention(self):
        now = utc_now()
        db = self.factory()
        for created_at in (now - timedelta(days=61), now - timedelta(days=59)):
            db.add(CopilotPreparation(
                owner_id="user-a", request_id=str(uuid.uuid4()), portal_host="gupy.io",
                status="NO_MATCH", consented_at=created_at, created_at=created_at,
            ))
        db.commit()
        db.close()
        with patch.object(main_module, "SessionLocal", self.factory):
            deleted = main_module._cleanup_copilot_preparations()
        db = self.factory()
        remaining = db.scalars(select(CopilotPreparation)).all()
        db.close()
        self.assertEqual(deleted, 1)
        self.assertEqual(len(remaining), 1)


class CopilotExtensionAuthenticationTests(unittest.TestCase):
    def request(self, headers):
        return Request({
            "type": "http", "method": "GET", "path": "/api/copilot/status",
            "headers": headers, "query_string": b"", "client": ("testclient", 50000),
            "server": ("testserver", 443), "scheme": "https",
        })

    def test_validates_bearer_token_and_account_verification(self):
        user = {"id": "user-a", "email": "ana@example.com", "email_confirmed_at": "2026-01-01T00:00:00Z"}
        with patch.object(auth_module, "user_from_token", new=AsyncMock(return_value=user)) as validate:
            result = asyncio.run(auth_module.extension_authenticated_user(self.request([(b"authorization", b"Bearer access-token")])))
        self.assertEqual(result["id"], "user-a")
        validate.assert_awaited_once_with("access-token")

    def test_requires_email_verification_and_mfa_session(self):
        with patch.object(auth_module, "user_from_token", new=AsyncMock(return_value={"id": "user-a", "email_confirmed_at": None})):
            with self.assertRaises(HTTPException) as unverified:
                asyncio.run(auth_module.extension_authenticated_user(self.request([(b"authorization", b"Bearer token")])))
        self.assertEqual(unverified.exception.status_code, 403)

        verified = {"id": "user-a", "email_confirmed_at": "2026-01-01T00:00:00Z"}
        with patch.object(auth_module, "user_from_token", new=AsyncMock(return_value=verified)), patch.object(auth_module, "_session_requires_mfa", return_value=True):
            with self.assertRaises(HTTPException) as mfa_required:
                asyncio.run(auth_module.extension_authenticated_user(self.request([(b"authorization", b"Bearer token")])))
        self.assertEqual(mfa_required.exception.status_code, 403)

    def test_expired_extension_access_token_does_not_rotate_site_refresh_cookie(self):
        request = self.request([
            (b"authorization", b"Bearer expired-access-token"),
            (b"x-cc-refresh-token", b"site-refresh-token"),
        ])
        with patch.object(auth_module, "user_from_token", new=AsyncMock(return_value=None)), patch.object(
            auth_module, "_refresh_session", new=AsyncMock()
        ) as refresh:
            with self.assertRaises(HTTPException) as expired:
                asyncio.run(auth_module.extension_authenticated_user(request))
        self.assertEqual(expired.exception.status_code, 401)
        refresh.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
