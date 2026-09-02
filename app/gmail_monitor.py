import asyncio
import base64
import html
import logging
import os
import re
from contextlib import suppress
from html.parser import HTMLParser
from typing import Any

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from .auth import authenticated_user
from .database import SessionLocal
from .gmail_integration import (
    GOOGLE_TOKEN_URL,
    _cipher,
    _client_id,
    _client_secret,
)
from .job_intake import parse_job_text
from .job_quality import assess_job_capture, split_job_alert
from .models import EmailIntegration, ProcessedEmailMessage
from .queue_service import enqueue


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/gmail", tags=["gmail"])

GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
# Search a broad recent window first and let _looks_like_job classify the
# message. Restricting Gmail's query to a fixed list of senders caused alerts
# from new companies and manual test messages to be silently skipped.
DEFAULT_QUERY = "newer_than:7d"
KNOWN_SOURCES = {
    "linkedin": "linkedin",
    "indeed": "indeed",
    "gupy": "gupy",
    "infojobs": "infojobs",
    "bebee": "bebee",
    "catho": "catho",
    "glassdoor": "glassdoor",
}
JOB_TERMS = (
    "vaga",
    "vagas",
    "oportunidade",
    "oportunidades",
    "emprego",
    "candidate-se",
    "candidatura",
    "job alert",
    "job",
    "jobs",
    "hiring",
    "recrutamento",
    "processo seletivo",
)
ROLE_TERMS = (
    "analista",
    "assistente",
    "auxiliar",
    "coordenador",
    "coordenadora",
    "supervisor",
    "supervisora",
    "gerente",
    "especialista",
    "consultor",
    "business partner",
    "recruiter",
    "diretor",
    "head de",
    "analyst",
    "coordinator",
    "manager",
    "specialist",
    "human resources",
)

_sync_lock = asyncio.Lock()
_monitor_task: asyncio.Task | None = None


class GmailSyncError(RuntimeError):
    pass


