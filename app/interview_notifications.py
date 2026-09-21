"""Opt-in, durable mail for manual application interview updates.

The outbox contains only owner/application/event identifiers. Delivery always
resolves a confirmed Supabase account address immediately before SMTP sending.
"""

from __future__ import annotations

import hashlib
import json
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Callable

import httpx
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .customer_success import (
    FOLLOWUP_BACKOFF_SECONDS,
    FOLLOWUP_MAX_ATTEMPTS,
    FOLLOWUP_RETENTION_DAYS,
    FOLLOWUP_STALE_AFTER,
    _period_window,
    _public_base_url,
    _verified_account_email,
    smtp_settings,
)
from .decision_engine import normalize_preferences
from .models import Application, ApplicationEvent, Candidate, InterviewEmailOutbox, Job, utc_now

logger = logging.getLogger(__name__)

INTERVIEW_STATUS = "ENTREVISTA"
INTERVIEW_POLL_SECONDS = 300
INTERVIEW_BATCH_SIZE = 50


def _parse_preferences(candidate: Candidate | None) -> tuple[dict, bool]:
    raw: dict = {}
    if candidate and candidate.preferences_data:
        try:
            decoded = json.loads(candidate.preferences_data)
            if isinstance(decoded, dict):
                raw = decoded
        except (TypeError, ValueError):
            pass
    normalized = normalize_preferences(raw)
    # The preference checkbox alone is not proof of consent. Legacy records
    # default notify_interviews to True, so require an explicit, valid timestamp.
    consent_value = raw.get("notify_interviews_consent_at")
    consented = False
    if isinstance(consent_value, str) and consent_value.strip():
        try:
            consent_at = datetime.fromisoformat(consent_value.strip().replace("Z", "+00:00"))
            if consent_at.tzinfo is None:
                consent_at = consent_at.replace(tzinfo=timezone.utc)
            consented = consent_at <= utc_now()
        except ValueError:
            consented = False
    normalized["notify_interviews_consent_at"] = consent_value if consented else None
    normalized["notify_interviews"] = bool(normalized["notify_interviews"] and consented)
    return normalized, consented


def _eligible_event(db, owner_id: str, application_id: int, event_id: int):
    event = db.get(ApplicationEvent, event_id)
    application = db.get(Application, application_id)
    if (
        event is None
        or application is None
        or event.application_id != application.id
        or event.status != INTERVIEW_STATUS
        or application.status != INTERVIEW_STATUS
        or application.job is None
        or str(application.job.owner_id or "") != owner_id
    ):
        return None
    candidate = db.scalar(
        select(Candidate).where(Candidate.owner_id == owner_id).order_by(Candidate.id.asc())
    )
    preferences, _ = _parse_preferences(candidate)
    frequency = preferences["notification_frequency"]
    if not preferences["notify_interviews"] or frequency == "none":
        return None
    return application, event, preferences


