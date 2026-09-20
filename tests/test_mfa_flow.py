import json
import base64
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from starlette.requests import Request

from app import auth


def unsigned_jwt_with_aal(aal: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"aal": aal}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.test-signature"


def request_with_cookies(cookie_header: str = "") -> Request:
    headers = [(b"cookie", cookie_header.encode("ascii"))] if cookie_header else []
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/mfa/complete",
            "headers": headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "https",
        }
    )


class MfaFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_user_without_verified_factor_can_login_without_mfa(self):
        login_session = {
            "access_token": "optional-access",
            "refresh_token": "optional-refresh",
            "expires_in": 3600,
            "user": {
                "id": "owner-a",
                "email": "a@example.com",
                "email_confirmed_at": "2026-09-18T12:00:00Z",
            },
        }
        factors_response = httpx.Response(200, json={"id": "owner-a", "factors": []})
        with (
            patch.object(auth, "_supabase_request", AsyncMock(side_effect=(httpx.Response(200, json=login_session), factors_response))) as request_mock,
        ):
            response = await auth.login(auth.LoginRequest(email="a@example.com", password="Senha-segura1!"))

        body = json.loads(response.body)
        self.assertTrue(body["authenticated"])
        self.assertNotIn("mfa_required", body)
        self.assertTrue(any(auth.ACCESS_COOKIE_NAME + "=optional-access" in value for value in response.headers.getlist("set-cookie")))
        self.assertEqual(request_mock.await_count, 2)
        self.assertEqual(request_mock.await_args_list[1].args[1], "/auth/v1/user")

    async def test_login_fails_closed_when_factor_status_cannot_be_checked(self):
        login_session = {
            "access_token": "optional-access",
            "refresh_token": "optional-refresh",
            "expires_in": 3600,
            "user": {"id": "owner-a", "email": "a@example.com", "email_confirmed_at": "2026-09-18T12:00:00Z"},
        }
        with patch.object(
            auth,
            "_supabase_request",
            AsyncMock(side_effect=(httpx.Response(200, json=login_session), httpx.Response(503, json={"msg": "Unavailable"}))),
        ):
            with self.assertRaises(auth.HTTPException) as raised:
                await auth.login(auth.LoginRequest(email="a@example.com", password="Senha-segura1!"))
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("token", raised.exception.detail.casefold())

    async def test_verified_totp_requires_challenge_when_mfa_is_optional_and_complete_promotes_session(self):
        login_session = {
            "access_token": "aal1-access",
            "refresh_token": "aal1-refresh",
            "expires_in": 3600,
            "user": {"id": "owner-a", "email": "a@example.com"},
        }
        responses = [
            httpx.Response(200, json=login_session),
            httpx.Response(200, json={"id": "owner-a", "factors": [{"id": "factor-1", "factor_type": "totp", "status": "verified"}]}),
            httpx.Response(200, json={"id": "challenge-1"}),
        ]
        with (
            patch.dict("os.environ", {"MFA_LOGIN_ENFORCE": "false"}, clear=False),
            patch.object(auth, "_supabase_request", AsyncMock(side_effect=responses)),
        ):
            response = await auth.login(auth.LoginRequest(email="a@example.com", password="Senha-segura1!"))

        body = json.loads(response.body)
        self.assertFalse(body["authenticated"])
        self.assertTrue(body["mfa_required"])
        cookies = "; ".join(item.split(";", 1)[0] for item in response.headers.getlist("set-cookie"))
        self.assertIn(auth.MFA_PENDING_ACCESS_COOKIE_NAME, cookies)
        self.assertNotIn(auth.ACCESS_COOKIE_NAME + "=aal1-access", cookies)
        pending_headers = response.headers.getlist("set-cookie")
        pending_access_cookie = next(
            value for value in pending_headers if value.startswith(auth.MFA_PENDING_ACCESS_COOKIE_NAME + "=")
        )
        self.assertIn("Max-Age=300", pending_access_cookie)
        self.assertIn("HttpOnly", pending_access_cookie)
        self.assertIn("SameSite=lax", pending_access_cookie)
        self.assertEqual("Secure" in pending_access_cookie, auth.COOKIE_SECURE)

        verified_session = {
            "access_token": unsigned_jwt_with_aal("aal2"),
            "refresh_token": "aal2-refresh",
            "expires_in": 3600,
            "user": {"id": "owner-a", "email": "a@example.com"},
        }
        with patch.object(
            auth,
            "_supabase_request",
            AsyncMock(return_value=httpx.Response(200, json=verified_session)),
        ) as request_mock:
            complete = await auth.mfa_complete_login(
                auth.MfaLoginCodeRequest(factor_id="factor-1", challenge_id="challenge-1", code="123456"),
                request_with_cookies(
                    f"{auth.MFA_PENDING_ACCESS_COOKIE_NAME}=aal1-access; "
                    f"{auth.MFA_PENDING_FACTOR_COOKIE_NAME}=factor-1; "
                    f"{auth.MFA_PENDING_CHALLENGE_COOKIE_NAME}=challenge-1"
                ),
            )

        self.assertTrue(json.loads(complete.body)["authenticated"])
        self.assertTrue(any(auth.ACCESS_COOKIE_NAME + "=" + verified_session["access_token"] in value for value in complete.headers.getlist("set-cookie")))
        self.assertTrue(request_mock.await_args.kwargs["json"]["challenge_id"] == "challenge-1")

    async def test_mfa_completion_rejects_missing_pending_session(self):
        with self.assertRaises(auth.HTTPException) as raised:
            await auth.mfa_complete_login(
                auth.MfaLoginCodeRequest(factor_id="factor-1", challenge_id="challenge-1", code="123456"),
                request_with_cookies(),
            )
        self.assertEqual(raised.exception.status_code, 401)

    async def test_mfa_completion_rejects_mismatched_challenge_before_provider_call(self):
        provider = AsyncMock()
        with patch.object(auth, "_supabase_request", provider):
            with self.assertRaises(auth.HTTPException) as raised:
                await auth.mfa_complete_login(
                    auth.MfaLoginCodeRequest(
                        factor_id="factor-1",
                        challenge_id="different-challenge",
                        code="123456",
                    ),
                    request_with_cookies(
                        f"{auth.MFA_PENDING_ACCESS_COOKIE_NAME}=aal1-access; "
                        f"{auth.MFA_PENDING_FACTOR_COOKIE_NAME}=factor-1; "
                        f"{auth.MFA_PENDING_CHALLENGE_COOKIE_NAME}=challenge-1"
                    ),
                )
        self.assertEqual(raised.exception.status_code, 400)
        provider.assert_not_awaited()

    async def test_mfa_completion_rejects_invalid_code_without_promoting_session(self):
        provider_response = httpx.Response(401, json={"msg": "Invalid TOTP code"})
        with patch.object(
            auth,
            "_supabase_request",
            AsyncMock(return_value=provider_response),
        ):
            with self.assertRaises(auth.HTTPException) as raised:
                await auth.mfa_complete_login(
                    auth.MfaLoginCodeRequest(factor_id="factor-1", challenge_id="challenge-1", code="000000"),
                    request_with_cookies(
                        f"{auth.MFA_PENDING_ACCESS_COOKIE_NAME}=aal1-access; "
                        f"{auth.MFA_PENDING_FACTOR_COOKIE_NAME}=factor-1; "
                        f"{auth.MFA_PENDING_CHALLENGE_COOKIE_NAME}=challenge-1"
                    ),
                )
        self.assertEqual(raised.exception.status_code, 401)

    async def test_expired_mfa_challenge_cannot_issue_a_session(self):
        provider_response = httpx.Response(401, json={"msg": "Factor challenge expired"})
        with patch.object(auth, "_supabase_request", AsyncMock(return_value=provider_response)):
            with self.assertRaises(auth.HTTPException) as raised:
                await auth.mfa_complete_login(
                    auth.MfaLoginCodeRequest(factor_id="factor-1", challenge_id="challenge-1", code="123456"),
                    request_with_cookies(
                        f"{auth.MFA_PENDING_ACCESS_COOKIE_NAME}=aal1-access; "
                        f"{auth.MFA_PENDING_FACTOR_COOKIE_NAME}=factor-1; "
                        f"{auth.MFA_PENDING_CHALLENGE_COOKIE_NAME}=challenge-1"
                    ),
                )
        self.assertEqual(raised.exception.status_code, 401)

    async def test_mfa_completion_rejects_provider_response_without_aal2(self):
        provider_response = httpx.Response(
            200,
            json={
                "access_token": unsigned_jwt_with_aal("aal1"),
                "refresh_token": "not-elevated-refresh",
                "expires_in": 3600,
            },
        )
        with patch.object(auth, "_supabase_request", AsyncMock(return_value=provider_response)):
            with self.assertRaises(auth.HTTPException) as raised:
                await auth.mfa_complete_login(
                    auth.MfaLoginCodeRequest(factor_id="factor-1", challenge_id="challenge-1", code="123456"),
                    request_with_cookies(
                        f"{auth.MFA_PENDING_ACCESS_COOKIE_NAME}=aal1-access; "
                        f"{auth.MFA_PENDING_FACTOR_COOKIE_NAME}=factor-1; "
                        f"{auth.MFA_PENDING_CHALLENGE_COOKIE_NAME}=challenge-1"
                    ),
                )
        self.assertEqual(raised.exception.status_code, 503)

    async def test_confirmation_session_with_verified_totp_is_challenged(self):
        user = {
            "id": "owner-a",
            "email": "a@example.com",
            "email_confirmed_at": "2026-09-18T12:00:00Z",
            "factors": [{"id": "factor-1", "factor_type": "totp", "status": "verified"}],
        }
        with (
            patch.object(auth, "user_from_token", AsyncMock(return_value=user)),
            patch.object(auth, "_supabase_request", AsyncMock(return_value=httpx.Response(200, json={"id": "challenge-1"}))),
        ):
            response = await auth.accept_session(
                auth.SessionRequest(
                    access_token=unsigned_jwt_with_aal("aal1"),
                    refresh_token="aal1-refresh",
                    expires_in=3600,
                )
            )

        body = json.loads(response.body)
        self.assertFalse(body["authenticated"])
        self.assertTrue(body["mfa_required"])
        cookies = response.headers.getlist("set-cookie")
        self.assertTrue(any(item.startswith(auth.MFA_PENDING_ACCESS_COOKIE_NAME + "=") for item in cookies))
        self.assertFalse(any(item.startswith(auth.ACCESS_COOKIE_NAME + "=") for item in cookies))

    async def test_enrollment_verification_promotes_provider_aal2_session(self):
        session = {
            "access_token": unsigned_jwt_with_aal("aal2"),
            "refresh_token": "elevated-refresh",
            "expires_in": 3600,
        }
        request = request_with_cookies(f"{auth.ACCESS_COOKIE_NAME}=existing-aal1")
        with patch.object(
            auth,
            "_supabase_request",
            AsyncMock(return_value=httpx.Response(200, json=session)),
        ):
            response = await auth.mfa_verify(
                auth.MfaCodeRequest(factor_id="factor-1", challenge_id="challenge-1", code="123456"),
                request,
                {"id": "owner-a"},
            )
        self.assertTrue(json.loads(response.body)["verified"])
        self.assertFalse(json.loads(response.body)["reauth_required"])
        self.assertTrue(any(auth.ACCESS_COOKIE_NAME + "=" + session["access_token"] in value for value in response.headers.getlist("set-cookie")))

    async def test_mfa_status_uses_factors_from_authenticated_user(self):
        response = await auth.mfa_status(
            request_with_cookies(f"{auth.ACCESS_COOKIE_NAME}=access-token"),
            {"id": "owner-a", "factors": [{
                "id": "factor-1",
                "factor_type": "totp",
                "status": "verified",
                "friendly_name": "Agente de Candidaturas",
            }]},
        )

        self.assertTrue(response["enabled"])
        self.assertEqual(response["factors"][0]["id"], "factor-1")


if __name__ == "__main__":
    unittest.main()
