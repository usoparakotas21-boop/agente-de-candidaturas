from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply browser security headers to successful and error responses."""

    CONTENT_SECURITY_POLICY = (
        "default-src 'self'; "
        "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; "
        "connect-src 'self'; form-action 'self' https://*.mercadopago.com https://*.infinitepay.io"
    )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", self.CONTENT_SECURITY_POLICY)
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
