"""Shared owner-bound subscription lookup and access decision."""
from datetime import datetime, timezone

from sqlalchemy import func, select

from .models import BillingSubscription


ACCESS_STATUSES = frozenset({"authorized", "active", "paused", "canceled", "pending", "in_process"})


def subscription_for_owner(session, owner_id: str, now: datetime):
    if not owner_id:
        return None
    query = select(BillingSubscription).where(BillingSubscription.owner_id == owner_id)
    # A newer pending/expired row must not hide an existing confirmed period.
    preferred = session.scalar(
        query.where(BillingSubscription.access_until > now)
        .where(func.lower(BillingSubscription.status).in_(ACCESS_STATUSES))
        .order_by(BillingSubscription.id.desc()).limit(1)
    )
    return preferred if preferred is not None else session.scalar(
        query.order_by(BillingSubscription.id.desc()).limit(1)
    )


def subscription_has_access(subscription, now: datetime) -> bool:
    if subscription is None:
        return False
    if str(subscription.status or "").casefold() not in ACCESS_STATUSES:
        return False
    expiry = subscription.access_until
    if expiry is not None:
        expiry = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry
        now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
        return expiry > now
    # Provider authorization or a courtesy label is not a paid access period.
    return False
