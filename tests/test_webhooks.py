import hashlib
import hmac
import time
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import main as main_module
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
        with TestClient(main_module.app) as client:
            response = client.get("/static/security-enhance.js?v=3")

        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers.get("content-type", ""))

    def test_payment_webhooks_are_public_for_provider_delivery(self):
        self.assertIn("/webhooks/mercadopago", AuthMiddleware.PUBLIC_PATHS)

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


if __name__ == "__main__":
    unittest.main()
