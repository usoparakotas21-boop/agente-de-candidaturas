import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from .auth import authenticated_user
from .database import SessionLocal
from .models import EmailIntegration


router = APIRouter(prefix="/auth/gmail", tags=["gmail"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def _client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.getenv("GOOGLE_CLIENT_SECRET", "").strip()


def _redirect_uri() -> str:
    configured = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if configured:
        return configured
    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    return f"{base_url}/auth/gmail/callback"


def _configuration_ready() -> bool:
    return bool(_client_id() and _client_secret() and os.getenv("TOKEN_ENCRYPTION_KEY"))


def _require_configuration() -> None:
    if not _configuration_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Gmail ainda nao configurado. Defina GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET e TOKEN_ENCRYPTION_KEY."
            ),
        )


def _owner_id(user: dict) -> str:
    owner_id = user.get("id") if isinstance(user, dict) else None
    if not owner_id:
        raise HTTPException(
            status_code=409,
            detail="Ative o login do sistema antes de conectar o Gmail.",
        )
    return str(owner_id)


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _urlsafe_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _state_secret() -> bytes:
    secret = os.getenv("OAUTH_STATE_SECRET", "").strip() or _client_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="OAuth ainda nao configurado.")
    return secret.encode("utf-8")


def _create_state(owner_id: str) -> str:
    payload = {
        "sub": owner_id,
        "exp": int(time.time()) + 600,
        "nonce": secrets.token_urlsafe(18),
    }
    body = _urlsafe_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = _urlsafe_encode(
        hmac.new(_state_secret(), body.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{body}.{signature}"


def _validate_state(state: str, owner_id: str) -> None:
    try:
        body, supplied_signature = state.split(".", 1)
        expected_signature = _urlsafe_encode(
            hmac.new(_state_secret(), body.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("invalid signature")
        payload = json.loads(_urlsafe_decode(body))
        if payload.get("sub") != owner_id or int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired or wrong user")
    except (
        AttributeError,
        binascii.Error,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        raise HTTPException(
            status_code=400,
            detail="A autorizacao do Gmail expirou ou e invalida. Tente novamente.",
        )


def _cipher() -> Fernet:
    key = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="TOKEN_ENCRYPTION_KEY ausente ou invalida.",
        )


@router.get("/start")
async def start_gmail_authorization(
    user: dict = Depends(authenticated_user),
):
    _require_configuration()
    owner_id = _owner_id(user)
    parameters = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": GMAIL_READONLY_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": _create_state(owner_id),
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(parameters)}")


@router.get("/callback")
async def gmail_authorization_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    user: dict = Depends(authenticated_user),
):
    _require_configuration()
    owner_id = _owner_id(user)
    if error:
        raise HTTPException(status_code=400, detail=f"Google recusou a autorizacao: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Resposta OAuth incompleta.")
    _validate_state(state, owner_id)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": _client_id(),
                    "client_secret": _client_secret(),
                    "redirect_uri": _redirect_uri(),
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail="O Google nao aceitou o codigo de autorizacao.",
                )
            tokens = token_response.json()
            access_token = tokens.get("access_token")
            if not access_token:
                raise HTTPException(status_code=400, detail="Google nao retornou token de acesso.")

            profile_response = await client.get(
                GMAIL_PROFILE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if profile_response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail="Nao foi possivel confirmar a conta Gmail autorizada.",
                )
            gmail_address = profile_response.json().get("emailAddress", "").strip()
    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail="O Google esta indisponivel no momento. Tente novamente.",
        )

    if not gmail_address:
        raise HTTPException(status_code=400, detail="Conta Gmail sem endereco identificavel.")

    db = SessionLocal()
    try:
        integration = db.scalar(
            select(EmailIntegration).where(
                EmailIntegration.owner_id == owner_id,
                EmailIntegration.provider == "gmail",
            )
        )
        refresh_token = tokens.get("refresh_token")
        if integration is None:
            if not refresh_token:
                raise HTTPException(
                    status_code=400,
                    detail="Google nao retornou permissao permanente. Conecte novamente.",
                )
            integration = EmailIntegration(owner_id=owner_id, provider="gmail")
            db.add(integration)
        if refresh_token:
            integration.encrypted_refresh_token = (
                _cipher().encrypt(refresh_token.encode("utf-8")).decode("ascii")
            )
        integration.email = gmail_address
        integration.scopes = tokens.get("scope") or GMAIL_READONLY_SCOPE
        db.commit()
    finally:
        db.close()

    return RedirectResponse("/dashboard?gmail=connected", status_code=303)


@router.get("/status")
async def gmail_connection_status(
    user: dict = Depends(authenticated_user),
):
    if not _configuration_ready():
        return {"configured": False, "connected": False, "email": None}
    owner_id = _owner_id(user)
    db = SessionLocal()
    try:
        integration = db.scalar(
            select(EmailIntegration).where(
                EmailIntegration.owner_id == owner_id,
                EmailIntegration.provider == "gmail",
            )
        )
        return {
            "configured": True,
            "connected": integration is not None,
            "email": integration.email if integration else None,
        }
    finally:
        db.close()
