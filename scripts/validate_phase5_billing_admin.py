"""Offline validation for Phase 5 billing and developer-admin APIs.

This script uses an isolated SQLite database and a fake Mercado Pago HTTP
client. It never contacts Mercado Pago, Supabase, Gmail, or a real user.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import billing_routes, main
from app.database import Base
from app.models import BillingSubscription, BillingWebhookEvent, Candidate, EmailIntegration, JobIngestionRun


def request_with_json(payload: dict, path: str = "/api/billing/webhook") -> Request:
    body = json.dumps(payload).encode("utf-8")
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
            "client": ("phase5-validator", 50000),
            "server": ("validator", 80),
            "scheme": "https",
        },
        receive,
    )


class FakeResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class FakeAsyncClient:
    calls: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url: str, **kwargs):
        self.calls.append(url)
        if "/v1/payments/" in url:
            payment_id = url.rsplit("/", 1)[-1]
            status = {"payment-approved": "approved", "payment-rejected": "rejected"}.get(payment_id, "approved")
            return FakeResponse({
                "id": payment_id,
                "status": status,
                "preapproval_id": "preapproval-pro",
                "transaction_amount": 99.0,
                "currency_id": "BRL",
            })
        preapproval_id = url.rsplit("/", 1)[-1]
        if preapproval_id == "preapproval-canceled":
            return FakeResponse({
                "id": preapproval_id,
                "status": "cancelled",
                "external_reference": "subscription-start-cancel",
                "auto_recurring": {"transaction_amount": 34.90, "frequency": 1, "frequency_type": "months", "currency_id": "BRL"},
            })
        return FakeResponse({
            "id": "preapproval-pro",
            "status": "authorized",
            "external_reference": "subscription-pro-test",
            "next_payment_date": "2099-01-01T00:00:00Z",
            "auto_recurring": {"transaction_amount": 99.0, "frequency": 1, "frequency_type": "months", "currency_id": "BRL"},
        })


def validation() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    now = main.utc_now()
    db = session_factory()
    db.add_all([
        Candidate(owner_id="phase5-user-a", name="Usuário Teste", location="Salvador, BA", email="phase5@example.test", phone="", linkedin="", target_roles="Analista", summary=""),
        EmailIntegration(owner_id="phase5-user-a", provider="gmail", email="phase5@example.test", encrypted_refresh_token="test", scopes="gmail.readonly", sync_status="connected"),
        EmailIntegration(owner_id="phase5-user-a", provider="outlook", email="phase5@example.test", encrypted_refresh_token="test", scopes="mail.read", sync_status="needs_reconnect"),
        JobIngestionRun(source_id="gupy", status="succeeded", fetched_count=12, upserted_count=8, skipped_count=4, started_at=now, finished_at=now),
        JobIngestionRun(source_id="catho", status="failed", fetched_count=0, upserted_count=0, skipped_count=0, error_code="timeout", started_at=now, finished_at=now),
    ])
    db.add(BillingSubscription(owner_id="phase5-user-a", plan_code="pro", external_reference="subscription-pro-test", mercadopago_preapproval_id="preapproval-pro", payer_email="phase5@example.test", monthly_amount=9900, currency="BRL", status="pending"))
    db.add(BillingSubscription(owner_id="phase5-user-a", plan_code="start", external_reference="subscription-start-cancel", mercadopago_preapproval_id="preapproval-canceled", payer_email="phase5@example.test", monthly_amount=3490, currency="BRL", status="authorized", access_until=now + timedelta(days=30)))
    db.commit()
    db.close()

    approved = {"type": "payment.updated", "data": {"id": "payment-approved"}}
    rejected = {"type": "payment.created", "data": {"id": "payment-rejected"}}
    canceled = {"type": "subscription_preapproval", "data": {"id": "preapproval-canceled"}}
    with patch.object(main, "SessionLocal", session_factory), \
         patch.object(main, "_mercadopago_signature_is_valid", return_value=True), \
         patch.object(main, "_enforce_rate_limit", return_value=None), \
         patch.object(main.httpx, "AsyncClient", FakeAsyncClient), \
         patch.dict(os.environ, {"MERCADOPAGO_ACCESS_TOKEN": "phase5-test-token"}, clear=False):
        result = asyncio.run(billing_routes.billing_webhook(request_with_json(approved)))
        assert result.get("verified") is True, result
        calls_after_first = len(FakeAsyncClient.calls)
        replay = asyncio.run(billing_routes.billing_webhook(request_with_json(approved)))
        assert replay.get("idempotent") is True
        assert len(FakeAsyncClient.calls) == calls_after_first, "webhook replay called provider again"
        approved_check = session_factory()
        try:
            approved_sub = approved_check.scalar(select(BillingSubscription).where(BillingSubscription.external_reference == "subscription-pro-test"))
            assert approved_sub and approved_sub.last_payment_status == "approved" and approved_sub.access_until is not None
        finally:
            approved_check.close()
        assert asyncio.run(billing_routes.billing_webhook(request_with_json(rejected))).get("verified") is True
        assert asyncio.run(billing_routes.billing_webhook(request_with_json(canceled))).get("verified") is True

        check = session_factory()
        try:
            pro = check.scalar(select(BillingSubscription).where(BillingSubscription.external_reference == "subscription-pro-test"))
            canceled_sub = check.scalar(select(BillingSubscription).where(BillingSubscription.external_reference == "subscription-start-cancel"))
            assert pro and pro.last_payment_status == "rejected" and pro.access_until is not None
            assert canceled_sub and canceled_sub.status == "canceled"
            events = check.scalars(select(BillingWebhookEvent)).all()
            assert len(events) == 3 and all(item.status == "processed" for item in events)
        finally:
            check.close()

        admin = {"email": "contato@candidaturacerta.com.br", "id": "admin"}
        with patch.object(main, "_require_admin", new=AsyncMock(return_value=admin)):
            courtesy = asyncio.run(main.admin_conceder_cortesia("phase5-user-a", main.AdminCourtesyRequest(plan="consultoria", duration_days=14, reason="Validação"), request_with_json({}, "/api/admin/usuarios/phase5-user-a/cortesia")))
            assert courtesy["plan"] == "consultoria"
            metrics = asyncio.run(main.admin_metricas(request_with_json({}, "/api/admin/metricas")))
            assert "receita_total_centavos" in metrics and "usuarios_ativos_por_plano" in metrics
            integrations = asyncio.run(main.admin_integracoes(request_with_json({}, "/api/admin/integracoes")))
            assert integrations["items"][0]["gmail"]["status"] == "connected"
            logs = asyncio.run(main.admin_logs_coleta(request_with_json({}, "/api/admin/logs-coleta")))
            assert logs["total"] == 2 and logs["fontes"]["catho"]["falha"] == 1
        with patch.object(main, "_require_admin", new=AsyncMock(side_effect=HTTPException(403, "Acesso restrito"))):
            try:
                asyncio.run(main.admin_metricas(request_with_json({}, "/api/admin/metricas")))
            except HTTPException as exc:
                assert exc.status_code == 403
            else:
                raise AssertionError("admin endpoint accepted a non-admin request")

    engine.dispose()
    print("Phase 5 validation: OK (Mercado Pago idempotency, plan transitions, admin metrics/integrations/courtesy/logs)")


if __name__ == "__main__":
    try:
        validation()
    except Exception as exc:
        print(f"Phase 5 validation: FAILED - {exc}", file=sys.stderr)
        raise
