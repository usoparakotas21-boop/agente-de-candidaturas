import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import outlook_integration as outlook
from app import outlook_monitor
from app.database import Base
from app.models import EmailIntegration


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/outlook/callback",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "https",
        }
    )


class _MockAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, data):
        return httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "scope": "Mail.Read User.Read",
            },
        )

    async def get(self, url, headers):
        return httpx.Response(
            200,
            json={"mail": "pessoa@example.com"},
        )


class OutlookIntegrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'outlook.db'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)
        self.key = Fernet.generate_key().decode("ascii")

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    async def test_start_builds_signed_authorization_request(self):
        environment = {
            "OUTLOOK_CLIENT_ID": "client-id",
            "OUTLOOK_CLIENT_SECRET": "client-secret",
            "OUTLOOK_REDIRECT_URI": "https://app.example.com/auth/outlook/callback",
        }
        with patch.dict("os.environ", environment, clear=False):
            response = await outlook.start(user={"id": "owner-a"})
            query = parse_qs(urlparse(response.headers["location"]).query)
            outlook._validate_state(query["state"][0], "owner-a")

        self.assertEqual(query["client_id"], ["client-id"])
        self.assertIn("Mail.Read", query["scope"][0])
        self.assertEqual(query["redirect_uri"], [environment["OUTLOOK_REDIRECT_URI"]])

    async def test_callback_encrypts_and_persists_refresh_token(self):
        environment = {
            "OUTLOOK_CLIENT_ID": "client-id",
            "OUTLOOK_CLIENT_SECRET": "client-secret",
            "OUTLOOK_REDIRECT_URI": "https://app.example.com/auth/outlook/callback",
            "TOKEN_ENCRYPTION_KEY": self.key,
        }
        with patch.dict("os.environ", environment, clear=False):
            state = outlook._state("owner-a")
            with (
                patch.object(outlook, "SessionLocal", self.session),
                patch.object(
                    outlook,
                    "authenticated_user",
                    AsyncMock(return_value={"id": "owner-a"}),
                ),
                patch.object(outlook.httpx, "AsyncClient", _MockAsyncClient),
            ):
                response = await outlook.callback(
                    make_request(), code="authorization-code", state=state
                )

        with self.session() as db:
            integration = db.scalar(select(EmailIntegration))
            encrypted_token = integration.encrypted_refresh_token
            self.assertEqual(integration.owner_id, "owner-a")
            self.assertEqual(integration.provider, "outlook")
            self.assertEqual(integration.email, "pessoa@example.com")
        self.assertEqual(
            Fernet(self.key.encode("ascii")).decrypt(encrypted_token.encode()).decode(),
            "refresh-token",
        )
        self.assertEqual(response.status_code, 303)

    def test_graph_message_is_normalized_for_shared_job_parser(self):
        message = outlook_monitor._graph_to_message(
            {
                "subject": "Vaga: Analista de RH",
                "from": {"emailAddress": {"name": "Alertas", "address": "jobs@example.com"}},
                "body": {"contentType": "html", "content": "<b>Analista de RH</b><br>Empresa Alpha"},
                "bodyPreview": "Analista de RH Empresa Alpha",
            }
        )

        parsed = outlook_monitor._message_content(message)
        self.assertEqual(parsed["subject"], "Vaga: Analista de RH")
        self.assertEqual(parsed["sender"], "Alertas")
        self.assertIn("Empresa Alpha", parsed["content"])


if __name__ == "__main__":
    unittest.main()
