import hashlib
import unittest
from unittest.mock import patch

import httpx

from app import auth


class _FakePasswordClient:
    last_url = ""
    last_headers = {}

    def __init__(self, *, timeout, headers):
        self.last_headers = headers
        _FakePasswordClient.last_headers = headers

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url):
        _FakePasswordClient.last_url = url
        suffix = hashlib.sha1("StrongPassword!123".encode()).hexdigest().upper()[5:]
        return httpx.Response(200, text=f"{suffix}:4\n")


class PasswordSecurityTest(unittest.IsolatedAsyncioTestCase):
    async def test_k_anonymized_check_rejects_known_compromised_password(self):
        with patch.object(auth, "PWNED_PASSWORD_CHECK", True), patch.object(
            auth.httpx, "AsyncClient", _FakePasswordClient
        ):
            self.assertTrue(await auth._password_was_compromised("StrongPassword!123"))

        full_hash = hashlib.sha1("StrongPassword!123".encode()).hexdigest().upper()
        self.assertNotIn(full_hash, _FakePasswordClient.last_url)
        self.assertEqual(len(_FakePasswordClient.last_url.rsplit("/", 1)[-1]), 5)
        self.assertEqual(_FakePasswordClient.last_headers["Add-Padding"], "true")

    async def test_check_is_disabled_without_production_flag(self):
        with patch.object(auth, "PWNED_PASSWORD_CHECK", False):
            self.assertFalse(await auth._password_was_compromised("StrongPassword!123"))


if __name__ == "__main__":
    unittest.main()
