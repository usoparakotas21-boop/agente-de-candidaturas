import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import auth
from app.security import SecurityHeadersMiddleware
from app import main as main_module


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
    def test_modal_accessibility_script_is_injected_into_pages(self):
        with patch.object(main_module, "current_csp_nonce", return_value="testnonce"):
            dashboard = main_module.dashboard()
        body = dashboard.body.decode('utf-8')
        self.assertIn('/static/modal-a11y.js', body)
        self.assertRegex(body, r'<meta name="csp-nonce" content="[^"]+">')
        self.assertRegex(body, r'<style nonce="[^"]+">')

    def test_security_headers_are_added_and_hsts_requires_https(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def home():
            from fastapi.responses import HTMLResponse

            return HTMLResponse("<h1>ok</h1>")

        with TestClient(app, base_url="https://testserver") as client:
            response = client.get("/")

        self.assertEqual(response.headers["content-security-policy"].split(";", 1)[0], "default-src 'self'")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "strict-origin-when-cross-origin")
        self.assertIn("max-age=31536000", response.headers["strict-transport-security"])
        self.assertIn("script-src 'self' 'nonce-", response.headers["content-security-policy"])
        self.assertNotIn("script-src 'self' 'unsafe-inline'", response.headers["content-security-policy"])
        self.assertIn("style-src 'self' 'nonce-", response.headers["content-security-policy"])
        self.assertIn("style-src-elem 'self' 'nonce-", response.headers["content-security-policy"])
        self.assertNotIn("style-src-attr 'unsafe-inline'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["cache-control"], "private, no-store, max-age=0")
        self.assertEqual(response.headers["pragma"], "no-cache")

    def test_static_content_is_not_forced_to_no_store(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/static/app.js")
        async def asset():
            from fastapi.responses import Response

            return Response("console.log('ok')", media_type="application/javascript")

        with TestClient(app, base_url="https://testserver") as client:
            response = client.get("/static/app.js")

        self.assertNotIn("cache-control", response.headers)

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

    def test_required_distributed_limiter_fails_closed_when_unconfigured(self):
        request = request_for()
        with (
            patch.dict("os.environ", {"RATE_LIMIT_DISTRIBUTED_REQUIRED": "true"}, clear=False),
            patch.object(auth.distributed_rate_limit, "is_configured", return_value=False),
        ):
            with self.assertRaises(auth.HTTPException) as raised:
                auth._enforce_rate_limit(request, "login", "pessoa@example.com")

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "Proteção contra excesso de tentativas indisponível.")

    def test_distributed_limiter_hashes_ip_and_account_keys(self):
        request = request_for()
        with (
            patch.object(auth.distributed_rate_limit, "is_configured", return_value=True),
            patch.object(
                auth.distributed_rate_limit,
                "check",
                return_value=(False, 0),
            ) as check,
        ):
            auth._enforce_rate_limit(request, "login", "pessoa@example.com")

        shared_keys = check.call_args.args[0]
        self.assertEqual(len(shared_keys), 2)
        self.assertTrue(all(key.startswith("agente-rate:") for key in shared_keys))
        self.assertNotIn("pessoa@example.com", shared_keys)
        self.assertNotIn("198.51.100.10", shared_keys)
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
