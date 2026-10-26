"""One backend authority for admin identity and legacy courtesy access."""
import os


def _field(user, key):
    return user.get(key) if isinstance(user, dict) else getattr(user, key, None)


def verified_identity(user):
    return bool(user and (_field(user, "id") or _field(user, "uid") or _field(user, "sub"))
                and (_field(user, "email_confirmed_at") or _field(user, "confirmed_at")))


def admin_emails():
    return {"contato@candidaturacerta.com.br", "usoparakotas4@gmail.com", "usoparakotas21@gmail.com"} | {
        item.strip().casefold() for item in os.getenv("ADMIN_EMAILS", "").split(",") if item.strip()
    }


def is_admin_identity(user):
    if not verified_identity(user):
        return False
    metadata = _field(user, "app_metadata") or {}
    claim = metadata.get("is_admin") if isinstance(metadata, dict) else None
    return str(claim).casefold() in {"true", "1"} or str(_field(user, "email") or "").strip().casefold() in admin_emails()


def courtesy_emails():
    # Historical courtesy account retains benefits, never administrator status.
    return {"henriqueoliveirarh93@gmail.com"}