def enqueue_interview_notification(
    db,
    owner_id: str,
    application_id: int,
    event_id: int,
    frequency: str,
    now: datetime | None = None,
) -> InterviewEmailOutbox | None:
    """Queue a manual move to interview once, if current settings explicitly opt in.

    The supplied frequency must match the user's normalized notification
    frequency. The caller owns the surrounding transaction and should commit
    the application event and outbox row together.
    """
    owner = str(owner_id or "").strip()
    if not owner or not isinstance(application_id, int) or not isinstance(event_id, int):
        return None
    current = now or utc_now()
    eligible = _eligible_event(db, owner, application_id, event_id)
    if eligible is None:
        return None
    _, _, preferences = eligible
    normalized_frequency = preferences["notification_frequency"]
    if normalized_frequency == "none" or str(frequency or "").strip().casefold() != normalized_frequency:
        return None
    try:
        _, scheduled_at = _period_window(normalized_frequency, current)
    except ValueError:
        return None

    values = {
        "owner_id": owner,
        "application_id": application_id,
        "event_id": event_id,
        "frequency": normalized_frequency,
        "status": "PENDING",
        "attempt_count": 0,
        "scheduled_at": scheduled_at,
        "created_at": current,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(
            pg_insert(InterviewEmailOutbox).values(**values).on_conflict_do_nothing(
                index_elements=["owner_id", "event_id"]
            )
        )
    elif dialect == "sqlite":
        db.execute(
            sqlite_insert(InterviewEmailOutbox).values(**values).on_conflict_do_nothing(
                index_elements=["owner_id", "event_id"]
            )
        )
    elif db.scalar(
        select(InterviewEmailOutbox).where(
            InterviewEmailOutbox.owner_id == owner,
            InterviewEmailOutbox.event_id == event_id,
        )
    ) is None:
        db.add(InterviewEmailOutbox(**values))
    db.flush()
    return db.scalar(
        select(InterviewEmailOutbox).where(
            InterviewEmailOutbox.owner_id == owner,
            InterviewEmailOutbox.event_id == event_id,
        )
    )


def _claim_due_group(session_factory: Callable, now: datetime) -> list[int]:
    db = session_factory()
    try:
        stale_before = now - FOLLOWUP_STALE_AFTER
        retryable = (
            (InterviewEmailOutbox.attempt_count < FOLLOWUP_MAX_ATTEMPTS)
            & (InterviewEmailOutbox.scheduled_at <= now)
            & InterviewEmailOutbox.status.in_(("PENDING", "RETRY", "WAITING_VERIFICATION"))
            & (
                (InterviewEmailOutbox.status == "PENDING")
                | InterviewEmailOutbox.next_attempt_at.is_(None)
                | (InterviewEmailOutbox.next_attempt_at <= now)
            )
        )
        stale_sending = (
            (InterviewEmailOutbox.scheduled_at <= now)
            & (InterviewEmailOutbox.status == "SENDING")
            & (InterviewEmailOutbox.started_at < stale_before)
        )
        due = retryable | stale_sending
        candidate = db.execute(
            select(
                InterviewEmailOutbox.owner_id,
                InterviewEmailOutbox.frequency,
                InterviewEmailOutbox.scheduled_at,
            )
            .where(due)
            .order_by(InterviewEmailOutbox.scheduled_at.asc(), InterviewEmailOutbox.id.asc())
            .limit(1)
        ).first()
        if candidate is None:
            return []
        owner_id, frequency, scheduled_at = candidate
        if db.get_bind().dialect.name == "postgresql":
            lock_source = f"{owner_id}:{frequency}:{scheduled_at.isoformat()}".encode("utf-8")
            lock_key = int.from_bytes(hashlib.sha256(lock_source).digest()[:8], "big", signed=True)
            # Serialize by digest window so multiple Render instances cannot
            # split one user's daily/weekly batch into separate messages.
            db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}).scalar()
        rows = db.scalars(
            select(InterviewEmailOutbox)
            .where(
                InterviewEmailOutbox.owner_id == owner_id,
                InterviewEmailOutbox.frequency == frequency,
                InterviewEmailOutbox.scheduled_at == scheduled_at,
                due,
            )
            .order_by(InterviewEmailOutbox.id.asc())
            .with_for_update(skip_locked=True)
        ).all()
        if not rows:
            db.commit()
            return []
        claimed_ids = []
        for row in rows:
            if row.status == "SENDING" and row.attempt_count >= FOLLOWUP_MAX_ATTEMPTS:
                row.status = "FAILED"
                row.started_at = None
                row.next_attempt_at = None
                row.last_error = "Limite de tentativas atingido após interrupção do worker."
                continue
            row.status = "SENDING"
            row.started_at = now
            row.attempt_count += 1
            claimed_ids.append(row.id)
        db.commit()
        return claimed_ids
    finally:
        db.close()


def _set_status(session_factory: Callable, outbox_id: int, status: str, now: datetime, message: str) -> None:
    _set_status_many(session_factory, [outbox_id], status, now, message)


