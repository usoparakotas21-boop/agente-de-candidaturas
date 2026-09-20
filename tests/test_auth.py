import json
import base64
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import auth


def unsigned_jwt_with_aal(aal: str | None) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=")
    claims = {} if aal is None else {"aal": aal}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{header}.{payload}.test-signature"


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
    def test_token_aal_defaults_missing_claim_to_aal1_and_handles_aal2(self):
        self.assertEqual(auth._token_aal(unsigned_jwt_with_aal(None)), "aal1")
        self.assertEqual(auth._token_aal(unsigned_jwt_with_aal("aal1")), "aal1")
        self.assertEqual(auth._token_aal(unsigned_jwt_with_aal("aal2")), "aal2")
        self.assertIsNone(auth._token_aal("not-a-jwt"))

    def test_verified_totp_requires_aal2(self):
        user = {
            "factors": [
                {"factor_type": "totp", "status": "verified", "id": "factor-1"}
            ]
        }
        self.assertTrue(auth._session_requires_mfa(user, unsigned_jwt_with_aal("aal1")))
        self.assertTrue(auth._session_requires_mfa(user, unsigned_jwt_with_aal(None)))
        self.assertTrue(auth._session_requires_mfa(user, "malformed"))
        self.assertFalse(auth._session_requires_mfa(user, unsigned_jwt_with_aal("aal2")))
        self.assertFalse(auth._session_requires_mfa({"factors": []}, unsigned_jwt_with_aal("aal1")))

    def test_render_hostname_builds_public_app_url(self):
        with patch.dict(
            "os.environ",
            {"APP_BASE_URL": "", "RENDER_EXTERNAL_HOSTNAME": "app.onrender.com"},
        ):
            self.assertEqual(auth._app_base_url(), "https://app.onrender.com")

    def test_invalid_explicit_url_falls_back_to_render_hostname(self):
        with patch.dict(
            "os.environ",
            {
                "APP_BASE_URL": "Site URL https://agente-de-candidaturas.onrender.com",
                "RENDER_EXTERNAL_HOSTNAME": "app.onrender.com",
            },
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

    async def test_signup_requires_explicit_legal_consent(self):
        with self.assertRaises(HTTPException) as raised:
            await auth.signup(
                auth.SignupRequest(
                    name="Pessoa Teste",
                    email="pessoa@example.com",
                    password="Senha-segura1!",
                )
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("Termos", str(raised.exception.detail))

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
                    password="Senha-segura1!",
                    terms_accepted=True,
                    privacy_accepted=True,
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
        metadata = request_mock.await_args.kwargs["json"]["data"]
        self.assertTrue(metadata["terms_accepted"])
        self.assertTrue(metadata["privacy_accepted"])
        self.assertEqual(metadata["terms_version"], auth.TERMS_VERSION)
        self.assertEqual(metadata["privacy_version"], auth.PRIVACY_VERSION)
        self.assertTrue(metadata["consented_at"].endswith("Z"))

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
                    password="Senha-segura1!",
                    terms_accepted=True,
                    privacy_accepted=True,
                )
            )

        body = json.loads(response.body)
        cookies = response.headers.getlist("set-cookie")
        self.assertTrue(body["authenticated"])
        self.assertFalse(body["confirmation_required"])
        self.assertTrue(any(auth.ACCESS_COOKIE_NAME in value for value in cookies))
        self.assertTrue(any(auth.REFRESH_COOKIE_NAME in value for value in cookies))

    async def test_signup_does_not_set_session_for_explicitly_unverified_user(self):
        session = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "user": {
                "id": "owner-new",
                "email": "pessoa@example.com",
                "email_confirmed_at": None,
                "confirmed_at": None,
            },
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
                    password="Senha-segura1!",
                    terms_accepted=True,
                    privacy_accepted=True,
                )
            )

        body = json.loads(response.body)
        self.assertFalse(body["authenticated"])
        self.assertTrue(body["confirmation_required"])
        self.assertEqual(response.headers.getlist("set-cookie"), [])

    async def test_login_rejects_explicitly_unverified_user(self):
        session = {
            "access_token": "access",
            "refresh_token": "refresh",
            "user": {
                "id": "owner-a",
                "email": "pessoa@example.com",
                "email_confirmed_at": None,
            },
        }
        with patch.object(
            auth,
            "_supabase_request",
            AsyncMock(return_value=httpx.Response(200, json=session)),
        ):
            response = await auth.login(
                auth.LoginRequest(email="pessoa@example.com", password="Senha-segura1!")
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.body)["code"], "email_not_verified")
        self.assertEqual(response.headers.get("x-auth-reason"), "email_not_verified")
        self.assertEqual(response.headers.getlist("set-cookie"), [])

    async def test_login_normalizes_email_before_calling_supabase(self):
        session = {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "user": {"id": "owner-a", "email": "pessoa@example.com"},
        }
        with patch.object(
            auth,
            "_supabase_request",
            AsyncMock(return_value=httpx.Response(200, json=session)),
        ) as request_mock:
            response = await auth.login(
                auth.LoginRequest(
                    email="  Pessoa@Example.com ",
                    password="Senha-segura1!",
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            request_mock.await_args_list[0].kwargs["json"]["email"],
            "pessoa@example.com",
        )
        self.assertEqual(request_mock.await_args_list[1].args[1], "/auth/v1/user")

    async def test_login_exposes_confirmation_error_from_supabase(self):
        supabase_response = httpx.Response(
            400,
            json={"error_code": "email_not_confirmed", "msg": "Email not confirmed"},
        )
        with patch.object(
            auth,
            "_supabase_request",
            AsyncMock(return_value=supabase_response),
        ):
            with self.assertRaises(HTTPException) as raised:
                await auth.login(
                    auth.LoginRequest(
                        email="pessoa@example.com",
                        password="Senha-segura1!",
                    )
                )

        self.assertEqual(raised.exception.status_code, 401)
        self.assertIn("Confirme seu e-mail", raised.exception.detail)

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
        self.assertTrue(all("SameSite=lax" in value for value in cookies))
        self.assertEqual(all("Secure" in value for value in cookies), auth.COOKIE_SECURE)

    async def test_confirmation_session_rejects_unverified_token(self):
        with patch.object(
            auth,
            "user_from_token",
            AsyncMock(
                return_value={
                    "id": "owner-new",
                    "email": "pessoa@example.com",
                    "email_confirmed_at": None,
                }
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await auth.accept_session(
                    auth.SessionRequest(access_token="pending-access")
                )
        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("Confirme seu e-mail", raised.exception.detail)

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

    async def test_resend_confirmation_uses_signup_flow_and_generic_message(self):
        with (
            patch.object(auth, "APP_BASE_URL", "https://app.example.com"),
            patch.object(
                auth,
                "_supabase_request",
                AsyncMock(return_value=httpx.Response(200, json={})),
            ) as request_mock,
        ):
            response = await auth.resend_confirmation(
                auth.EmailRequest(email=" Pessoa@Example.com ")
            )

        self.assertIn("Se houver um cadastro pendente", response["message"])
        method, path = request_mock.await_args.args
        self.assertEqual(method, "POST")
        self.assertIn("/auth/v1/resend?redirect_to=", path)
        self.assertEqual(
            request_mock.await_args.kwargs["json"],
            {"type": "signup", "email": "pessoa@example.com"},
        )

    async def test_resend_confirmation_maps_provider_rate_limit(self):
        with (
            patch.object(auth, "APP_BASE_URL", "https://app.example.com"),
            patch.object(
                auth,
                "_supabase_request",
                AsyncMock(return_value=httpx.Response(429, json={"msg": "too many"})),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await auth.resend_confirmation(
                    auth.EmailRequest(email="pessoa@example.com")
                )

        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("Aguarde", str(raised.exception.detail))

    async def test_signup_rejects_missing_public_https_url(self):
        with patch.object(auth, "APP_BASE_URL", ""):
            with self.assertRaises(HTTPException) as raised:
                await auth.signup(
                    auth.SignupRequest(
                        name="Pessoa Teste",
                        email="pessoa@example.com",
                        password="Senha-segura1!",
                        terms_accepted=True,
                        privacy_accepted=True,
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

    async def test_me_rejects_old_aal1_session_when_totp_is_verified(self):
        user = {
            "id": "owner-a",
            "email": "a@example.com",
            "factors": [{"id": "factor-1", "factor_type": "totp", "status": "verified"}],
        }
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(auth, "_configuration_ready", return_value=True),
            patch.object(auth, "_resolve_session", AsyncMock(return_value=(user, None))),
        ):
            response = await auth.current_user(
                make_request(cookie=f"{auth.ACCESS_COOKIE_NAME}={unsigned_jwt_with_aal('aal1')}")
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.body)["code"], "mfa_required")

    async def test_refresh_resolution_revalidates_the_new_access_token(self):
        refreshed = {
            "access_token": unsigned_jwt_with_aal("aal1"),
            "refresh_token": "rotated-refresh",
            "user": {"id": "untrusted-refresh-payload"},
        }
        validated_user = {
            "id": "owner-a",
            "email": "a@example.com",
            "factors": [{"id": "factor-1", "factor_type": "totp", "status": "verified"}],
        }
        request = make_request(cookie=f"{auth.REFRESH_COOKIE_NAME}=old-refresh")
        with (
            patch.object(auth, "_refresh_session", AsyncMock(return_value=refreshed)),
            patch.object(auth, "user_from_token", AsyncMock(return_value=validated_user)) as validate,
        ):
            user, session = await auth._resolve_session(request)
        self.assertEqual(user["id"], "owner-a")
        self.assertEqual(session["refresh_token"], "rotated-refresh")
        validate.assert_awaited_once_with(refreshed["access_token"])


class AuthMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.add_middleware(auth.AuthMiddleware)

        @self.app.post("/auth/signup")
        async def public_signup():
            return {"public": True}

        @self.app.get("/termos")
        async def terms_page():
            return {"public": "terms"}

        @self.app.get("/privacidade")
        async def privacy_page():
            return {"public": "privacy"}

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

    def test_legal_pages_are_public_before_login(self):
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(auth, "_configuration_ready", return_value=False),
            TestClient(self.app) as client,
        ):
            terms = client.get("/termos")
            privacy = client.get("/privacidade")
        self.assertEqual(terms.status_code, 200)
        self.assertEqual(terms.json(), {"public": "terms"})
        self.assertEqual(privacy.status_code, 200)
        self.assertEqual(privacy.json(), {"public": "privacy"})

        with TestClient(self.app) as client:
            self.assertIn(client.get("/termos/").status_code, {200, 307})
            self.assertIn(client.get("/privacidade/").status_code, {200, 307})

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

    def test_private_route_blocks_old_aal1_session_after_totp_is_enabled(self):
        user = {
            "id": "owner-a",
            "email": "a@example.com",
            "factors": [{"id": "factor-1", "factor_type": "totp", "status": "verified"}],
        }
        token = unsigned_jwt_with_aal("aal1")
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(auth, "_configuration_ready", return_value=True),
            patch.object(auth, "_resolve_session", AsyncMock(return_value=(user, None))),
            TestClient(self.app) as client,
        ):
            response = client.get("/private", cookies={auth.ACCESS_COOKIE_NAME: token})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "mfa_required")
        self.assertIn(auth.ACCESS_COOKIE_NAME, response.headers.get("set-cookie", ""))

    def test_private_route_accepts_aal2_and_users_without_totp(self):
        users_and_tokens = [
            (
                {
                    "id": "owner-a",
                    "email": "a@example.com",
                    "factors": [{"id": "factor-1", "factor_type": "totp", "status": "verified"}],
                },
                unsigned_jwt_with_aal("aal2"),
            ),
            ({"id": "owner-b", "email": "b@example.com", "factors": []}, unsigned_jwt_with_aal("aal1")),
        ]
        for user, token in users_and_tokens:
            with (
                patch.object(auth, "AUTH_REQUIRED", True),
                patch.object(auth, "_configuration_ready", return_value=True),
                patch.object(auth, "_resolve_session", AsyncMock(return_value=(user, None))),
                TestClient(self.app) as client,
            ):
                response = client.get("/private", cookies={auth.ACCESS_COOKIE_NAME: token})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["owner_id"], user["id"])

    def test_refreshed_aal1_session_with_verified_totp_is_blocked(self):
        user = {
            "id": "owner-a",
            "email": "a@example.com",
            "factors": [{"id": "factor-1", "factor_type": "totp", "status": "verified"}],
        }
        renewed = {"access_token": unsigned_jwt_with_aal("aal1"), "refresh_token": "new-refresh"}
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(auth, "_configuration_ready", return_value=True),
            patch.object(auth, "_resolve_session", AsyncMock(return_value=(user, renewed))),
            TestClient(self.app) as client,
        ):
            response = client.get("/private", cookies={auth.REFRESH_COOKIE_NAME: "old-refresh"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "mfa_required")

    def test_private_route_redirects_unverified_html_request(self):
        user = {
            "id": "owner-a",
            "email": "a@example.com",
            "email_confirmed_at": None,
        }
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
            response = client.get("/private", headers={"accept": "text/html"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/auth/verification-required")

    def test_private_route_rejects_unverified_api_request(self):
        user = {
            "id": "owner-a",
            "email": "a@example.com",
            "email_confirmed_at": None,
        }
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
            response = client.get("/private", headers={"accept": "application/json"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "email_not_verified")

    def test_signup_route_is_public(self):
        with (
            patch.object(auth, "AUTH_REQUIRED", True),
            patch.object(auth, "_configuration_ready", return_value=True),
            TestClient(self.app) as client,
        ):
            response = client.post("/auth/signup")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["public"])
