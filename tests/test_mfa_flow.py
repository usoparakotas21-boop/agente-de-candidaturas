import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from starlette.requests import Request

from app import auth


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
    async def test_login_requires_totp_and_complete_promotes_session(self):
        login_session = {
            "access_token": "aal1-access",
            "refresh_token": "aal1-refresh",
            "expires_in": 3600,
            "user": {"id": "owner-a", "email": "a@example.com"},
        }
        responses = [
            httpx.Response(200, json=login_session),
            httpx.Response(200, json={"totp": [{"id": "factor-1", "status": "verified"}]}),
            httpx.Response(200, json={"id": "challenge-1"}),
        ]
        with (
            patch.dict("os.environ", {"MFA_LOGIN_ENFORCE": "true"}, clear=False),
            patch.object(auth, "_supabase_request", AsyncMock(side_effect=responses)),
        ):
            response = await auth.login(auth.LoginRequest(email="a@example.com", password="Senha-segura1!"))

        body = json.loads(response.body)
        self.assertFalse(body["authenticated"])
        self.assertTrue(body["mfa_required"])
        cookies = "; ".join(item.split(";", 1)[0] for item in response.headers.getlist("set-cookie"))
        self.assertIn(auth.MFA_PENDING_ACCESS_COOKIE_NAME, cookies)
        self.assertNotIn(auth.ACCESS_COOKIE_NAME + "=aal1-access", cookies)

        verified_session = {
            "access_token": "aal2-access",
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
        self.assertTrue(any(auth.ACCESS_COOKIE_NAME + "=aal2-access" in value for value in complete.headers.getlist("set-cookie")))
        self.assertTrue(request_mock.await_args.kwargs["json"]["challenge_id"] == "challenge-1")

    async def test_mfa_completion_rejects_missing_pending_session(self):
        with self.assertRaises(auth.HTTPException) as raised:
            await auth.mfa_complete_login(
                auth.MfaLoginCodeRequest(factor_id="factor-1", challenge_id="challenge-1", code="123456"),
                request_with_cookies(),
            )
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
