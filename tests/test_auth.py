import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import auth


def make_request(cookie: str = "") -> Request:
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode("ascii")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/profile",
        "headers": headers,
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }
    return Request(scope)


class AuthTest(unittest.IsolatedAsyncioTestCase):
    def test_render_hostname_builds_public_app_url(self):
        with patch.dict(
            "os.environ",
            {"APP_BASE_URL": "", "RENDER_EXTERNAL_HOSTNAME": "app.onrender.com"},
        ):
            self.assertEqual(auth._app_base_url(), "https://app.onrender.com")

    async def test_signup_rejects_short_password(self):
        with self.assertRaises(HTTPException) as raised:
            await auth.signup(
                auth.SignupRequest(
                    name="Pessoa Teste",
                    email="pessoa@example.com",
                    password="curta",
                )
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_supabase_error_explains_existing_email(self):
        response = httpx.Response(
            422,
            json={"error_code": "user_already_exists", "msg": "User already registered"},
        )
        self.assertIn("ja possui cadastro", auth._supabase_error(response, "fallback"))

    async def test_signup_waits_for_email_confirmation_without_session(self):
        supabase_response = httpx.Response(
            200,
            json={"id": "owner-new", "email": "pessoa@example.com"},
        )
        with (
            patch.object(auth, "APP_BASE_URL", "https://app.example.com"),
            patch.object(
                auth,
                "_supabase_request",
                AsyncMock(return_value=supabase_response),
            ) as request_mock,
        ):
            response = await auth.signup(
                auth.SignupRequest(
                    name="Pessoa Teste",
                    email="Pessoa@Example.com",
                    password="senha-segura",
                )
            )

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(body["created"])
        self.assertTrue(body["confirmation_required"])
        self.assertFalse(body["authenticated"])
        self.assertEqual(response.headers.getlist("set-cookie"), [])
        _, path = request_mock.await_args.args
        self.assertIn("/auth/v1/signup?redirect_to=", path)
        self.assertEqual(
            request_mock.await_args.kwargs["json"]["email"],
            "pessoa@example.com",
        )

    async def test_signup_sets_session_when_email_confirmation_is_disabled(self):
        session = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "user": {"id": "owner-new", "email": "pessoa@example.com"},
        }
        with (
            patch.object(auth, "APP_BASE_URL", "https://app.example.com"),
            patch.object(
                auth,
                "_supabase_request",
                AsyncMock(return_value=httpx.Response(200, json=session)),
            ),
        ):
            response = await auth.signup(
                auth.SignupRequest(
                    name="Pessoa Teste",
                    email="pessoa@example.com",
                    password="senha-segura",
                )
            )

        body = json.loads(response.body)
        cookies = response.headers.getlist("set-cookie")
        self.assertTrue(body["authenticated"])
        self.assertFalse(body["confirmation_required"])
        self.assertTrue(any(auth.ACCESS_COOKIE_NAME in value for value in cookies))
        self.assertTrue(any(auth.REFRESH_COOKIE_NAME in value for value in cookies))

    async def test_confirmation_session_verifies_token_and_sets_cookies(self):
        user = {"id": "owner-new", "email": "pessoa@example.com"}
        with patch.object(
            auth,
            "user_from_token",
            AsyncMock(return_value=user),
        ):
            response = await auth.accept_session(
                auth.SessionRequest(
                    access_token="confirmed-access",
                    refresh_token="confirmed-refresh",
                    expires_in=7200,
                )
            )

        cookies = response.headers.getlist("set-cookie")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(auth.ACCESS_COOKIE_NAME in value for value in cookies))
        self.assertTrue(any(auth.REFRESH_COOKIE_NAME in value for value in cookies))
        self.assertTrue(all("HttpOnly" in value for value in cookies))

    async def test_forgot_password_returns_generic_message(self):
        with (
            patch.object(auth, "APP_BASE_URL", "https://app.example.com"),
            patch.object(
                auth,
                "_supabase_request",
                AsyncMock(return_value=httpx.Response(200, json={})),
            ),
        ):
            response = await auth.forgot_password(
                auth.EmailRequest(email="pessoa@example.com")
            )
        self.assertIn("Se o e-mail estiver cadastrado", response["message"])

    async def test_signup_rejects_missing_public_https_url(self):
        with patch.object(auth, "APP_BASE_URL", ""):
            with self.assertRaises(HTTPException) as raised:
                await auth.signup(
                    auth.SignupRequest(
                        name="Pessoa Teste",
                        email="pessoa@example.com",
                        password="senha-segura",
                    )
                )
        self.assertEqual(raised.exception.status_code, 503)

    async def test_local_mode_returns_unrestricted_marker(self):
        with patch.object(auth, "AUTH_REQUIRED", False):
            user = await auth.authenticated_user(make_request())
        self.assertTrue(user["local_mode"])
        self.assertIsNone(user["id"])

    async def test_required_mode_uses_verified_middleware_user(self):
        request = make_request()
        request.state.user = {"id": "owner-a", "email": "a@example.com"}
        with patch.object(auth, "AUTH_REQUIRED", True):
            user = await auth.authenticated_user(request)
        self.assertEqual(user["id"], "owner-a")

    async def test_required_mode_rejects_missing_user(self):
        with patch.object(auth, "AUTH_REQUIRED", True):
            with self.assertRaises(HTTPException) as raised:
                await auth.authenticated_user(make_request())
        self.assertEqual(raised.exception.status_code, 401)

    async def test_me_renews_access_and_refresh_cookies(self):
        renewed = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }
        user = {"id": "owner-a", "email": "a@example.com"}
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(auth, "_configuration_ready", return_value=True),
            patch.object(
                auth,
                "_resolve_session",
                AsyncMock(return_value=(user, renewed)),
            ),
        ):
            response = await auth.current_user(make_request())

        cookies = response.headers.getlist("set-cookie")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(auth.ACCESS_COOKIE_NAME in value for value in cookies))
        self.assertTrue(any(auth.REFRESH_COOKIE_NAME in value for value in cookies))
        self.assertTrue(all("HttpOnly" in value for value in cookies))


class AuthMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.add_middleware(auth.AuthMiddleware)

        @self.app.post("/auth/signup")
        async def public_signup():
            return {"public": True}

        @self.app.get("/private")
        async def private(request: FastAPIRequest):
            return {"owner_id": request.state.user["id"]}

    def test_private_route_rejects_missing_session(self):
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(auth, "_configuration_ready", return_value=True),
            patch.object(
                auth,
                "_resolve_session",
                AsyncMock(return_value=(None, None)),
            ),
            TestClient(self.app) as client,
        ):
            response = client.get("/private")
        self.assertEqual(response.status_code, 401)

    def test_private_route_receives_verified_user(self):
        user = {"id": "owner-a", "email": "a@example.com"}
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(auth, "_configuration_ready", return_value=True),
            patch.object(
                auth,
                "_resolve_session",
                AsyncMock(return_value=(user, None)),
            ),
            TestClient(self.app) as client,
        ):
            response = client.get("/private")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["owner_id"], "owner-a")

    def test_signup_route_is_public(self):
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(auth, "_configuration_ready", return_value=True),
            TestClient(self.app) as client,
        ):
            response = client.post("/auth/signup")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["public"])
