"""Stable API aliases for billing integrations.

The original Mercado Pago routes live in :mod:`app.main` and are kept for
backwards compatibility with the production frontend.  This router exposes a
versioned, predictable API surface while delegating the actual checkout and
entitlement rules to that existing implementation.
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import authenticated_user


router = APIRouter(tags=["billing"])


class BillingCheckoutRequest(BaseModel):
    plan_code: Literal["start", "start_plus", "pro", "consultoria", "combo"]


class BillingCheckoutResponse(BaseModel):
    checkout_url: str
    order_nsu: str | None = None
    plan_code: str | None = None
    recurring: bool = False


@router.post("/api/billing/checkout", response_model=BillingCheckoutResponse)
async def create_billing_checkout(
    payload: BillingCheckoutRequest,
    request: Request,
    user: dict[str, Any] = Depends(authenticated_user),
):
    """Create a recurring plan checkout or the one-month Combo checkout."""

    from . import main

    if payload.plan_code == "combo":
        result = await main.create_combo_checkout(request, user)
        return {
            "checkout_url": result["checkout_url"],
            "order_nsu": result.get("order_nsu"),
            "plan_code": "combo",
            "recurring": False,
        }
    result = await main.create_subscription_checkout(
        main.SubscriptionCheckoutRequest(plan_code=payload.plan_code), request, user
    )
    return {
        "checkout_url": result["checkout_url"],
        "order_nsu": result.get("external_reference") or result.get("order_nsu"),
        "plan_code": payload.plan_code,
        "recurring": True,
    }


@router.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    """Verify and process a Mercado Pago event with durable idempotency.

    The request body is read once and cached by Starlette, so the legacy
    handler can safely parse it again after the ledger claim.
    """

    from . import main

    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    # Keep signature and provider-credential semantics identical to the
    # existing public webhook. Invalid requests are rejected before creating a
    # ledger row and therefore cannot poison idempotency state.
    if not main._mercadopago_token() or not main._mercadopago_signature_is_valid(request, payload):
        return await main.mercadopago_webhook(request)

    event_type = str(payload.get("type") or payload.get("topic") or "").strip().casefold()
    payment_id = str(
        (payload.get("data") or {}).get("id")
        or payload.get("id")
        or request.query_params.get("data.id")
        or ""
    ).strip()
    if not payment_id:
        return await main.mercadopago_webhook(request)

    claim = main._claim_billing_webhook_event(payment_id, event_type or "unknown", payload)
    if not claim["claimed"]:
        return {"received": True, "verified": True, "idempotent": True, "status": claim["status"]}

    try:
        result = await main.mercadopago_webhook(request)
        if isinstance(result, dict) and result.get("verified") is False:
            main._finish_billing_webhook_event(payment_id, event_type or "unknown", status="failed", error="provider_event_not_verified")
        else:
            main._finish_billing_webhook_event(payment_id, event_type or "unknown", status="processed")
        return result
    except HTTPException as exc:
        main._finish_billing_webhook_event(payment_id, event_type or "unknown", status="failed", error=str(exc.detail))
        raise
    except Exception as exc:
        main._finish_billing_webhook_event(payment_id, event_type or "unknown", status="failed", error=str(exc))
        raise

