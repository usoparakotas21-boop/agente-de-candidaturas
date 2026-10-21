"""Shared owner-bound subscription lookup and access decision."""
from datetime import datetime, timezone

from sqlalchemy import or_, select

from .models import BillingSubscription


def subscription_for_owner(session, owner_id: str, now: datetime):
    if not owner_id:
        return None
    query = select(BillingSubscription).where(BillingSubscription.owner_id == owner_id)
    preferred = session.scalar(
        query.where(or_(
            BillingSubscription.status.in_(["authorized", "active"]),
            BillingSubscription.external_reference.ilike("%cortesia%"),
            BillingSubscription.access_until > now,
        )).order_by(BillingSubscription.id.desc()).limit(1)
    )
    return preferred if preferred is not None else session.scalar(
        query.order_by(BillingSubscription.id.desc()).limit(1)
    )


def subscription_has_access(subscription, now: datetime) -> bool:
    if subscription is None:
        return False
    expiry = subscription.access_until
    if expiry is not None:
        expiry = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry
        now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
        return expiry > now
    return subscription.status in {"authorized", "active"} or (
        "cortesia" in str(subscription.external_reference or "").casefold()
    )
