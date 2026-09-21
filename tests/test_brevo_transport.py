import os
import unittest
from email.message import EmailMessage
from unittest.mock import patch

from app import main as main_module


class _Response:
    def raise_for_status(self):
        return None


class _Client:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, *, headers, json):
        self.calls.append((url, headers, json))
        return _Response()


class _SMTP:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        return None

    def login(self, username, password):
        return None

    def send_message(self, message):
        return None


class BrevoTransportTests(unittest.TestCase):
    def test_brevo_https_payload_preserves_text_reply_to_and_attachments(self):
        message = EmailMessage()
        message["From"] = "Candidatura Certa <contato@candidaturacerta.com.br>"
        message["To"] = "Pessoa <pessoa@example.com>"
        message["Reply-To"] = "contato@candidaturacerta.com.br"
        message["Subject"] = "Documento pronto"
        message.set_content("Seu documento está pronto.")
        message.add_attachment(b"pdf-bytes", maintype="application", subtype="pdf", filename="curriculo.pdf")

        client = _Client()
        with patch.dict(os.environ, {"BREVO_API_KEY": "test-key"}, clear=False), patch.object(
            main_module.httpx, "Client", return_value=client
        ):
            main_module._send_via_brevo_api(message, timeout=5)

        url, headers, payload = client.calls[0]
        self.assertEqual(url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(headers["api-key"], "test-key")
        self.assertEqual(payload["sender"]["email"], "contato@candidaturacerta.com.br")
        self.assertEqual(payload["to"][0]["email"], "pessoa@example.com")
        self.assertEqual(payload["replyTo"]["email"], "contato@candidaturacerta.com.br")
        self.assertIn("Seu documento está pronto.", payload["textContent"])
        self.assertEqual(payload["attachment"][0]["name"], "curriculo.pdf")

    def test_complete_smtp_configuration_wins_over_a_leftover_brevo_key(self):
        message = EmailMessage()
        message["From"] = "contato@candidaturacerta.com.br"
        message["To"] = "pessoa@example.com"
        message["Subject"] = "Documento pronto"
        message.set_content("Seu documento está pronto.")
        smtp_config = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_FROM_EMAIL": "contato@candidaturacerta.com.br",
            "SMTP_USERNAME": "smtp-user",
            "SMTP_PASSWORD": "smtp-password",
            "SMTP_USE_TLS": "true",
            "BREVO_API_KEY": "leftover-test-key",
        }
        with patch.dict(os.environ, smtp_config, clear=False), patch.object(
            main_module.smtplib, "SMTP", return_value=_SMTP()
        ) as smtp, patch.object(main_module, "_send_via_brevo_api") as brevo:
            config = main_module._email_transport_config()
            transport = main_module._send_email_message(message, config, timeout=5)

        self.assertEqual(transport, "smtp")
        smtp.assert_called_once()
        brevo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
