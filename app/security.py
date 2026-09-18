import secrets
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


_CSP_NONCE: ContextVar[str] = ContextVar("csp_nonce", default="")


def current_csp_nonce() -> str:
    return _CSP_NONCE.get()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply browser security headers to successful and error responses."""

    CONTENT_SECURITY_POLICY = (
        "default-src 'self'; "
        "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        # Inline style attributes remain allowed for the legacy templates, but
        # every <style> element must carry the per-response nonce.
        "script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' 'nonce-{nonce}'; "
        "style-src-elem 'self' 'nonce-{nonce}'; "
        "style-src-attr 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; "
        "connect-src 'self'; form-action 'self' https://*.mercadopago.com"
    )

    async def dispatch(self, request: Request, call_next):
        nonce = secrets.token_urlsafe(18)
        token = _CSP_NONCE.set(nonce)
        try:
            response = await call_next(request)
        finally:
            _CSP_NONCE.reset(token)
        response.headers.setdefault("Content-Security-Policy", self.CONTENT_SECURITY_POLICY.format(nonce=nonce))
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        if request.url.scheme == "https" or forwarded_proto == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
