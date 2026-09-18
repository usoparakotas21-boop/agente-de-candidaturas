"""Retention helpers for raw intake data that is no longer needed."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, inspect, update

from .models import ProcessedEmailMessage, QueueItem


def _retention_days(value: int | None = None) -> int:
    try:
        days = int(value if value is not None else os.getenv("RAW_DATA_RETENTION_DAYS", "60"))
    except (TypeError, ValueError):
        days = 60
    return max(30, min(days, 3650))


def cleanup_expired_raw_data(db, *, max_age_days: int | None = None) -> dict[str, int]:
    """Delete raw processed-email rows and redact old queue excerpts.

    Structured job fields, decisions and application history remain available.
    The queue excerpt is cleared in place so deduplication and the audit trail
    continue working without retaining the original e-mail/OCR payload.
    """
    days = _retention_days(max_age_days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        tables = inspect(db.connection())
        deleted = 0
        redacted = 0
        if tables.has_table(ProcessedEmailMessage.__tablename__):
            deleted = db.execute(
                delete(ProcessedEmailMessage).where(
                    ProcessedEmailMessage.processed_at < cutoff,
                )
            ).rowcount or 0
        if tables.has_table(QueueItem.__tablename__):
            redacted = db.execute(
                update(QueueItem)
                .where(
                    QueueItem.captured_at < cutoff,
                    QueueItem.raw_excerpt.is_not(None),
                )
                .values(raw_excerpt=None)
            ).rowcount or 0
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"processed_email_messages": int(deleted), "queue_excerpts": int(redacted)}
