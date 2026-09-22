import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import main as main_module


class _FakeSMTP:
    messages = []

    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self):
        return None

    def login(self, *_args):
        return None

    def send_message(self, message):
        type(self).messages.append(message)


class EmailDeliveryTests(unittest.TestCase):
    def setUp(self):
        _FakeSMTP.messages = []
        self.user = {
            "id": "email-test-owner",
            "email": "confirmed@example.com",
            "email_confirmed_at": "2026-09-21T00:00:00Z",
        }
        self.smtp_config = {
            "host": "smtp.example.com",
            "port": 587,
            "use_tls": True,
            "use_ssl": False,
            "username": "relay@example.com",
            "password": "test-only-secret",
            "sender": "Candidatura Certa <contato@candidaturacerta.com.br>",
        }

    def test_confirmed_account_receives_safe_probe(self):
        with (
            patch.object(main_module, "_email_transport_config", return_value=self.smtp_config),
            patch.object(main_module, "_enforce_rate_limit"),
            patch.object(main_module.smtplib, "SMTP", _FakeSMTP),
        ):
            result = main_module.send_test_email(user=self.user)

        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["transport"], "smtp")
        self.assertEqual(len(_FakeSMTP.messages), 1)
        message = _FakeSMTP.messages[0]
        self.assertEqual(message["To"], self.user["email"])
        self.assertIn("Teste de entrega", message["Subject"])
        self.assertIn("não contém dados sensíveis", message.get_content())

    def test_unconfirmed_account_is_refused_before_transport(self):
        user = {"id": self.user["id"], "email": self.user["email"]}
        with patch.object(main_module, "_send_email_message") as send:
            with self.assertRaises(HTTPException) as raised:
                main_module.send_test_email(user=user)
        self.assertEqual(raised.exception.status_code, 403)
        send.assert_not_called()

    def test_missing_transport_returns_safe_unavailable_response(self):
        with patch.object(main_module, "_email_transport_config", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                main_module.send_test_email(user=self.user)
        self.assertEqual(raised.exception.status_code, 503)

    def test_transport_failure_does_not_expose_provider_details(self):
        with (
            patch.object(main_module, "_email_transport_config", return_value=self.smtp_config),
            patch.object(main_module, "_enforce_rate_limit"),
            patch.object(main_module, "_send_email_message", side_effect=OSError("secret relay detail")),
        ):
            with self.assertRaises(HTTPException) as raised:
                main_module.send_test_email(user=self.user)
        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn("secret relay detail", str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()
