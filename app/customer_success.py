"""Opt-in lifecycle mail for overdue application follow-ups.

Only the authenticated Supabase account address is eligible as a recipient.
The durable outbox stores owner/application identifiers, never an email address.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Callable
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import joinedload, selectinload

from .decision_engine import normalize_preferences
from .models import Application, Candidate, FollowupEmailOutbox, Job, utc_now

logger = logging.getLogger(__name__)

FOLLOWUP_AFTER_DAYS = 7
FOLLOWUP_TIMEZONE = "America/Sao_Paulo"
FOLLOWUP_DAILY_HOUR = 9
FOLLOWUP_IMMEDIATE_BUCKET_SECONDS = 300
FOLLOWUP_POLL_SECONDS = 300
FOLLOWUP_MAX_ATTEMPTS = 5
FOLLOWUP_STALE_AFTER = timedelta(minutes=15)
FOLLOWUP_BACKOFF_SECONDS = (30, 120, 600, 1800)
FOLLOWUP_RETENTION_DAYS = 60
FOLLOWUP_BATCH_SIZE = 50


def smtp_settings() -> dict[str, object] | None:
    """Return authenticated SMTP settings only when all required credentials exist."""
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    if not host or not sender or not username or not password:
        return None
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except (TypeError, ValueError):
        port = 587
    return {
        "host": host,
        "port": port,
        "sender": sender,
        "username": username,
        "password": password,
        "use_tls": os.getenv("SMTP_USE_TLS", "true").strip().casefold() != "false",
    }


def _aware(value: datetime, reference: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=reference.tzinfo or timezone.utc)
    return value


def _last_submission_at(application: Application, now: datetime) -> datetime | None:
    submitted = [_aware(event.created_at, now) for event in application.events if event.status == "CANDIDATURA_ENVIADA"]
    value = max(submitted, default=None)
    if value is None and application.status == "CANDIDATURA_ENVIADA":
        value = application.updated_at or application.created_at
    return _aware(value, now) if value is not None else None


def _period_window(frequency: str, now: datetime) -> tuple[str, datetime]:
    """Choose a deterministic digest window; all app instances use the same key."""
    zone = ZoneInfo(FOLLOWUP_TIMEZONE)
    local_now = now.astimezone(zone)
    if frequency == "immediate":
        epoch = int(now.timestamp())
        bucket = epoch - (epoch % FOLLOWUP_IMMEDIATE_BUCKET_SECONDS)
        scheduled = datetime.fromtimestamp(bucket, tz=timezone.utc)
        return f"immediate:{bucket}", scheduled
    slot = local_now.replace(hour=FOLLOWUP_DAILY_HOUR, minute=0, second=0, microsecond=0)
    if frequency == "daily":
        if local_now > slot:
            slot += timedelta(days=1)
        return f"daily:{slot.date().isoformat()}", slot.astimezone(timezone.utc)
    if frequency == "weekly":
        days_to_monday = (7 - local_now.weekday()) % 7
        slot += timedelta(days=days_to_monday)
        if local_now > slot:
            slot += timedelta(days=7)
        iso = slot.isocalendar()
        return f"weekly:{iso.year}-W{iso.week:02d}", slot.astimezone(timezone.utc)
    raise ValueError("Frequência de notificação não suportada.")


def _current_period_key(frequency: str, now: datetime) -> str | None:
    zone = ZoneInfo(FOLLOWUP_TIMEZONE)
    local = now.astimezone(zone)
    if frequency == "daily":
        return f"daily:{local.date().isoformat()}"
    if frequency == "weekly":
        iso = local.isocalendar()
        return f"weekly:{iso.year}-W{iso.week:02d}"
    return None


def _get_or_create_digest(db, owner_id: str, frequency: str, now: datetime) -> FollowupEmailOutbox | None:
    period_key, scheduled_at = _period_window(frequency, now)
    current_key = _current_period_key(frequency, now)
    dialect = db.get_bind().dialect.name

    def get_locked(key: str):
        return db.scalar(
            select(FollowupEmailOutbox)
            .where(
                FollowupEmailOutbox.owner_id == owner_id,
                FollowupEmailOutbox.period_key == key,
            )
            .with_for_update()
        )

    # Include newly overdue rows in today's/this week's digest if it is still
    # pending. Once claimed or sent, the next frequency window is used.
    if current_key and current_key != period_key:
        current = get_locked(current_key)
        if current and current.status in {"PENDING", "RETRY", "WAITING_VERIFICATION"}:
            return current

    for _ in range(3):
        row = get_locked(period_key)
        if row is not None:
            if row.status in {"PENDING", "RETRY", "WAITING_VERIFICATION"}:
                return row
            if frequency == "immediate":
                period_key, scheduled_at = _period_window(frequency, scheduled_at + timedelta(seconds=FOLLOWUP_IMMEDIATE_BUCKET_SECONDS))
            else:
                slot = scheduled_at + (timedelta(days=1) if frequency == "daily" else timedelta(days=7))
                if frequency == "daily":
                    period_key = f"daily:{slot.astimezone(ZoneInfo(FOLLOWUP_TIMEZONE)).date().isoformat()}"
                else:
                    iso = slot.astimezone(ZoneInfo(FOLLOWUP_TIMEZONE)).isocalendar()
                    period_key = f"weekly:{iso.year}-W{iso.week:02d}"
                scheduled_at = slot
            continue

        values = {
            "owner_id": owner_id,
            "period_key": period_key,
            "frequency": frequency,
            "application_ids": [],
            "status": "PENDING",
            "attempt_count": 0,
            "scheduled_at": scheduled_at,
            "created_at": now,
        }
        if dialect == "postgresql":
            statement = pg_insert(FollowupEmailOutbox).values(**values).on_conflict_do_nothing(
                index_elements=["owner_id", "period_key"]
            )
        elif dialect == "sqlite":
            statement = sqlite_insert(FollowupEmailOutbox).values(**values).on_conflict_do_nothing(
                index_elements=["owner_id", "period_key"]
            )
        else:
            statement = None
        if statement is not None:
            db.execute(statement)
            db.flush()
            row = get_locked(period_key)
        else:
            row = FollowupEmailOutbox(**values)
            db.add(row)
            db.flush()
        if row and row.status in {"PENDING", "RETRY", "WAITING_VERIFICATION"}:
            return row
        if frequency == "immediate":
            period_key, scheduled_at = _period_window(frequency, scheduled_at + timedelta(seconds=FOLLOWUP_IMMEDIATE_BUCKET_SECONDS))
        else:
            scheduled_at += timedelta(days=1 if frequency == "daily" else 7)
            if frequency == "daily":
                period_key = f"daily:{scheduled_at.astimezone(ZoneInfo(FOLLOWUP_TIMEZONE)).date().isoformat()}"
            else:
                iso = scheduled_at.astimezone(ZoneInfo(FOLLOWUP_TIMEZONE)).isocalendar()
                period_key = f"weekly:{iso.year}-W{iso.week:02d}"
    return None


def schedule_followup_digests(db, now: datetime | None = None) -> int:
    """Create or extend owner/frequency outbox rows for due applications."""
    current = now or utc_now()
    applications = db.scalars(
        select(Application)
        .join(Application.job)
        .options(joinedload(Application.job), selectinload(Application.events))
        .where(
            Application.status == "CANDIDATURA_ENVIADA",
            Application.followup_notified_at.is_(None),
            Application.followup_notification_outbox_id.is_(None),
            Job.owner_id.is_not(None),
        )
        .order_by(Application.id.asc())
    ).unique().all()
    if not applications:
        return 0

    owner_ids = {str(application.job.owner_id) for application in applications if application.job.owner_id}
    candidates = db.scalars(
        select(Candidate)
        .where(Candidate.owner_id.in_(owner_ids))
        .order_by(Candidate.id.asc())
    ).all() if owner_ids else []
    candidate_by_owner: dict[str, Candidate] = {}
    for candidate in candidates:
        candidate_by_owner.setdefault(str(candidate.owner_id), candidate)

    due_by_owner: dict[str, list[Application]] = {}
    frequency_by_owner: dict[str, str] = {}
    for application in applications:
        owner_id = str(application.job.owner_id or "").strip()
        candidate = candidate_by_owner.get(owner_id)
        if not owner_id or candidate is None:
            continue
        raw_preferences = {}
        if candidate.preferences_data:
            try:
                raw_preferences = json.loads(candidate.preferences_data)
            except (TypeError, ValueError):
                raw_preferences = {}
        preferences = normalize_preferences(raw_preferences)
        frequency = preferences["notification_frequency"]
        if not preferences["notify_followups"] or frequency == "none":
            continue
        sent_at = _last_submission_at(application, current)
        if sent_at is None or current - sent_at < timedelta(days=FOLLOWUP_AFTER_DAYS):
            continue
        due_by_owner.setdefault(owner_id, []).append(application)
        frequency_by_owner[owner_id] = frequency

    scheduled = 0
    for owner_id, due_apps in due_by_owner.items():
        frequency = frequency_by_owner[owner_id]
        for application in due_apps:
            # Serialize assignment of each application so simultaneous Render
            # instances cannot put it into two digest periods.
            locked_app = db.scalar(
                select(Application).where(Application.id == application.id).with_for_update()
            )
            if (
                locked_app is None
                or locked_app.followup_notified_at is not None
                or locked_app.followup_notification_outbox_id is not None
                or locked_app.status != "CANDIDATURA_ENVIADA"
            ):
                continue
            row = _get_or_create_digest(db, owner_id, frequency, current)
            if row is None or row.status not in {"PENDING", "RETRY"}:
                continue
            app_ids = list(row.application_ids or [])
            if application.id not in app_ids:
                app_ids.append(application.id)
                row.application_ids = sorted(set(int(value) for value in app_ids))
            locked_app.followup_notification_outbox_id = row.id
            scheduled += 1
    db.commit()
    return scheduled


def cleanup_followup_email_outbox(db, now: datetime | None = None, max_age_days: int = FOLLOWUP_RETENTION_DAYS) -> int:
    """Delete lifecycle outbox data after the configured retention period."""
    cutoff = (now or utc_now()) - timedelta(days=max(1, max_age_days))
    expired = db.scalars(
        select(FollowupEmailOutbox).where(FollowupEmailOutbox.created_at < cutoff)
    ).all()
    if not expired:
        return 0
    ids = [row.id for row in expired]
    db.execute(
        update(Application)
        .where(Application.followup_notification_outbox_id.in_(ids))
        .values(followup_notification_outbox_id=None)
    )
    count = db.query(FollowupEmailOutbox).filter(FollowupEmailOutbox.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return int(count)


def _auth_admin_config() -> tuple[str, str] | None:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return (url, key) if url.startswith("https://") and key else None


def _verified_account_email(owner_id: str, http_client_factory: Callable = httpx.Client) -> str | None:
    """Fetch and verify the owner identity through Supabase Admin, without logging its email."""
    config = _auth_admin_config()
    if config is None:
        raise RuntimeError("SUPABASE_ADMIN_NOT_CONFIGURED")
    supabase_url, service_key = config
    with http_client_factory(timeout=10.0) as client:
        response = client.get(
            f"{supabase_url}/auth/v1/admin/users/{quote(owner_id, safe='')}",
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        )
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise RuntimeError(f"SUPABASE_ADMIN_HTTP_{response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("SUPABASE_ADMIN_INVALID_RESPONSE")
    account = payload.get("user") if isinstance(payload.get("user"), dict) else payload
    if str(account.get("id") or "") != owner_id:
        return None
    if not (account.get("email_confirmed_at") or account.get("confirmed_at")):
        return None
    email = str(account.get("email") or "").strip()
    return email if "@" in email and "\r" not in email and "\n" not in email else None


def _public_base_url() -> str:
    configured = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if configured.startswith("https://"):
        return configured
    return "https://candidaturacerta.com.br"


def _render_digest_message(sender: str, recipient: str, owner_id: str, period_key: str, apps: list[dict]) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"Lembrete: {len(apps)} candidatura(s) sem retorno"
    message["From"] = sender
    message["To"] = recipient
    digest_id = hashlib.sha256(f"{owner_id}:{period_key}".encode("utf-8")).hexdigest()[:32]
    message["Message-ID"] = f"<followup-{digest_id}@candidaturacerta.com.br>"
    lines = [
        "Olá! Estas candidaturas estão há pelo menos 7 dias sem retorno:",
        "",
    ]
    for item in apps:
        title = str(item.get("title") or "Vaga")[:200].replace("\r", " ").replace("\n", " ")
        company = str(item.get("company") or "Empresa não informada")[:200].replace("\r", " ").replace("\n", " ")
        lines.append(f"• {title} — {company} ({item['days_waiting']} dias)")
    lines.extend(("", f"Revise e acompanhe suas candidaturas em {_public_base_url()}/candidaturas.", "", "Você pode alterar estes lembretes em Configurações > Alertas e rotina."))
    message.set_content("\n".join(lines))
    return message


def _current_digest_apps(db, outbox: FollowupEmailOutbox, now: datetime) -> tuple[list[Application], str | None]:
    ids = sorted({int(value) for value in (outbox.application_ids or []) if str(value).isdigit()})
    if not ids:
        return [], None
    applications = db.scalars(
        select(Application)
        .join(Application.job)
        .options(joinedload(Application.job), selectinload(Application.events))
        .where(
            Application.id.in_(ids),
            Job.owner_id == outbox.owner_id,
        )
        .order_by(Application.id.asc())
    ).unique().all()
    due = []
    for application in applications:
        sent_at = _last_submission_at(application, now)
        if (
            application.status == "CANDIDATURA_ENVIADA"
            and application.followup_notified_at is None
            and (application.followup_notification_outbox_id in (None, outbox.id))
            and sent_at is not None
            and now - sent_at >= timedelta(days=FOLLOWUP_AFTER_DAYS)
        ):
            due.append(application)
    candidate = db.scalar(
        select(Candidate)
        .where(Candidate.owner_id == outbox.owner_id)
        .order_by(Candidate.id.asc())
    )
    raw = {}
    if candidate and candidate.preferences_data:
        try:
            raw = json.loads(candidate.preferences_data)
        except (TypeError, ValueError):
            raw = {}
    prefs = normalize_preferences(raw)
    if not prefs["notify_followups"] or prefs["notification_frequency"] != outbox.frequency:
        return [], None
    return due, prefs["notification_frequency"]


def _set_outbox_skipped(session_factory: Callable, outbox_id: int, message: str) -> None:
    db = session_factory()
    try:
        row = db.get(FollowupEmailOutbox, outbox_id)
        if row is None:
            return
        db.execute(
            update(Application)
            .where(Application.followup_notification_outbox_id == row.id)
            .values(followup_notification_outbox_id=None)
        )
        row.status = "SKIPPED"
        row.started_at = None
        row.next_attempt_at = None
        row.last_error = message[:240]
        db.commit()
    finally:
        db.close()


def _set_waiting_verification(session_factory: Callable, outbox_id: int, now: datetime) -> None:
    """Keep the assignment and recheck a missing/unconfirmed account daily."""
    db = session_factory()
    try:
        row = db.get(FollowupEmailOutbox, outbox_id)
        if row is None:
            return
        row.status = "WAITING_VERIFICATION"
        row.attempt_count = max(0, row.attempt_count - 1)
        row.started_at = None
        row.next_attempt_at = now + timedelta(days=1)
        row.last_error = "E-mail da conta ausente ou ainda não confirmado no Supabase."
        db.commit()
    finally:
        db.close()


def _record_retry(session_factory: Callable, outbox_id: int, now: datetime, error_code: str) -> None:
    db = session_factory()
    try:
        row = db.get(FollowupEmailOutbox, outbox_id)
        if row is None:
            return
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


def _record_sent(session_factory: Callable, outbox_id: int, now: datetime) -> None:
    db = session_factory()
    try:
        row = db.get(FollowupEmailOutbox, outbox_id)
        if row is None:
            return
        row.status = "SENT"
        row.sent_at = now
        row.started_at = None
        row.next_attempt_at = None
        row.last_error = None
        db.execute(
            update(Application)
            .where(Application.followup_notification_outbox_id == row.id)
            .values(
                followup_notified_at=now,
                followup_notification_outbox_id=None,
            )
        )
        db.commit()
    finally:
        db.close()


def _claim_one_due(session_factory: Callable, now: datetime) -> int | None:
    db = session_factory()
    try:
        stale_before = now - FOLLOWUP_STALE_AFTER
        row = db.scalar(
            select(FollowupEmailOutbox)
            .where(
                FollowupEmailOutbox.attempt_count < FOLLOWUP_MAX_ATTEMPTS,
                FollowupEmailOutbox.scheduled_at <= now,
                (
                    ((FollowupEmailOutbox.status == "PENDING") | (FollowupEmailOutbox.status == "RETRY") | (FollowupEmailOutbox.status == "WAITING_VERIFICATION"))
                    & (
                        (FollowupEmailOutbox.status == "PENDING")
                        | (FollowupEmailOutbox.next_attempt_at.is_(None))
                        | (FollowupEmailOutbox.next_attempt_at <= now)
                    )
                )
                | (
                    (FollowupEmailOutbox.status == "SENDING")
                    & (FollowupEmailOutbox.started_at < stale_before)
                ),
            )
            .order_by(FollowupEmailOutbox.scheduled_at.asc(), FollowupEmailOutbox.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        if row.status == "SENDING" and row.started_at is not None and row.started_at >= stale_before:
            return None
        row.status = "SENDING"
        row.started_at = now
        row.attempt_count += 1
        db.commit()
        return row.id
    finally:
        db.close()


def run_followup_digest_cycle(
    session_factory: Callable,
    *,
    now: datetime | None = None,
    smtp_factory: Callable = smtplib.SMTP,
    http_client_factory: Callable = httpx.Client,
    max_digests: int = 20,
) -> dict[str, int | bool]:
    """Schedule and deliver due digests; SMTP absence blocks all network I/O."""
    smtp = smtp_settings()
    if smtp is None:
        return {"smtp_configured": False, "scheduled": 0, "sent": 0, "retried": 0, "skipped": 0}
    current = now or utc_now()
    db = session_factory()
    try:
        scheduled = schedule_followup_digests(db, current)
    finally:
        db.close()

    sent = retried = skipped = processed = 0
    while processed < max(0, max_digests):
        outbox_id = _claim_one_due(session_factory, current)
        if outbox_id is None:
            break
        processed += 1
        db = session_factory()
        try:
            outbox = db.get(FollowupEmailOutbox, outbox_id)
            if outbox is None:
                skipped += 1
                continue
            due_apps, frequency = _current_digest_apps(db, outbox, current)
            owner_id = outbox.owner_id
            period_key = outbox.period_key
            if not due_apps or frequency is None:
                db.close()
                _set_outbox_skipped(session_factory, outbox_id, "Sem candidaturas elegíveis ou lembrete desativado.")
                skipped += 1
                continue
            app_payload = [
                {
                    "title": app.job.title,
                    "company": app.job.company,
                    "days_waiting": max(7, (current - _last_submission_at(app, current)).days),
                }
                for app in due_apps
            ]
        finally:
            if db.is_active:
                db.close()

        try:
            recipient = _verified_account_email(owner_id, http_client_factory)
            if not recipient:
                _set_waiting_verification(session_factory, outbox_id, current)
                skipped += 1
                continue
            message = _render_digest_message(str(smtp["sender"]), recipient, owner_id, period_key, app_payload)
            with smtp_factory(str(smtp["host"]), int(smtp["port"]), timeout=10) as client:
                if bool(smtp["use_tls"]):
                    client.starttls()
                if smtp["username"]:
                    client.login(str(smtp["username"]), str(smtp["password"]))
                client.send_message(message)
            _record_sent(session_factory, outbox_id, current)
            sent += 1
        except Exception as exc:
            # Keep error details private; exception strings may contain SMTP
            # addresses, auth fragments, or provider response text.
            code = f"Falha temporária no envio ({type(exc).__name__})."
            _record_retry(session_factory, outbox_id, current, code)
            logger.warning("Falha no digest de follow-up outbox_id=%s tipo=%s", outbox_id, type(exc).__name__)
            retried += 1
    return {"smtp_configured": True, "scheduled": scheduled, "sent": sent, "retried": retried, "skipped": skipped}
