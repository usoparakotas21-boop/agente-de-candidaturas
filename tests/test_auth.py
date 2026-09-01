import unittest
from unittest.mock import AsyncMock, patch

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
