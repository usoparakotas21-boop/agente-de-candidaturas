import json
import unittest

from app import main as main_module


class ErrorHandlingTest(unittest.IsolatedAsyncioTestCase):
    async def test_unhandled_errors_use_generic_public_message(self):
        response = await main_module.unhandled_error(
            main_module.Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/private",
                    "headers": [],
                    "query_string": b"",
                    "server": ("testserver", 80),
                    "client": ("testclient", 50000),
                    "scheme": "https",
                }
            ),
            RuntimeError("senha do banco super secreta"),
        )
        body = json.loads(response.body)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("super secreta", body["detail"])
        self.assertEqual(body["code"], "internal_error")


if __name__ == "__main__":
    unittest.main()
