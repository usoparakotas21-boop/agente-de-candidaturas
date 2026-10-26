"""Atomic, persistent OAuth state consumption across workers and restarts."""
import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from .models import OAuthStateNonce


def _digest(provider, owner_id, nonce):
    return hashlib.sha256(f"{provider}:{owner_id}:{nonce}".encode()).hexdigest()


def register_nonce(sessions, provider, owner_id, nonce, expires_at):
    try:
        with sessions() as db:
            db.execute(delete(OAuthStateNonce).where(OAuthStateNonce.expires_at <= datetime.now(timezone.utc)))
            db.add(OAuthStateNonce(
                nonce_hash=_digest(provider, owner_id, nonce), provider=provider,
                owner_id=owner_id, expires_at=datetime.fromtimestamp(expires_at, timezone.utc),
            ))
            db.commit()
    except SQLAlchemyError:
        raise HTTPException(503, "Protecao OAuth indisponivel. Tente novamente.") from None


def consume_nonce(sessions, provider, owner_id, nonce):
    if not isinstance(nonce, str) or not 16 <= len(nonce) <= 128:
        raise HTTPException(400, "Autorizacao OAuth invalida ou ja utilizada.")
    try:
        with sessions() as db:
            result = db.execute(delete(OAuthStateNonce).where(
                OAuthStateNonce.nonce_hash == _digest(provider, owner_id, nonce),
                OAuthStateNonce.provider == provider,
                OAuthStateNonce.owner_id == owner_id,
                OAuthStateNonce.expires_at > datetime.now(timezone.utc),
            ))
            accepted = result.rowcount == 1
            db.commit()
    except SQLAlchemyError:
        raise HTTPException(503, "Protecao OAuth indisponivel. Tente novamente.") from None
    if not accepted:
        raise HTTPException(400, "Autorizacao OAuth invalida ou ja utilizada.")
