import os
import unittest
from unittest.mock import patch

from app import auth, customer_success
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


if __name__ == "__main__":
    unittest.main()
