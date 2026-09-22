"""Helpers for keeping OAuth callbacks aligned with the public site."""

from urllib.parse import urlparse


def public_callback_url(configured: str, base_url: str, path: str) -> str:
    """Return a configured callback, repairing stale Render hostnames.

    During the domain migration an old ``*.onrender.com`` value can remain in
    the service environment.  When the application already has an HTTPS
    canonical base URL, using that stale hostname makes the provider return to
    the wrong site.  Custom callbacks (including test hosts) remain untouched.
    """

    configured = (configured or "").strip()
    base_url = (base_url or "").strip().rstrip("/")
    if not configured:
        return f"{base_url}{path}"

    configured_parts = urlparse(configured)
    base_parts = urlparse(base_url)
    configured_host = (configured_parts.hostname or "").lower()
    base_host = (base_parts.hostname or "").lower()
    if (
        configured_parts.scheme == "https"
        and base_parts.scheme == "https"
        and configured_host.endswith(".onrender.com")
        and base_host
        and configured_host != base_host
    ):
        return f"{base_url}{path}"
    return configured
