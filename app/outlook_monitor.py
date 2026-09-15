import asyncio
import base64
import logging
import os
from contextlib import suppress
from typing import Any

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from .auth import authenticated_user
from .database import SessionLocal
from .gmail_monitor import (
    _message_content,
    sync_integration,
)
from .models import EmailIntegration
from .outlook_integration import TOKEN_URL, _cipher, _secret

router = APIRouter(prefix="/auth/outlook", tags=["outlook"])
OUTLOOK_MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
_sync_lock = asyncio.Lock()
_monitor_task: asyncio.Task | None = None
logger = logging.getLogger(__name__)


class OutlookSyncError(RuntimeError):
    pass


async def _access_token(integration: EmailIntegration) -> str:
    try:
        refresh = _cipher().decrypt(integration.encrypted_refresh_token.encode("ascii")).decode()
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise OutlookSyncError("Token Outlook armazenado nao pode ser aberto.") from exc
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": os.getenv("OUTLOOK_CLIENT_ID", ""),
                "client_secret": _secret(),
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code != 200:
        raise OutlookSyncError("Microsoft recusou a renovacao do acesso ao Outlook.")
    token = response.json().get("access_token")
    if not token:
        raise OutlookSyncError("Microsoft nao retornou um token temporario.")
    return str(token)


async def _list_message_ids(access_token: str) -> list[str]:
    top = min(max(int(os.getenv("OUTLOOK_MAX_RESULTS", "25")), 1), 100)
    params = {
        "$top": top,
        "$orderby": "receivedDateTime desc",
        "$select": "id",
    }
    since = os.getenv("OUTLOOK_SINCE", "").strip()
    if since:
        params["$filter"] = "receivedDateTime ge " + since
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.get(
            OUTLOOK_MESSAGES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
    if response.status_code != 200:
        raise OutlookSyncError("Nao foi possivel pesquisar mensagens no Outlook.")
    return [str(item["id"]) for item in response.json().get("value", []) if item.get("id")]


def _graph_to_message(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("body") or {}
    content = str(body.get("content") or payload.get("bodyPreview") or "")
    content_type = str(body.get("contentType") or "text").casefold()
    encoded = base64.urlsafe_b64encode(content.encode("utf-8")).decode("ascii").rstrip("=")
    sender = ((payload.get("from") or {}).get("emailAddress") or {})
    sender_text = sender.get("name") or sender.get("address") or ""
    return {
        "payload": {
            "headers": [
                {"name": "Subject", "value": str(payload.get("subject") or "")},
                {"name": "From", "value": sender_text},
            ],
            "mimeType": "text/html" if content_type == "html" else "text/plain",
            "body": {"data": encoded},
        },
        "snippet": str(payload.get("bodyPreview") or ""),
    }


async def _get_message(access_token: str, message_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.get(
            f"https://graph.microsoft.com/v1.0/me/messages/{message_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": 'outlook.body-content-type="html"',
            },
            params={"$select": "id,subject,from,body,bodyPreview,receivedDateTime"},
        )
    if response.status_code != 200:
        raise OutlookSyncError("Nao foi possivel ler uma mensagem selecionada do Outlook.")
    return _graph_to_message(response.json())


async def sync_owner(owner_id: str) -> dict[str, int]:
    db = SessionLocal()
    try:
        integration = db.scalar(select(EmailIntegration).where(
            EmailIntegration.owner_id == owner_id,
            EmailIntegration.provider == "outlook",
        ))
        if integration is None:
            raise HTTPException(status_code=409, detail="Conecte o Outlook primeiro.")
        db.expunge(integration)
    finally:
        db.close()
    async with _sync_lock:
        token = await _access_token(integration)
        return await sync_integration(
            integration,
            access_token=token,
            list_message_ids=_list_message_ids,
            get_message=_get_message,
            source_name="outlook",
            provider_label="Outlook",
        )


async def sync_all_integrations() -> None:
    db = SessionLocal()
    try:
        integrations = list(db.scalars(select(EmailIntegration).where(EmailIntegration.provider == "outlook")).all())
        for integration in integrations:
            db.expunge(integration)
    finally:
        db.close()
    for integration in integrations:
        try:
            async with _sync_lock:
                token = await _access_token(integration)
                await sync_integration(integration, access_token=token, list_message_ids=_list_message_ids, get_message=_get_message, source_name="outlook", provider_label="Outlook")
        except Exception as exc:
            logger.warning(
                "Sincronizacao Outlook falhou para integracao %s: %s - %s",
                integration.id,
                type(exc).__name__,
                str(exc)[:300],
            )


async def _monitor_loop() -> None:
    await asyncio.sleep(max(int(os.getenv("OUTLOOK_INITIAL_DELAY_SECONDS", "15")), 1))
    while True:
        await sync_all_integrations()
        await asyncio.sleep(max(int(os.getenv("OUTLOOK_POLL_SECONDS", "300")), 60))


def start_monitor() -> None:
    global _monitor_task
    if os.getenv("OUTLOOK_AUTO_SYNC", "false").casefold() == "true" and (_monitor_task is None or _monitor_task.done()):
        _monitor_task = asyncio.create_task(_monitor_loop())


async def stop_monitor() -> None:
    global _monitor_task
    if _monitor_task is not None:
        _monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await _monitor_task
        _monitor_task = None


@router.post("/sync")
async def synchronize_outlook_now(user: dict = Depends(authenticated_user)):
    owner_id = str(user.get("id", ""))
    if not owner_id:
        raise HTTPException(status_code=409, detail="Login necessario.")
    return await sync_owner(owner_id)
