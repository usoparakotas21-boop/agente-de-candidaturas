import secrets
from urllib.parse import urlsplit
from contextvars import ContextVar

from fastapi import Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


_CSP_NONCE: ContextVar[str] = ContextVar("csp_nonce", default="")


def current_csp_nonce() -> str:
    return _CSP_NONCE.get()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply browser security headers to successful and error responses."""

    @staticmethod
    def content_security_policy(nonce: str) -> str:
        return (
            "default-src 'self'; "
            "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            f"script-src 'self' 'nonce-{nonce}' https://googletagmanager.com https://www.googletagmanager.com; "
            f"style-src 'self' 'nonce-{nonce}' 'unsafe-inline'; "
            f"style-src-elem 'self' 'nonce-{nonce}'; "
            "img-src 'self' data: https://google-analytics.com https://www.google-analytics.com https://googletagmanager.com; font-src 'self' data:; "
            "connect-src 'self' https://google-analytics.com https://www.google-analytics.com https://googletagmanager.com https://*.google-analytics.com https://*.analytics.google.com; frame-src https://www.youtube-nocookie.com https://player.vimeo.com; "
            "form-action 'self' https://*.mercadopago.com"
        )

    async def dispatch(self, request: Request, call_next):
        # SameSite=Lax does not block a compromised sibling subdomain.
        # Webhooks authenticate their provider signature; the extension uses
        # its explicit bearer credential rather than ambient cookies.
        denied = None
        provider_path = request.url.path.rstrip("/") in {
            "/webhooks/mercadopago", "/api/billing/webhook",
        }
        bearer_extension = (
            request.url.path.startswith("/api/copilot/")
            and request.headers.get("authorization", "").lower().startswith("bearer ")
        )
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not provider_path and not bearer_extension:
            from app.auth import APP_BASE_URL

            origin = request.headers.get("origin")
            expected = urlsplit(APP_BASE_URL)
            trusted_origin = f"{expected.scheme}://{expected.netloc}"
            if (origin is not None and origin != trusted_origin) or request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
                denied = JSONResponse({"detail": "Origem da solicitacao nao permitida."}, status_code=403)
        nonce = secrets.token_urlsafe(18)
        token = _CSP_NONCE.set(nonce)
        try:
            response = denied if denied is not None else await call_next(request)
        finally:
            _CSP_NONCE.reset(token)
        response.headers.setdefault("Content-Security-Policy", self.content_security_policy(nonce))
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        # HTML pages carry account state, checkout context, or security UI.
        # Authentication/configuration failures also must not be cached, since
        # a browser or intermediary could replay a stale access decision.
        # Static assets and ordinary public JSON keep their normal cache policy.
        content_type = response.headers.get("content-type", "").lower()
        if content_type.startswith("text/html") or response.status_code in {401, 403, 503}:
            response.headers.setdefault("Cache-Control", "private, no-store, max-age=0")
            response.headers.setdefault("Pragma", "no-cache")
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        if request.url.scheme == "https" or forwarded_proto == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
