import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app import auth, main as main_module


class SensitiveRouteRateLimitTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = {"id": "account-123", "email": "person@example.com"}
        self.request = Mock(spec=Request)

    async def test_interview_evaluation_is_limited_before_ai_provider_call(self):
        request = self.request
        payload = main_module.InterviewAnswerRequest(
            question="Como você resolve conflitos?",
            answer="Eu escuto as pessoas e busco uma solução baseada em fatos.",
        )
        with (
            patch.object(main_module, "_document_export_metadata", return_value={"plan": "pro"}),
            patch.object(
                main_module,
                "_enforce_rate_limit",
                side_effect=HTTPException(429, "Muitas tentativas."),
            ) as limit,
            patch.object(main_module, "evaluate_interview_answer", new_callable=AsyncMock) as evaluate,
        ):
            with self.assertRaises(HTTPException) as raised:
                await main_module.evaluate_interview(payload, request=request, user=self.user)

        self.assertEqual(raised.exception.status_code, 429)
        limit.assert_called_once_with(request, "ai-interview-evaluation", "account-123")
        evaluate.assert_not_awaited()

    def test_document_generation_and_export_are_limited_before_work(self):
        request = self.request
        studio_payload = main_module.DocumentStudioRequest(
            title="Analista de Recursos Humanos",
            details="Descrição e requisitos de uma vaga para teste de limite.",
        )
        export_payload = main_module.DocumentStudioExportRequest(application_id=12)
        operations = (
            lambda: main_module.generate_doc(12, request=request, user=self.user),
            lambda: main_module.create_cover_letter(12, request=request, user=self.user),
            lambda: main_module.create_cover_letter_doc(12, request=request, user=self.user),
            lambda: main_module.generate_document_studio(
                studio_payload, request=request, user=self.user
            ),
            lambda: main_module.export_document_studio(
                export_payload, request=request, user=self.user
            ),
            lambda: main_module.generate_doc_standalone(
                main_module.ResumeRequest(title="Analista", resume={}),
                request=request,
                user=self.user,
            ),
        )

        for operation in operations:
            with self.subTest(operation=operation), patch.object(
                main_module,
                "_enforce_rate_limit",
                side_effect=HTTPException(429, "Muitas tentativas."),
            ) as limit, patch.object(main_module, "SessionLocal") as session_local, patch.object(
                main_module, "_build_application"
            ) as build_application, patch.object(main_module, "generate_docx") as generate_docx:
                with self.assertRaises(HTTPException) as raised:
                    operation()

            self.assertEqual(raised.exception.status_code, 429)
            limit.assert_called_once_with(request, "document-generation", "account-123")
            session_local.assert_not_called()
            build_application.assert_not_called()
            generate_docx.assert_not_called()

    async def test_mercadopago_webhook_is_limited_before_verification_or_provider_call(self):
        request = self.request
        with (
            patch.object(
                main_module,
                "_enforce_rate_limit",
                side_effect=HTTPException(429, "Muitas tentativas."),
            ) as limit,
            patch.object(main_module, "_mercadopago_signature_is_valid") as verify_signature,
            patch.object(main_module.httpx, "AsyncClient") as provider_client,
        ):
            with self.assertRaises(HTTPException) as raised:
                await main_module.mercadopago_webhook(request)

        self.assertEqual(raised.exception.status_code, 429)
        limit.assert_called_once_with(request, "mercadopago-webhook")
        verify_signature.assert_not_called()
        provider_client.assert_not_called()

    def test_fastapi_injects_request_for_limited_routes(self):
        paths = {
            "/api/interviews/evaluate",
            "/applications/{app_id}/email-submission/preview",
            "/applications/{app_id}/email-submission/send",
            "/api/documents/deliveries/{delivery_id}/retry",
            "/jobs/{job_id}/cover-letter",
            "/jobs/{job_id}/cover-letter/document",
            "/jobs/{job_id}/generate-document",
            "/document-studio/generate",
            "/document-studio/export",
            "/generate-document",
            "/webhooks/mercadopago",
        }
        for route in main_module.app.routes:
            if getattr(route, "path", None) in paths:
                with self.subTest(path=route.path):
                    self.assertEqual(route.dependant.request_param_name, "request")

    def test_sensitive_route_rate_limit_budgets(self):
        self.assertEqual(auth._RATE_LIMITS["application-email-preview"], (30, 60 * 60))
        self.assertEqual(auth._RATE_LIMITS["application-email-send"], (5, 15 * 60))
        self.assertEqual(auth._RATE_LIMITS["email-test"], (3, 15 * 60))
        self.assertEqual(auth._RATE_LIMITS["receipt-email-retry"], (3, 15 * 60))
        self.assertEqual(auth._RATE_LIMITS["ai-interview-evaluation"], (15, 60 * 60))
        self.assertEqual(auth._RATE_LIMITS["document-generation"], (20, 60 * 60))
        self.assertEqual(auth._RATE_LIMITS["document-email-retry"], (3, 15 * 60))
        self.assertEqual(auth._RATE_LIMITS["copilot-prepare"], (20, 60 * 60))
        self.assertEqual(auth._RATE_LIMITS["copilot-profile"], (30, 60))
        self.assertEqual(auth._RATE_LIMITS["copilot-documents"], (20, 60 * 60))
        self.assertEqual(auth._RATE_LIMITS["mercadopago-webhook"], (600, 60))

    def test_email_routes_have_operational_rate_limit_scopes(self):
        with patch.object(auth.distributed_rate_limit, "is_configured", return_value=False):
            for scope in (
                "application-email-preview",
                "application-email-send",
                "email-test",
                "document-email-retry",
                "receipt-email-retry",
            ):
                with self.subTest(scope=scope):
                    auth._enforce_rate_limit(self.request, scope, f"test-{scope}")


if __name__ == "__main__":
    unittest.main()
