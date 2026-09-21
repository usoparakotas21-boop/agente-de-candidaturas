import hashlib
import hmac
import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import main as main_module
from app import gmail_integration as gmail_integration_module
from app import outlook_integration as outlook_integration_module
from app import queue_routes as queue_routes_module
from app.auth import AuthMiddleware
from app.database import Base
from app.models import DocumentExportPurchase


def webhook_request(payment_id: str, signature: str, request_id: str = "req-123") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhooks/mercadopago",
            "headers": [
                (b"x-signature", signature.encode()),
                (b"x-request-id", request_id.encode()),
                (b"content-type", b"application/json"),
            ],
            "query_string": f"data.id={payment_id}".encode(),
            "server": ("testserver", 80),
            "client": ("198.51.100.10", 50000),
            "scheme": "https",
        }
    )


class WebhookSecurityTest(unittest.TestCase):
    def test_static_assets_are_public_for_page_bootstrapping(self):
        app = FastAPI()
        app.add_middleware(AuthMiddleware)

        @app.get("/static/test.js", response_class=PlainTextResponse)
        async def static_asset():
            return "console.log('ok')"

        with TestClient(app) as client:
            response = client.get("/static/test.js")

        self.assertEqual(response.status_code, 200)

    def test_application_serves_existing_static_asset_without_auth(self):
        # The production engine points to Supabase; keep this public-asset test
        # hermetic so collection never needs a live database connection.
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        local_session = sessionmaker(bind=engine)
        with patch.object(main_module, "engine", engine), patch.object(main_module, "SessionLocal", local_session):
            with TestClient(main_module.app) as client:
                response = client.get("/static/security-enhance.js?v=3")

        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers.get("content-type", ""))
        self.assertIn(".security-item strong,.security-item small{display:block}", response.text)
        self.assertIn("/api/privacy/export", response.text)
        self.assertIn("agente-de-candidaturas-dados.json", response.text)

    def test_payment_webhooks_are_public_for_provider_delivery(self):
        self.assertIn("/webhooks/mercadopago", AuthMiddleware.PUBLIC_PATHS)

    def test_mercadopago_return_restores_document_studio_context(self):
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/billing/mercadopago/success",
                "headers": [],
                "query_string": b"application_id=42&return_status=approved",
                "server": ("testserver", 80),
                "client": ("198.51.100.10", 50000),
                "scheme": "https",
            }
        )
        response = main_module.mercadopago_success(request)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/criar-documentos?application_id=42&payment_status=approved")

    def test_queue_internal_errors_use_generic_public_message(self):
        error = RuntimeError("senha do banco super secreta")
        self.assertEqual(
            queue_routes_module._queue_action_error(error),
            "Nao foi possivel concluir a acao agora. Tente novamente em instantes.",
        )

    def test_oauth_denials_do_not_echo_provider_details(self):
        with patch.object(gmail_integration_module, "_require_configuration"):
            with self.assertRaises(HTTPException) as gmail_error:
                asyncio.run(
                    gmail_integration_module.gmail_authorization_callback(
                        error="access_denied&error_description=token-secreto",
                        user={"id": "owner-a"},
                    )
                )
        self.assertEqual(gmail_error.exception.status_code, 400)
        self.assertNotIn("token-secreto", str(gmail_error.exception.detail))

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/auth/outlook/callback",
                "headers": [],
                "query_string": b"",
                "server": ("testserver", 80),
                "client": ("198.51.100.10", 50000),
                "scheme": "https",
            }
        )
        with patch.object(
            outlook_integration_module,
            "authenticated_user",
            new=AsyncMock(return_value={"id": "owner-a"}),
        ):
            with self.assertRaises(HTTPException) as outlook_error:
                asyncio.run(
                    outlook_integration_module.callback(
                        request,
                        error="access_denied&error_description=token-secreto",
                    )
                )
        self.assertEqual(outlook_error.exception.status_code, 400)
        self.assertNotIn("token-secreto", str(outlook_error.exception.detail))

    def test_mercadopago_hmac_signature_is_required_and_time_limited(self):
        secret = "test-webhook-secret"
        timestamp = str(int(time.time()))
        manifest = "id:payment-123;request-id:req-123;ts:" + timestamp + ";"
        digest = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
        payload = {"data": {"id": "payment-123"}}
        with patch.dict("os.environ", {"MERCADOPAGO_WEBHOOK_SECRET": secret}, clear=False):
            request = webhook_request("payment-123", f"ts={timestamp},v1={digest}")
            self.assertTrue(main_module._mercadopago_signature_is_valid(request, payload))
            stale = webhook_request("payment-123", f"ts={int(time.time()) - 301},v1={digest}")
            self.assertFalse(main_module._mercadopago_signature_is_valid(stale, payload))
            unsigned = webhook_request("payment-123", "")
            self.assertFalse(main_module._mercadopago_signature_is_valid(unsigned, payload))

    def test_webhook_fails_closed_when_provider_token_is_missing(self):
        request = webhook_request("payment-123", "")
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main_module.mercadopago_webhook(request))
        self.assertEqual(raised.exception.status_code, 503)

    def test_webhook_rejects_unsigned_delivery_when_provider_is_configured(self):
        request = webhook_request("payment-123", "")
        with patch.dict("os.environ", {"MERCADOPAGO_ACCESS_TOKEN": "token"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main_module.mercadopago_webhook(request))
        self.assertEqual(raised.exception.status_code, 401)

    def test_export_checkout_does_not_fallback_to_legacy_provider(self):
        with patch.dict(
            "os.environ",
            {"INFINITEPAY_EXPORT_PRICE_CENTS": "990"},
            clear=True,
        ):
            with self.assertRaises(HTTPException):
                main_module._document_export_price_cents()

    def test_paid_transition_is_idempotent_and_rejects_conflicting_replay(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        purchase = DocumentExportPurchase(owner_id="owner-a", order_nsu="order-a", amount=990)
        session.add(purchase)
        session.commit()
        self.assertEqual(
            main_module._mark_purchase_paid(session, purchase, transaction_nsu="payment-1", paid_amount=990),
            "paid",
        )
        session.refresh(purchase)
        self.assertEqual(
            main_module._mark_purchase_paid(session, purchase, transaction_nsu="payment-1", paid_amount=990),
            "idempotent",
        )
        self.assertEqual(
            main_module._mark_purchase_paid(session, purchase, transaction_nsu="payment-2", paid_amount=990),
            "conflict",
        )
        session.close()
        engine.dispose()

    def test_paid_transition_rejects_amount_mismatch(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        purchase = DocumentExportPurchase(owner_id="owner-a", order_nsu="order-a", amount=990)
        session.add(purchase)
        session.commit()
        self.assertEqual(
            main_module._mark_purchase_paid(session, purchase, transaction_nsu="payment-low", paid_amount=989),
            "amount_mismatch",
        )
        session.refresh(purchase)
        self.assertEqual(purchase.status, "PENDING")
        self.assertIsNone(purchase.transaction_nsu)
        session.close()
        engine.dispose()

    @patch.object(main_module.smtplib, "SMTP")
    def test_receipt_is_sent_once_when_smtp_is_configured(self, smtp_mock):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(bind=engine)()
        purchase = DocumentExportPurchase(
            owner_id="owner-a", payer_email="pessoa@example.com", order_nsu="order-a", amount=990,
            status="PAID", paid_amount=990, transaction_nsu="payment-1",
        )
        session.add(purchase)
        session.commit()
        with patch.dict("os.environ", {"SMTP_HOST": "smtp.test", "SMTP_FROM_EMAIL": "no-reply@test", "SMTP_USERNAME": "user", "SMTP_PASSWORD": "secret"}, clear=False):
            self.assertEqual(main_module._send_purchase_receipt(session, purchase), "sent")
            session.refresh(purchase)
            self.assertEqual(purchase.receipt_email_status, "SENT")
            self.assertEqual(main_module._send_purchase_receipt(session, purchase), "sent")
        smtp_mock.assert_called_once()
        session.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