class _ReadableEmailParser(HTMLParser):
    BLOCK_TAGS = {
        "article", "br", "div", "h1", "h2", "h3", "h4", "li", "p", "section", "tr"
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.link = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a":
            self.link = next((value or "" for name, value in attrs if name == "href"), "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.link.startswith(("http://", "https://")):
            self.parts.extend(("\n", html.unescape(self.link), "\n"))
            self.link = ""
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)


def _decode_base64url(value: str) -> str:
    if not value:
        return ""
    try:
        padded = value + ("=" * (-len(value) % 4))
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _walk_parts(part: dict[str, Any]) -> tuple[list[str], list[str]]:
    plain: list[str] = []
    rich: list[str] = []
    mime_type = str(part.get("mimeType", "")).casefold()
    decoded = _decode_base64url(part.get("body", {}).get("data", ""))
    if decoded:
        if mime_type == "text/plain":
            plain.append(decoded)
        elif mime_type == "text/html":
            rich.append(decoded)
    for child in part.get("parts", []) or []:
        child_plain, child_rich = _walk_parts(child)
        plain.extend(child_plain)
        rich.extend(child_rich)
    return plain, rich


def _html_urls(value: str) -> list[str]:
    urls = re.findall(
        r'''(?is)href\s*=\s*["'](https?://[^"']+)["']''',
        value,
    )
    return [html.unescape(url).strip() for url in urls]


def _html_text(value: str) -> str:
    parser = _ReadableEmailParser()
    parser.feed(value)
    parser.close()
    return parser.text()


def _header(payload: dict[str, Any], name: str) -> str:
    wanted = name.casefold()
    for item in payload.get("headers", []) or []:
        if str(item.get("name", "")).casefold() == wanted:
            return str(item.get("value", "")).strip()
    return ""


def _message_content(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload", {}) or {}
    plain, rich = _walk_parts(payload)
    rich_text = "\n".join(_html_text(value) for value in rich if value.strip())
    plain_text = "\n".join(value for value in plain if value.strip())
    content = rich_text or plain_text
    if not content:
        content = str(message.get("snippet", ""))
    return {
        "subject": _header(payload, "Subject"),
        "sender": _header(payload, "From"),
        "content": content[:80_000],
    }


def _source_for(sender: str, content: str) -> str:
    combined = f"{sender}\n{content[:4000]}".casefold()
    for marker, source in KNOWN_SOURCES.items():
        if marker in combined:
            return source
    return "gmail"


def _looks_like_job(subject: str, sender: str, content: str) -> bool:
    subject_lower = subject.casefold()
    searchable = f"{subject}\n{sender}\n{content[:12000]}".casefold()
    has_job_term = any(term in searchable for term in JOB_TERMS)
    has_role = any(term in searchable for term in ROLE_TERMS)
    known_sender = any(marker in sender.casefold() for marker in KNOWN_SOURCES)
    return has_job_term and (has_role or known_sender or any(
        term in subject_lower for term in JOB_TERMS
    ))


async def _access_token(integration: EmailIntegration) -> str:
    try:
        refresh_token = _cipher().decrypt(
            integration.encrypted_refresh_token.encode("ascii")
        ).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise GmailSyncError("Token Gmail armazenado nao pode ser aberto.") from exc

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code != 200:
        raise GmailSyncError("Google recusou a renovacao do acesso ao Gmail.")
    access_token = response.json().get("access_token")
    if not access_token:
        raise GmailSyncError("Google nao retornou um token temporario.")
    return str(access_token)


async def _list_message_ids(access_token: str) -> list[str]:
    query = os.getenv("GMAIL_JOB_QUERY", DEFAULT_QUERY).strip() or DEFAULT_QUERY
    max_results = min(max(int(os.getenv("GMAIL_MAX_RESULTS", "25")), 1), 100)
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.get(
            GMAIL_MESSAGES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": query, "maxResults": max_results},
        )
    if response.status_code != 200:
        raise GmailSyncError("Nao foi possivel pesquisar mensagens no Gmail.")
    return [
        str(item["id"])
        for item in response.json().get("messages", [])
        if item.get("id")
    ]


async def _get_message(access_token: str, message_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.get(
            f"{GMAIL_MESSAGES_URL}/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"},
        )
    if response.status_code != 200:
        raise GmailSyncError("Nao foi possivel ler uma mensagem selecionada.")
    return response.json()


def _already_processed(integration_id: int, message_ids: list[str]) -> set[str]:
    if not message_ids:
        return set()
    db = SessionLocal()
    try:
        return set(
            db.scalars(
                select(ProcessedEmailMessage.provider_message_id).where(
                    ProcessedEmailMessage.integration_id == integration_id,
                    ProcessedEmailMessage.provider_message_id.in_(message_ids),
                )
            ).all()
        )
    finally:
        db.close()


def _record_result(
    integration: EmailIntegration,
    message_id: str,
    subject: str,
    sender: str,
    status: str,
    *,
    job_id: int | None = None,
    queue_item_id: int | None = None,
    error: str = "",
) -> None:
    db = SessionLocal()
    try:
        processed = ProcessedEmailMessage(
            integration_id=integration.id,
            owner_id=integration.owner_id,
            provider_message_id=message_id,
            subject=subject[:500],
            sender=sender[:500],
            status=status,
            job_id=job_id,
            error=error[:1000] or None,
        )
        db.add(processed)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def sync_integration(integration: EmailIntegration) -> dict[str, int]:
    access_token = await _access_token(integration)
    message_ids = await _list_message_ids(access_token)
    processed = _already_processed(integration.id, message_ids)
    counters = {
        "found": len(message_ids),
        "new": 0,
        "candidates": 0,
        "captured": 0,
        "duplicate": 0,
        "review": 0,
        "ignored": 0,
        "errors": 0,
        "queue": 0,
    }

    for message_id in reversed(message_ids):
        if message_id in processed:
            continue
        counters["new"] += 1
        subject = ""
        sender = ""
        try:
            message = await _get_message(access_token, message_id)
            parsed = _message_content(message)
            subject = parsed["subject"]
            sender = parsed["sender"]
            content = parsed["content"]
            if not _looks_like_job(subject, sender, content):
                _record_result(
                    integration,
                    message_id,
                    subject,
                    sender,
                    "IGNORED",
                )
                counters["ignored"] += 1
                continue

            source = _source_for(sender, content)
            blocks = split_job_alert(subject, content)
            counters["candidates"] += len(blocks)
            outcomes: list[str] = []
            job_ids: list[int] = []
            queue_ids: list[int] = []
            message_captured = 0
            message_duplicates = 0
            message_reviews = 0
            message_ignored = 0
            message_queued = 0

            for index, raw_text in enumerate(blocks, start=1):
                try:
                    # Parsear a vaga
                    parsed_job = parse_job_text(raw_text, source)
                    
                    # Avaliar qualidade
                    quality = assess_job_capture(parsed_job)
                    
                    # Preparar dados para a fila
                    captured_data = {
                        "health_score": quality.get("health", {}).get("score"),
                        "health_band": quality.get("health", {}).get("band"),
                        "health_signals": quality.get("health", {}).get("signals", []),
                        "fraud_suspected": quality.get("health", {}).get("fraud_suspected", False),

                        "title": parsed_job.get("title"),
                        "company": parsed_job.get("company"),
                        "location": parsed_job.get("location"),
                        "modality": parsed_job.get("modality"),
                        "url": parsed_job.get("url"),
                        "description": parsed_job.get("description"),
                        "raw_excerpt": raw_text[:2000],
                        "confidence_title": quality.get("confidence_title"),
                        "confidence_company": quality.get("confidence_company"),
                        "confidence_description": quality.get("confidence_description"),
                        "confidence_url": quality.get("confidence_url"),
                        "confidence_overall": quality.get("confidence"),
                    }
                    
                    decision_result = {
                        "decision": quality.get("decision", "REVISAR"),
                        "reasons": quality.get("reasons", []),
                        "engine_version": "0.23.0",
                        "score": quality.get("score"),
                    }
                    
                except ValueError as exc:
                    message_ignored += 1
                    outcomes.append(f"vaga {index}: DESCARTAR ({exc})")
                    continue

                # Enfileirar a vaga
                db = SessionLocal()
                try:
                    item, created = enqueue(
                        session=db,
                        owner_id=integration.owner_id,
                        captured=captured_data,
                        decision_result=decision_result,
                        source="gmail",
                        source_ref=message_id,
                    )
                    db.commit()
                    
                    if created:
                        message_queued += 1
                        queue_ids.append(item.id)
                        if item.job_id:
                            job_ids.append(item.job_id)
                            message_captured += 1
                        elif item.decision == "REVISAR":
                            message_reviews += 1
                        else:
                            message_ignored += 1
                    else:
                        message_duplicates += 1
                        
                except Exception as exc:
                    db.rollback()
                    logger.error("Erro ao enfileirar vaga: %s", exc)
                    message_ignored += 1
                    outcomes.append(f"vaga {index}: ERRO ({exc})")
                finally:
                    db.close()

                reason = ", ".join(decision_result.get("reasons", [])) or "campos essenciais validados"
                outcomes.append(
                    f"vaga {index}: {decision_result['decision']} "
                    f"({captured_data.get('confidence_overall', 0)}%; {reason})"
                )

            counters["captured"] += message_captured
            counters["duplicate"] += message_duplicates
            counters["review"] += message_reviews
            counters["ignored"] += message_ignored
            counters["queue"] += message_queued

            if message_captured and (message_reviews or message_ignored):
                status = "CAPTURED_PARTIAL"
            elif message_captured > 1:
                status = "CAPTURED_MULTIPLE"
            elif message_captured == 1:
                status = "CAPTURED"
            elif message_duplicates:
                status = "DUPLICATE"
            elif message_reviews:
                status = "REVIEW_REQUIRED"
            else:
                status = "IGNORED_LOW_QUALITY"
            _record_result(
                integration,
                message_id,
                subject,
                sender,
                status,
                job_id=job_ids[0] if job_ids else None,
                error=" | ".join(outcomes),
            )
        except Exception as exc:
            logger.warning("Falha ao processar mensagem Gmail %s: %s", message_id, type(exc).__name__)
            _record_result(
                integration,
                message_id,
                subject,
                sender,
                "ERROR",
                error=str(getattr(exc, "detail", exc)),
            )
            counters["errors"] += 1
    return counters


async def sync_owner(owner_id: str) -> dict[str, int]:
    db = SessionLocal()
    try:
        integration = db.scalar(
            select(EmailIntegration).where(
                EmailIntegration.owner_id == owner_id,
                EmailIntegration.provider == "gmail",
            )
        )
        if integration is None:
            raise HTTPException(status_code=409, detail="Conecte o Gmail primeiro.")
        db.expunge(integration)
    finally:
        db.close()
    async with _sync_lock:
        return await sync_integration(integration)


async def sync_all_integrations() -> None:
    db = SessionLocal()
    try:
        integrations = list(db.scalars(select(EmailIntegration)).all())
        for integration in integrations:
            db.expunge(integration)
    finally:
        db.close()
    async with _sync_lock:
        for integration in integrations:
            try:
                await sync_integration(integration)
            except Exception as exc:
                logger.warning(
                    "Sincronizacao Gmail falhou para integracao %s: %s",
                    integration.id,
                    type(exc).__name__,
                )


async def _monitor_loop() -> None:
    initial_delay = max(int(os.getenv("GMAIL_INITIAL_DELAY_SECONDS", "15")), 1)
    interval = max(int(os.getenv("GMAIL_POLL_SECONDS", "300")), 60)
    await asyncio.sleep(initial_delay)
    while True:
        await sync_all_integrations()
        await asyncio.sleep(interval)


def start_monitor() -> None:
    global _monitor_task
    enabled = os.getenv("GMAIL_AUTO_SYNC", "false").casefold() == "true"
    if enabled and (_monitor_task is None or _monitor_task.done()):
        _monitor_task = asyncio.create_task(_monitor_loop())


async def stop_monitor() -> None:
    global _monitor_task
    if _monitor_task is not None:
        _monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await _monitor_task
        _monitor_task = None


@router.post("/sync")
async def synchronize_gmail_now(
    user: dict = Depends(authenticated_user),
):
    owner_id = str(user.get("id", ""))
    if not owner_id:
        raise HTTPException(status_code=409, detail="Login necessario.")
    return await sync_owner(owner_id)
