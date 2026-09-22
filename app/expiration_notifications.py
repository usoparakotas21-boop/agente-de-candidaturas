"""Opt-in expiration alerts based only on an explicit JobPosting.validThrough.

Outbox rows retain owner/job identifiers and the structured deadline only. The
confirmed Supabase account address and the current job details are resolved
again at send time; SMTP being unavailable prevents all network activity.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Callable
from zoneinfo import ZoneInfo

import httpx

from .email_transport import select_email_transport, send_email_message
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .customer_success import (
    FOLLOWUP_BACKOFF_SECONDS,
    FOLLOWUP_MAX_ATTEMPTS,
    FOLLOWUP_RETENTION_DAYS,
    FOLLOWUP_STALE_AFTER,
    FOLLOWUP_TIMEZONE,
    _period_window,
    _public_base_url,
    _verified_account_email,
    smtp_settings,
)
from .decision_engine import normalize_preferences
from .models import Candidate, ExpiringJobEmailOutbox, Job, utc_now

logger = logging.getLogger(__name__)

EXPIRATION_NOTICE_DAYS = 7
EXPIRATION_EMAIL_BATCH_SIZE = 20
EXPIRATION_EMAIL_RETENTION_DAYS = 60
UTC = timezone.utc


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _consent_timestamp(raw: dict, now: datetime) -> str | None:
    value = raw.get("notify_expiring_consent_at")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    parsed = _as_utc(parsed)
    if parsed > _as_utc(now):
        return None
    return parsed.isoformat()


def _parse_preferences(candidate: Candidate | None, now: datetime) -> tuple[dict, bool]:
    raw: dict = {}
    if candidate and candidate.preferences_data:
        try:
            decoded = json.loads(candidate.preferences_data)
            if isinstance(decoded, dict):
                raw = decoded
        except (TypeError, ValueError):
            pass
    preferences = normalize_preferences(raw)
    consent_at = _consent_timestamp(raw, now)
    preferences["notify_expiring_consent_at"] = consent_at
    preferences["notify_expiring"] = bool(preferences["notify_expiring"] and consent_at)
    return preferences, bool(consent_at)


def _deadline_key(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="seconds")


def _owner_preferences(db, owner_id: str, now: datetime) -> tuple[dict, bool]:
    candidate = db.scalar(
        select(Candidate)
        .where(Candidate.owner_id == owner_id)
        .order_by(Candidate.id.asc())
    )
    return _parse_preferences(candidate, now)


def schedule_expiration_alerts(db, now: datetime | None = None) -> int:
    """Idempotently schedule alerts for explicitly dated jobs expiring in 7 days."""
    current = _as_utc(now or utc_now())
    owner_ids = {
        str(value)
        for value in db.scalars(
            select(Candidate.owner_id).where(Candidate.owner_id.is_not(None)).distinct()
        ).all()
        if str(value or "").strip()
    }
    if not owner_ids:
        return 0
    candidates = db.scalars(
        select(Candidate)
        .where(Candidate.owner_id.in_(owner_ids))
        .order_by(Candidate.id.asc())
    ).all()
    candidate_by_owner: dict[str, Candidate] = {}
    for candidate in candidates:
        candidate_by_owner.setdefault(str(candidate.owner_id), candidate)

    # This query uses only the structured valid_through column. It never parses
    # dates from a title, description, URL, or an inferred expiration policy.
    jobs = db.scalars(
        select(Job)
        .where(
            Job.owner_id.in_(owner_ids),
            Job.valid_through.is_not(None),
            Job.valid_through > current,
            Job.valid_through <= current + timedelta(days=EXPIRATION_NOTICE_DAYS),
        )
        .order_by(Job.owner_id.asc(), Job.id.asc())
    ).all()

    scheduled = 0
    dialect = db.get_bind().dialect.name
    for job in jobs:
        owner_id = str(job.owner_id or "").strip()
        candidate = candidate_by_owner.get(owner_id)
        if not owner_id or candidate is None or job.valid_through is None:
            continue
        preferences, has_consent = _parse_preferences(candidate, current)
        frequency = preferences["notification_frequency"]
        if not has_consent or not preferences["notify_expiring"] or frequency == "none":
            continue
        try:
            _, scheduled_at = _period_window(frequency, current)
        except ValueError:
            continue
        deadline = _as_utc(job.valid_through)
        # Do not schedule a weekly/daily digest after a near-term deadline.
        if scheduled_at >= deadline:
            scheduled_at = current
        values = {
            "owner_id": owner_id,
            "job_id": job.id,
            "deadline_key": _deadline_key(deadline),
            "frequency": frequency,
            "status": "PENDING",
            "attempt_count": 0,
            "scheduled_at": scheduled_at,
            "created_at": current,
        }
        if dialect == "postgresql":
            result = db.execute(
                pg_insert(ExpiringJobEmailOutbox)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["owner_id", "job_id", "deadline_key"]
                )
            )
            scheduled += int(result.rowcount or 0)
        elif dialect == "sqlite":
            result = db.execute(
                sqlite_insert(ExpiringJobEmailOutbox)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["owner_id", "job_id", "deadline_key"]
                )
            )
            scheduled += int(result.rowcount or 0)
        else:
            existing = db.scalar(
                select(ExpiringJobEmailOutbox).where(
                    ExpiringJobEmailOutbox.owner_id == owner_id,
                    ExpiringJobEmailOutbox.job_id == job.id,
                    ExpiringJobEmailOutbox.deadline_key == values["deadline_key"],
                )
            )
            if existing is None:
                db.add(ExpiringJobEmailOutbox(**values))
                scheduled += 1
    db.commit()
    return scheduled


def cleanup_expiration_email_outbox(
    db,
    now: datetime | None = None,
    max_age_days: int = EXPIRATION_EMAIL_RETENTION_DAYS,
) -> int:
    cutoff = _as_utc(now or utc_now()) - timedelta(days=max(1, max_age_days))
    count = (
        db.query(ExpiringJobEmailOutbox)
        .filter(ExpiringJobEmailOutbox.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(count)


def _claim_due_group(session_factory: Callable, now: datetime) -> list[int]:
    db = session_factory()
    try:
        stale_before = now - FOLLOWUP_STALE_AFTER
        retryable = (
            (ExpiringJobEmailOutbox.attempt_count < FOLLOWUP_MAX_ATTEMPTS)
            & (ExpiringJobEmailOutbox.scheduled_at <= now)
            & ExpiringJobEmailOutbox.status.in_(("PENDING", "RETRY", "WAITING_VERIFICATION"))
            & (
                (ExpiringJobEmailOutbox.status == "PENDING")
                | ExpiringJobEmailOutbox.next_attempt_at.is_(None)
                | (ExpiringJobEmailOutbox.next_attempt_at <= now)
            )
        )
        stale_sending = (
            (ExpiringJobEmailOutbox.scheduled_at <= now)
            & (ExpiringJobEmailOutbox.status == "SENDING")
            & (ExpiringJobEmailOutbox.started_at < stale_before)
        )
        due = retryable | stale_sending
        group = db.execute(
            select(
                ExpiringJobEmailOutbox.owner_id,
                ExpiringJobEmailOutbox.frequency,
                ExpiringJobEmailOutbox.scheduled_at,
            )
            .where(due)
            .order_by(ExpiringJobEmailOutbox.scheduled_at.asc(), ExpiringJobEmailOutbox.id.asc())
            .limit(1)
        ).first()
        if group is None:
            return []
        owner_id, frequency, scheduled_at = group
        if db.get_bind().dialect.name == "postgresql":
            lock_source = f"{owner_id}:{frequency}:{scheduled_at.isoformat()}".encode("utf-8")
            lock_key = int.from_bytes(hashlib.sha256(lock_source).digest()[:8], "big", signed=True)
            db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}).scalar()
        rows = db.scalars(
            select(ExpiringJobEmailOutbox)
            .where(
                ExpiringJobEmailOutbox.owner_id == owner_id,
                ExpiringJobEmailOutbox.frequency == frequency,
                ExpiringJobEmailOutbox.scheduled_at == scheduled_at,
                due,
            )
            .order_by(ExpiringJobEmailOutbox.id.asc())
            .with_for_update(skip_locked=True)
        ).all()
        claimed: list[int] = []
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
            claimed.append(row.id)
        db.commit()
        return claimed
    finally:
        db.close()


def _current_payload(db, outbox_id: int, now: datetime) -> dict | None:
    row = db.get(ExpiringJobEmailOutbox, outbox_id)
    if row is None:
        return None
    job = db.scalar(
        select(Job).where(
            Job.id == row.job_id,
            Job.owner_id == row.owner_id,
        )
    )
    if job is None or job.valid_through is None:
        return None
    deadline = _as_utc(job.valid_through)
    if _deadline_key(deadline) != row.deadline_key:
        return None
    if deadline <= now or deadline > now + timedelta(days=EXPIRATION_NOTICE_DAYS):
        return None
    preferences, has_consent = _owner_preferences(db, row.owner_id, now)
    if (
        not has_consent
        or not preferences["notify_expiring"]
        or preferences["notification_frequency"] != row.frequency
        or row.frequency == "none"
    ):
        return None
    return {
        "outbox_id": row.id,
        "owner_id": row.owner_id,
        "job_id": job.id,
        "deadline_key": row.deadline_key,
        "title": job.title,
        "company": job.company,
        "deadline": deadline,
    }


def _current_payloads(session_factory: Callable, outbox_ids: list[int], now: datetime) -> list[dict]:
    db = session_factory()
    try:
        return [
            payload
            for outbox_id in outbox_ids
            if (payload := _current_payload(db, outbox_id, now)) is not None
        ]
    finally:
        db.close()


def _set_status_many(
    session_factory: Callable,
    outbox_ids: list[int],
    status: str,
    now: datetime,
    message: str,
) -> None:
    if not outbox_ids:
        return
    db = session_factory()
    try:
        rows = db.scalars(
            select(ExpiringJobEmailOutbox).where(ExpiringJobEmailOutbox.id.in_(outbox_ids))
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


def _record_retry(session_factory: Callable, outbox_ids: list[int], now: datetime, error_code: str) -> None:
    if not outbox_ids:
        return
    db = session_factory()
    try:
        rows = db.scalars(
            select(ExpiringJobEmailOutbox).where(ExpiringJobEmailOutbox.id.in_(outbox_ids))
        ).all()
        for row in rows:
            row.started_at = None
            row.last_error = error_code[:240]
            if row.attempt_count >= FOLLOWUP_MAX_ATTEMPTS:
                row.status = "FAILED"
                row.next_attempt_at = None
            else:
                row.status = "RETRY"
                delay = FOLLOWUP_BACKOFF_SECONDS[
                    min(row.attempt_count - 1, len(FOLLOWUP_BACKOFF_SECONDS) - 1)
                ]
                row.next_attempt_at = now + timedelta(seconds=delay)
        db.commit()
    finally:
        db.close()


def _record_sent(session_factory: Callable, outbox_ids: list[int], now: datetime) -> None:
    if not outbox_ids:
        return
    db = session_factory()
    try:
        rows = db.scalars(
            select(ExpiringJobEmailOutbox).where(ExpiringJobEmailOutbox.id.in_(outbox_ids))
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


def _message(sender: str, recipient: str, owner_id: str, alerts: list[dict], now: datetime) -> EmailMessage:
    alert_keys = sorted(f"{item['job_id']}:{item['deadline_key']}" for item in alerts)
    digest = hashlib.sha256(f"{owner_id}:{'|'.join(alert_keys)}".encode("utf-8")).hexdigest()[:32]
    lines = ["Olá! Estas vagas têm uma data de encerramento informada no anúncio e podem expirar em breve:", ""]
    brazil = ZoneInfo(FOLLOWUP_TIMEZONE)
    for item in alerts:
        title = " ".join(str(item.get("title") or "Vaga").replace("\r", " ").replace("\n", " ").split())[:200]
        company = " ".join(str(item.get("company") or "Empresa não informada").replace("\r", " ").replace("\n", " ").split())[:200]
        deadline = _as_utc(item["deadline"])
        days_left = max(1, math.ceil((deadline - _as_utc(now)).total_seconds() / 86400))
        local_date = deadline.astimezone(brazil).strftime("%d/%m/%Y")
        lines.append(f"• {title} — {company} · encerra em {local_date} (aprox. {days_left} dia(s))")
    lines.extend(("", f"Revise suas oportunidades em {_public_base_url()}/vagas.", "", "Este aviso usa somente a data de validade estruturada que veio no anúncio. Você pode desligá-lo em Configurações > Alertas e rotina."))
    message = EmailMessage()
    message["Subject"] = f"{len(alerts)} vaga(s) com encerramento próximo"
    message["From"] = sender
    message["To"] = recipient
    message["Message-ID"] = f"<expiring-{digest}@candidaturacerta.com.br>"
    message.set_content("\n".join(lines))
    return message


def run_expiration_notification_cycle(
    session_factory: Callable,
    *,
    now: datetime | None = None,
    smtp_factory: Callable = smtplib.SMTP,
    http_client_factory: Callable = httpx.Client,
    max_messages: int = EXPIRATION_EMAIL_BATCH_SIZE,
) -> dict[str, int | bool]:
    """Schedule and send explicit-date alerts through the configured email transport."""
    smtp = smtp_settings()
    mail_config = select_email_transport(smtp)
    if mail_config is None:
        return {"smtp_configured": False, "email_transport_configured": False, "scheduled": 0, "sent": 0, "retried": 0, "skipped": 0}
    current = _as_utc(now or utc_now())
    db = session_factory()
    try:
        scheduled = schedule_expiration_alerts(db, current)
    finally:
        db.close()

    sent = retried = skipped = processed = 0
    while processed < max(0, max_messages):
        outbox_ids = _claim_due_group(session_factory, current)
        if not outbox_ids:
            break
        processed += 1
        eligible = _current_payloads(session_factory, outbox_ids, current)
        eligible_ids = {item["outbox_id"] for item in eligible}
        stale_ids = [value for value in outbox_ids if value not in eligible_ids]
        if stale_ids:
            _set_status_many(session_factory, stale_ids, "SKIPPED", current, "Data, consentimento ou frequência não está mais elegível.")
            skipped += len(stale_ids)
        if not eligible:
            continue

        owner_id = eligible[0]["owner_id"]
        try:
            recipient = _verified_account_email(owner_id, http_client_factory)
            if not recipient:
                _set_status_many(session_factory, list(eligible_ids), "WAITING_VERIFICATION", current, "E-mail da conta ausente ou ainda não confirmado no Supabase.")
                skipped += len(eligible_ids)
                continue
            # Re-check date and opt-in after identity lookup, immediately before SMTP.
            current_eligible = _current_payloads(session_factory, list(eligible_ids), current)
            current_ids = {item["outbox_id"] for item in current_eligible}
            revoked_ids = [value for value in eligible_ids if value not in current_ids]
            if revoked_ids:
                _set_status_many(session_factory, revoked_ids, "SKIPPED", current, "Data ou consentimento alterado antes do envio.")
                skipped += len(revoked_ids)
            if not current_eligible:
                continue
            message = _message(str(mail_config["sender"]), recipient, owner_id, current_eligible, current)
            send_email_message(message, mail_config, timeout=10, smtp_factory=smtp_factory)
            _record_sent(session_factory, [item["outbox_id"] for item in current_eligible], current)
            sent += 1
        except Exception as exc:
            code = f"Falha temporária no envio ({type(exc).__name__})."
            _record_retry(session_factory, list(eligible_ids), current, code)
            logger.warning(
                "Falha no alerta de expiração outbox_count=%d tipo=%s",
                len(eligible_ids),
                type(exc).__name__,
            )
            retried += len(eligible_ids)
    return {"smtp_configured": smtp is not None, "email_transport_configured": True, "scheduled": scheduled, "sent": sent, "retried": retried, "skipped": skipped}