def _set_status_many(
    session_factory: Callable, outbox_ids: list[int], status: str, now: datetime, message: str
) -> None:
    db = session_factory()
    try:
        rows = db.scalars(
            select(InterviewEmailOutbox).where(InterviewEmailOutbox.id.in_(outbox_ids))
        ).all()
        for row in rows:
            row.status = status
            row.started_at = None
            row.last_error = message[:240]
            if status == "WAITING_VERIFICATION":
                row.attempt_count = max(0, row.attempt_count - 1)
                row.next_attempt_at = now + timedelta(days=1)
            else:
                row.next_attempt_at = None
        db.commit()
    finally:
        db.close()


def _record_retry(session_factory: Callable, outbox_id: int, now: datetime, error_code: str) -> None:
    _record_retry_many(session_factory, [outbox_id], now, error_code)


def _record_retry_many(session_factory: Callable, outbox_ids: list[int], now: datetime, error_code: str) -> None:
    db = session_factory()
    try:
        rows = db.scalars(
            select(InterviewEmailOutbox).where(InterviewEmailOutbox.id.in_(outbox_ids))
        ).all()
        for row in rows:
            row.started_at = None
            row.last_error = error_code[:240]
            if row.attempt_count >= FOLLOWUP_MAX_ATTEMPTS:
                row.status = "FAILED"
                row.next_attempt_at = None
            else:
                row.status = "RETRY"
                delay = FOLLOWUP_BACKOFF_SECONDS[min(row.attempt_count - 1, len(FOLLOWUP_BACKOFF_SECONDS) - 1)]
                row.next_attempt_at = now + timedelta(seconds=delay)
        db.commit()
    finally:
        db.close()


def _message(sender: str, recipient: str, owner_id: str, events: list[dict]) -> EmailMessage:
    event_ids = sorted(int(event["event_id"]) for event in events)
    digest = hashlib.sha256(
        f"{owner_id}:{','.join(map(str, event_ids))}:interview".encode("utf-8")
    ).hexdigest()[:32]
    entries = []
    for event in events:
        title = " ".join(str(event.get("title") or "sua candidatura").replace("\r", " ").replace("\n", " ").split())[:200]
        company = " ".join(str(event.get("company") or "Empresa não informada").replace("\r", " ").replace("\n", " ").split())[:200]
        entries.append(f"- {title} — {company}")
    message = EmailMessage()
    message["Subject"] = "Resumo de candidaturas marcadas como entrevista"
    message["From"] = sender
    message["To"] = recipient
    message["Message-ID"] = f"<interview-{digest}@candidaturacerta.com.br>"
    message.set_content(
        "Olá! Você atualizou manualmente o andamento destas candidaturas para entrevista:\n\n"
        f"{chr(10).join(entries)}\n\n"
        f"Revise suas candidaturas em {_public_base_url()}/candidaturas.\n\n"
        "Este aviso foi enviado conforme sua preferência de notificações. Você pode alterá-la em Configurações."
    )
    return message


def _verified_and_current(session_factory: Callable, outbox_id: int, now: datetime):
    db = session_factory()
    try:
        row = db.get(InterviewEmailOutbox, outbox_id)
        if row is None:
            return None
        eligible = _eligible_event(db, row.owner_id, row.application_id, row.event_id)
        if eligible is None:
            return None
        application, _, preferences = eligible
        if preferences["notification_frequency"] != row.frequency:
            return None
        return {
            "owner_id": row.owner_id,
            "outbox_id": row.id,
            "event_id": row.event_id,
            "title": application.job.title,
            "company": application.job.company,
        }
    finally:
        db.close()


def _record_sent(session_factory: Callable, outbox_id: int, now: datetime) -> None:
    _record_sent_many(session_factory, [outbox_id], now)


