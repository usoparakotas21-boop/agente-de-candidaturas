import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import auth
from app.security import SecurityHeadersMiddleware


def request_for(host: str = "198.51.100.10") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": (host, 50000),
            "scheme": "http",
        }
    )


class SecurityControlsTest(unittest.TestCase):
    def test_security_headers_are_added_and_hsts_requires_https(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def home():
            return {"ok": True}

        with TestClient(app, base_url="https://testserver") as client:
            response = client.get("/")

        self.assertEqual(response.headers["content-security-policy"].split(";", 1)[0], "default-src 'self'")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "strict-origin-when-cross-origin")
        self.assertIn("max-age=31536000", response.headers["strict-transport-security"])

    def test_auth_limiter_blocks_ip_and_account_after_threshold(self):
        request = request_for()
        auth._rate_attempts.clear()
        with patch.dict(auth._RATE_LIMITS, {"login": (2, 60)}, clear=False):
            auth._enforce_rate_limit(request, "login", "pessoa@example.com")
            auth._enforce_rate_limit(request, "login", "pessoa@example.com")
            with self.assertRaises(auth.HTTPException) as raised:
                auth._enforce_rate_limit(request, "login", "pessoa@example.com")

        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("Retry-After", raised.exception.headers)
        auth._rate_attempts.clear()


if __name__ == "__main__":
    unittest.main()
