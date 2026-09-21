import os
import unittest
from unittest.mock import patch

from app import auth, customer_success, gmail_integration, outlook_integration
from app import main as main_module


class PublicUrlTests(unittest.TestCase):
    def test_all_public_links_default_to_candidatura_certa_domain(self):
        with patch.dict(
            os.environ,
            {
                "APP_BASE_URL": "",
                "RENDER_EXTERNAL_HOSTNAME": "agente-de-candidaturas.onrender.com",
            },
            clear=False,
        ):
            expected = "https://candidaturacerta.com.br"
            self.assertEqual(auth._app_base_url(), expected)
            self.assertEqual(main_module._public_base_url(), expected)
            self.assertEqual(customer_success._public_base_url(), expected)

    def test_gmail_callback_defaults_to_public_domain_when_override_is_empty(self):
        with (
            patch.dict(os.environ, {"GOOGLE_REDIRECT_URI": ""}, clear=False),
            patch.object(gmail_integration, "APP_BASE_URL", "https://candidaturacerta.com.br"),
        ):
            self.assertEqual(
                gmail_integration._redirect_uri(),
                "https://candidaturacerta.com.br/auth/gmail/callback",
            )

    def test_outlook_callback_defaults_to_public_domain_when_override_is_empty(self):
        with (
            patch.dict(os.environ, {"OUTLOOK_REDIRECT_URI": ""}, clear=False),
            patch.object(outlook_integration, "APP_BASE_URL", "https://candidaturacerta.com.br"),
        ):
            self.assertEqual(
                outlook_integration._redirect(),
                "https://candidaturacerta.com.br/auth/outlook/callback",
            )


if __name__ == "__main__":
    unittest.main()