def _record_sent_many(session_factory: Callable, outbox_ids: list[int], now: datetime) -> None:
    db = session_factory()
    try:
        rows = db.scalars(
            select(InterviewEmailOutbox).where(InterviewEmailOutbox.id.in_(outbox_ids))
        ).all()
        for row in rows:
            row.status = "SENT"
            row.sent_at = now
            row.started_at = None
            row.next_attempt_at = None
            row.last_error = None
        db.commit()
    finally:
        db.close()


def run_interview_notification_cycle(
    session_factory: Callable,
    *,
    now: datetime | None = None,
    smtp_factory: Callable = smtplib.SMTP,
    http_client_factory: Callable = httpx.Client,
    max_messages: int = INTERVIEW_BATCH_SIZE,
) -> dict[str, int | bool]:
    """Deliver eligible interview summaries; missing SMTP prevents network I/O."""
    smtp = smtp_settings()
    if smtp is None:
        return {"smtp_configured": False, "sent": 0, "retried": 0, "skipped": 0}
    current = now or utc_now()
    sent = retried = skipped = processed = 0
    while processed < max(0, max_messages):
        outbox_ids = _claim_due_group(session_factory, current)
        if not outbox_ids:
            break
        processed += 1
        eligible_events = []
        for outbox_id in outbox_ids:
            current_event = _verified_and_current(session_factory, outbox_id, current)
            if current_event is None:
                _set_status(session_factory, outbox_id, "SKIPPED", current, "Status ou consentimento alterado antes do envio.")
                skipped += 1
            else:
                eligible_events.append(current_event)
        if not eligible_events:
            continue
        event_ids_to_retry = [event["outbox_id"] for event in eligible_events]
        try:
            owner_id = eligible_events[0]["owner_id"]
            recipient = _verified_account_email(owner_id, http_client_factory)
            if not recipient:
                _set_status_many(
                    session_factory,
                    [event["outbox_id"] for event in eligible_events],
                    "WAITING_VERIFICATION",
                    current,
                    "E-mail da conta ausente ou ainda não confirmado no Supabase.",
                )
                skipped += len(eligible_events)
                continue
            # Re-read settings and status after the external identity lookup so
            # an opt-out or later status transition closes the send race.
            fresh_events = []
            for event in eligible_events:
                current_event = _verified_and_current(session_factory, event["outbox_id"], current)
                if current_event is None:
                    _set_status(session_factory, event["outbox_id"], "SKIPPED", current, "Status ou consentimento alterado antes do envio.")
                    skipped += 1
                else:
                    fresh_events.append(current_event)
            if not fresh_events:
                continue
            event_ids_to_retry = [event["outbox_id"] for event in fresh_events]
            message = _message(str(smtp["sender"]), recipient, owner_id, fresh_events)
            with smtp_factory(str(smtp["host"]), int(smtp["port"]), timeout=10) as client:
                if bool(smtp["use_tls"]):
                    client.starttls()
                if smtp["username"]:
                    client.login(str(smtp["username"]), str(smtp["password"]))
                client.send_message(message)
            _record_sent_many(session_factory, [event["outbox_id"] for event in fresh_events], current)
            sent += 1
        except Exception as exc:
            safe_error = f"Falha temporária no envio ({type(exc).__name__})."
            _record_retry_many(
                session_factory,
                event_ids_to_retry,
                current,
                safe_error,
            )
            logger.warning("Falha no resumo de entrevistas owner_id=%s count=%s tipo=%s", owner_id, len(eligible_events), type(exc).__name__)
            retried += 1
    return {"smtp_configured": True, "sent": sent, "retried": retried, "skipped": skipped}


def cleanup_interview_email_outbox(
    db,
    now: datetime | None = None,
    max_age_days: int = FOLLOWUP_RETENTION_DAYS,
) -> int:
    """Delete interview-mail audit rows older than the default 60-day retention."""
    cutoff = (now or utc_now()) - timedelta(days=max(1, max_age_days))
    count = (
        db.query(InterviewEmailOutbox)
        .filter(InterviewEmailOutbox.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(count)
