import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from .auth import APP_BASE_URL, authenticated_user
from .database import SessionLocal
from .models import EmailIntegration

router = APIRouter(prefix="/auth/outlook", tags=["outlook"])
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_URL = "https://graph.microsoft.com/v1.0/me"


def _secret():
    return os.getenv("OUTLOOK_CLIENT_SECRET", "").strip()


def _state(owner_id):
    body = json.dumps({"sub": owner_id, "exp": int(time.time()) + 600, "nonce": secrets.token_urlsafe(16)}, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    return body.encode().hex() + "." + sig


def _validate_state(value, owner_id):
    try:
        body, supplied = value.split(".", 1)
        raw = bytes.fromhex(body).decode()
        expected = hmac.new(_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
        data = json.loads(raw)
        if not hmac.compare_digest(supplied, expected) or data.get("sub") != owner_id or int(data.get("exp", 0)) < int(time.time()):
            raise ValueError
    except Exception:
        raise HTTPException(400, "Autorizacao do Outlook expirada ou invalida.")


def _redirect():
    return os.getenv("OUTLOOK_REDIRECT_URI", "").strip() or f"{APP_BASE_URL}/auth/outlook/callback"


def _owner(user):
    value = user.get("id") if isinstance(user, dict) else None
    if not value:
        raise HTTPException(409, "Ative o login antes de conectar o Outlook.")
    return str(value)


def _cipher():
    try:
        return Fernet(os.getenv("TOKEN_ENCRYPTION_KEY", "").encode("ascii"))
    except Exception:
        raise HTTPException(503, "TOKEN_ENCRYPTION_KEY ausente ou invalida.")


@router.get("/start")
async def start(user: dict = Depends(authenticated_user)):
    if not os.getenv("OUTLOOK_CLIENT_ID") or not _secret():
        raise HTTPException(503, "Outlook ainda nao configurado no Render.")
    oid = _owner(user)
    params = {"client_id": os.getenv("OUTLOOK_CLIENT_ID"), "response_type": "code", "redirect_uri": _redirect(), "response_mode": "query", "scope": "openid email offline_access User.Read Mail.Read", "state": _state(oid)}
    return RedirectResponse(AUTH_URL + "?" + urlencode(params))


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    user = await authenticated_user(request)
    oid = _owner(user)
    if error:
        raise HTTPException(400, f"Microsoft recusou a autorizacao: {error}")
    if not code or not state:
        raise HTTPException(400, "Resposta OAuth incompleta.")
    _validate_state(state, oid)
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(TOKEN_URL, data={"client_id": os.getenv("OUTLOOK_CLIENT_ID"), "client_secret": _secret(), "code": code, "redirect_uri": _redirect(), "grant_type": "authorization_code"})
        if token_response.status_code != 200:
            try:
                details = token_response.json()
            except ValueError:
                details = {}
            reason = details.get("error_description") or details.get("error") or "verifique Client Secret e Redirect URI."
            raise HTTPException(400, f"A Microsoft recusou o token: {reason}")
        tokens = token_response.json()
        graph = await client.get(GRAPH_URL, headers={"Authorization": f"Bearer {tokens.get('access_token', '')}"})
    if graph.status_code != 200:
        raise HTTPException(400, "Nao foi possivel identificar a conta Microsoft.")
    profile = graph.json()
    email = (profile.get("mail") or profile.get("userPrincipalName") or "").strip()
    refresh = tokens.get("refresh_token")
    if not email or not refresh:
        raise HTTPException(400, "Microsoft nao retornou os dados necessarios.")
    db = SessionLocal()
    try:
        integration = db.scalar(select(EmailIntegration).where(EmailIntegration.owner_id == oid, EmailIntegration.provider == "outlook"))
        if integration is None:
            integration = EmailIntegration(owner_id=oid, provider="outlook", email=email, encrypted_refresh_token="", scopes="")
            db.add(integration)
        integration.email = email
        integration.encrypted_refresh_token = _cipher().encrypt(refresh.encode()).decode("ascii")
        integration.scopes = tokens.get("scope", "Mail.Read")
        db.commit()
    finally:
        db.close()
    return RedirectResponse("/settings#integrations", status_code=303)


@router.get("/status")
async def status(user: dict = Depends(authenticated_user)):
    if not os.getenv("OUTLOOK_CLIENT_ID") or not _secret():
        return {"configured": False, "connected": False, "email": None}
    oid = _owner(user)
    db = SessionLocal()
    try:
        integration = db.scalar(select(EmailIntegration).where(EmailIntegration.owner_id == oid, EmailIntegration.provider == "outlook"))
        return {"configured": True, "connected": integration is not None, "email": integration.email if integration else None}
    finally:
        db.close()
