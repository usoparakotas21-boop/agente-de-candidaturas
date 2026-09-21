import asyncio
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app import main as main_module
from app.database import Base
from app.models import BillingSubscription, utc_now


class BillingSubscriptionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def tearDown(self):
        self.engine.dispose()

    def _request(self):
        return Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []})

    async def test_checkout_creates_monthly_preapproval_at_fixed_plan_price(self):
        captured = {}
        provider_response = httpx.Response(
            201,
            json={
                "id": "preapproval-start",
                "status": "pending",
                "init_point": "https://www.mercadopago.com.br/subscriptions/checkout?id=preapproval-start",
            },
        )

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, *, headers, json):
                captured.update(url=url, headers=headers, payload=json)
                return provider_response

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module.httpx, "AsyncClient", FakeClient),
            patch.dict("os.environ", {"MERCADOPAGO_ACCESS_TOKEN": "server-token"}),
        ):
            result = await main_module.create_subscription_checkout(
                main_module.SubscriptionCheckoutRequest(plan_code="start"),
                Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []}),
                {"id": "owner-1", "email": "candidate@example.com"},
            )

        self.assertEqual(captured["url"], "https://api.mercadopago.com/preapproval")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer server-token")
        self.assertTrue(captured["headers"]["X-Idempotency-Key"].startswith("subscription-start-"))
        self.assertEqual(captured["payload"]["auto_recurring"], {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": 34.9,
            "currency_id": "BRL",
        })
        self.assertEqual(result["monthly_amount"], 3490)
        db = self.session_factory()
        try:
            subscription = db.scalar(select(BillingSubscription))
            self.assertEqual(subscription.owner_id, "owner-1")
            self.assertEqual(subscription.plan_code, "start")
            self.assertEqual(subscription.status, "pending")
            self.assertEqual(subscription.mercadopago_preapproval_id, "preapproval-start")
        finally:
            db.close()

    async def test_pro_checkout_uses_fixed_ninety_nine_brl_monthly_price(self):
        captured = {}

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, *, headers, json):
                captured.update(url=url, headers=headers, payload=json)
                return httpx.Response(201, json={
                    "id": "preapproval-pro",
                    "status": "pending",
                    "init_point": "https://www.mercadopago.com.br/subscriptions/checkout?id=preapproval-pro",
                })

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_enforce_rate_limit"),
            patch.object(main_module.httpx, "AsyncClient", FakeClient),
            patch.dict("os.environ", {"MERCADOPAGO_ACCESS_TOKEN": "server-token"}),
        ):
            result = await main_module.create_subscription_checkout(
                main_module.SubscriptionCheckoutRequest(plan_code="pro"),
                self._request(),
                {"id": "owner-pro", "email": "pro@example.com"},
            )

        self.assertEqual(captured["url"], "https://api.mercadopago.com/preapproval")
        self.assertEqual(captured["payload"]["auto_recurring"], {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": 99.0,
            "currency_id": "BRL",
        })
        self.assertEqual(result["monthly_amount"], 9900)
        self.assertEqual(result["frequency"], "monthly")
        db = self.session_factory()
        try:
            subscription = db.scalar(select(BillingSubscription))
            self.assertEqual(subscription.owner_id, "owner-pro")
            self.assertEqual(subscription.plan_code, "pro")
            self.assertEqual(subscription.monthly_amount, 9900)
        finally:
            db.close()

    def test_pro_ebook_download_is_plan_gated_and_handles_missing_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            book_path = Path(temp_dir) / "hackeando_disc.docx"
            book_path.write_bytes(b"ebook test asset")
            pro_user = {"id": "ebook-pro", "app_metadata": {"plan": "pro"}}
            start_user = {"id": "ebook-start", "app_metadata": {"plan": "start"}}
            with (
                patch.object(main_module, "SessionLocal", self.session_factory),
                patch.object(main_module, "PRO_BOOK_PATH", book_path),
            ):
                response = main_module.download_pro_ebook(pro_user)
                self.assertEqual(Path(response.path), book_path)
                self.assertEqual(response.filename, "Hackeando-DISC.docx")
                with self.assertRaises(HTTPException) as denied:
                    main_module.download_pro_ebook(start_user)
                self.assertEqual(denied.exception.status_code, 403)

                with patch.object(main_module, "PRO_BOOK_PATH", Path(temp_dir) / "missing.docx"):
                    with self.assertRaises(HTTPException) as unavailable:
                        main_module.download_pro_ebook(pro_user)
                self.assertEqual(unavailable.exception.status_code, 503)

    async def test_unknown_checkout_recovers_by_search_before_reusing_reference(self):
        external_reference = "subscription-start-recovery"
        db = self.session_factory()
        db.add(BillingSubscription(
            owner_id="owner-recovery",
            plan_code="start",
            external_reference=external_reference,
            payer_email="candidate@example.com",
            monthly_amount=3490,
            status="checkout_unknown",
            updated_at=utc_now() - timedelta(minutes=5),
        ))
        db.commit()
        db.close()
        requests = []

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, **kwargs):
                requests.append(("get", url, kwargs))
                return httpx.Response(200, json={"results": []})

            async def post(self, url, **kwargs):
                requests.append(("post", url, kwargs))
                return httpx.Response(201, json={
                    "id": "preapproval-recovered",
                    "status": "pending",
                    "init_point": "https://www.mercadopago.com.br/subscriptions/recovered",
                })

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module.httpx, "AsyncClient", FakeClient),
            patch.dict("os.environ", {"MERCADOPAGO_ACCESS_TOKEN": "server-token"}),
        ):
            result = await main_module.create_subscription_checkout(
                main_module.SubscriptionCheckoutRequest(plan_code="start"),
                Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []}),
                {"id": "owner-recovery", "email": "candidate@example.com"},
            )

        self.assertEqual(result["external_reference"], external_reference)
        self.assertEqual([item[0] for item in requests], ["get", "post"])
        self.assertEqual(requests[1][2]["headers"]["X-Idempotency-Key"], external_reference)

    async def test_provider_5xx_is_unknown_and_recovers_existing_preapproval_without_posting_again(self):
        class FailingClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, *args, **kwargs):
                return httpx.Response(503, json={"message": "temporarily unavailable"})

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_enforce_rate_limit"),
            patch.object(main_module.httpx, "AsyncClient", FailingClient),
            patch.dict("os.environ", {"MERCADOPAGO_ACCESS_TOKEN": "server-token"}),
        ):
            with self.assertRaises(HTTPException) as error:
                await main_module.create_subscription_checkout(
                    main_module.SubscriptionCheckoutRequest(plan_code="start"),
                    self._request(),
                    {"id": "owner-5xx", "email": "candidate@example.com"},
                )
        self.assertEqual(error.exception.status_code, 502)
        db = self.session_factory()
        try:
            subscription = db.scalar(select(BillingSubscription))
            self.assertEqual(subscription.status, "checkout_unknown")
            external_reference = subscription.external_reference
            subscription.updated_at = utc_now() - timedelta(minutes=2)
            db.commit()
        finally:
            db.close()

        recovered_provider = {
            "external_reference": external_reference,
            "id": "preapproval-after-503",
            "status": "pending",
            "init_point": "https://www.mercadopago.com.br/subscriptions/recovered",
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": 34.9,
                "currency_id": "BRL",
            },
        }

        class RecoveryClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, *args, **kwargs):
                return httpx.Response(200, json={"results": [recovered_provider]})

            async def post(self, *args, **kwargs):
                self.fail("must recover the existing preapproval without a second POST")

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_enforce_rate_limit"),
            patch.object(main_module.httpx, "AsyncClient", RecoveryClient),
            patch.dict("os.environ", {"MERCADOPAGO_ACCESS_TOKEN": "server-token"}),
        ):
            result = await main_module.create_subscription_checkout(
                main_module.SubscriptionCheckoutRequest(plan_code="start"),
                self._request(),
                {"id": "owner-5xx", "email": "candidate@example.com"},
            )
        self.assertEqual(result["external_reference"], external_reference)
        self.assertEqual(result["checkout_url"], recovered_provider["init_point"])

    async def test_concurrent_initial_checkouts_reserve_only_one_provider_request(self):
        post_started = asyncio.Event()
        release_post = asyncio.Event()
        post_count = 0

        class SlowProviderClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, *args, **kwargs):
                nonlocal post_count
                post_count += 1
                post_started.set()
                await release_post.wait()
                return httpx.Response(201, json={
                    "id": "preapproval-single-reservation",
                    "status": "pending",
                    "init_point": "https://www.mercadopago.com.br/subscriptions/single-reservation",
                })

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module, "_enforce_rate_limit"),
            patch.object(main_module.httpx, "AsyncClient", SlowProviderClient),
            patch.dict("os.environ", {"MERCADOPAGO_ACCESS_TOKEN": "server-token"}),
        ):
            first = asyncio.create_task(main_module.create_subscription_checkout(
                main_module.SubscriptionCheckoutRequest(plan_code="start"),
                self._request(),
                {"id": "owner-race", "email": "candidate@example.com"},
            ))
            await post_started.wait()
            with self.assertRaises(HTTPException) as error:
                await main_module.create_subscription_checkout(
                    main_module.SubscriptionCheckoutRequest(plan_code="start"),
                    self._request(),
                    {"id": "owner-race", "email": "candidate@example.com"},
                )
            release_post.set()
            first_result = await first

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(post_count, 1)
        self.assertEqual(first_result["plan_code"], "start")

    async def test_payment_webhook_grants_pro_only_after_verified_monthly_payment(self):
        external_reference = "subscription-pro-test"
        db = self.session_factory()
        db.add(BillingSubscription(
            owner_id="owner-2",
            plan_code="pro",
            external_reference=external_reference,
            mercadopago_preapproval_id="preapproval-pro",
            checkout_url="https://www.mercadopago.com.br/checkout",
            payer_email="pro@example.com",
            monthly_amount=9900,
            status="pending",
        ))
        db.commit()
        db.close()

        payment = {
            "id": "invoice-pro-1",
            "preapproval_id": "preapproval-pro",
            "status": "scheduled",
            "summarized": "paid",
            "transaction_amount": "99.00",
            "currency_id": "BRL",
            "payment": {"id": "payment-pro-1", "status": "approved"},
        }
        paid_through = (utc_now() + timedelta(days=30)).isoformat()
        preapproval = {
            "id": "preapproval-pro",
            "external_reference": external_reference,
            "status": "authorized",
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": 99.0,
                "currency_id": "BRL",
            },
            "next_payment_date": paid_through,
        }

        queued_responses = [httpx.Response(200, json=payment), httpx.Response(200, json=preapproval)]

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, *args, **kwargs):
                return queued_responses.pop(0)

        async def receive():
            return {"type": "http.request", "body": json.dumps({"type": "subscription_authorized_payment", "data": {"id": "invoice-pro-1"}}).encode(), "more_body": False}

        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/webhooks/mercadopago",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "scheme": "https",
            "server": ("example.com", 443),
            "client": ("127.0.0.1", 12345),
        }, receive)
        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module.httpx, "AsyncClient", FakeClient),
            patch.object(main_module, "_mercadopago_signature_is_valid", return_value=True),
            patch.dict("os.environ", {"MERCADOPAGO_ACCESS_TOKEN": "server-token"}),
        ):
            result = await main_module.mercadopago_webhook(request)
            queued_responses.extend([httpx.Response(200, json=payment), httpx.Response(200, json=preapproval)])
            replay = await main_module.mercadopago_webhook(request)

        self.assertTrue(result["verified"])
        self.assertTrue(result["entitled"])
        self.assertTrue(replay["idempotent"])
        db = self.session_factory()
        try:
            subscription = db.scalar(select(BillingSubscription))
            self.assertEqual(subscription.status, "authorized")
            self.assertEqual(subscription.last_payment_status, "approved")
            self.assertTrue(main_module._subscription_is_entitled(subscription))
        finally:
            db.close()

    def test_subscription_does_not_grant_access_until_payment_is_confirmed(self):
        subscription = BillingSubscription(
            owner_id="owner-3",
            plan_code="start",
            external_reference="subscription-start-pending",
            mercadopago_preapproval_id="preapproval-pending",
            payer_email="start@example.com",
            monthly_amount=3490,
            status="authorized",
            next_payment_at=utc_now() + timedelta(days=30),
        )
        self.assertFalse(main_module._subscription_is_entitled(subscription))
        subscription.access_until = utc_now() + timedelta(days=30)
        self.assertTrue(main_module._subscription_is_entitled(subscription))
        subscription.access_until = utc_now() - timedelta(days=1)
        self.assertFalse(main_module._subscription_is_entitled(subscription))

    async def test_cancel_is_not_recorded_without_provider_confirmation(self):
        db = self.session_factory()
        db.add(BillingSubscription(
            owner_id="owner-cancel",
            plan_code="start",
            external_reference="subscription-cancel-test",
            mercadopago_preapproval_id="preapproval-cancel-test",
            payer_email="candidate@example.com",
            monthly_amount=3490,
            status="authorized",
            access_until=utc_now() + timedelta(days=20),
        ))
        db.commit()
        db.close()

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def put(self, *args, **kwargs):
                return httpx.Response(200, json={"status": "authorized"})

        with (
            patch.object(main_module, "SessionLocal", self.session_factory),
            patch.object(main_module.httpx, "AsyncClient", FakeClient),
            patch.dict("os.environ", {"MERCADOPAGO_ACCESS_TOKEN": "server-token"}),
        ):
            with self.assertRaises(HTTPException) as error:
                await main_module.cancel_current_subscription({"id": "owner-cancel"})
        self.assertEqual(error.exception.status_code, 502)
        db = self.session_factory()
        try:
            subscription = db.scalar(select(BillingSubscription))
            self.assertEqual(subscription.status, "authorized")
        finally:
            db.close()
        subscription.access_until = utc_now() + timedelta(days=30)
        subscription.status = "canceled"
        self.assertTrue(main_module._subscription_is_entitled(subscription))
        subscription.access_until = utc_now() - timedelta(days=1)
        self.assertFalse(main_module._subscription_is_entitled(subscription))


if __name__ == "__main__":
    unittest.main()
