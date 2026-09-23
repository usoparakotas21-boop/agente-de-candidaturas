"""Helpers for keeping OAuth callbacks aligned with the public site."""

from urllib.parse import urlparse


def public_callback_url(configured: str, base_url: str, path: str) -> str:
    """Return a canonical OAuth callback URL using HTTPS.

    Google and Microsoft OAuth requires exact matching with registered redirect URIs.
    Any non-HTTPS scheme, port residual, or *.onrender.com hostname mismatch is rewritten
    to the canonical base_url (https://candidaturacerta.com.br).
    Custom HTTPS endpoints remain supported.
    """
    configured = (configured or "").strip()
    base_url = (base_url or "").strip().rstrip("/")
    if "candidaturacerta.com.br" in base_url or "onrender.com" in base_url or not base_url:
        base_url = "https://candidaturacerta.com.br"
    
    canonical_default = f"{base_url}{path}"

    if not configured:
        return canonical_default

    configured_parts = urlparse(configured)
    configured_host = (configured_parts.hostname or "").lower()

    if configured_host.endswith(".onrender.com"):
        return canonical_default

    if configured_parts.scheme != "https" and configured_host not in {"localhost", "127.0.0.1"}:
        return canonical_default

    if configured_host == "candidaturacerta.com.br":
        return f"https://candidaturacerta.com.br{path}"

    return configured


