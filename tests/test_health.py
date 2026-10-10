import json
import unittest
from unittest.mock import MagicMock, patch

from app import main


class HealthTests(unittest.TestCase):
    def test_connected_database_closes_session_and_returns_only_health(self):
        session = MagicMock()
        with patch.object(main, "SessionLocal", return_value=session):
            self.assertEqual(main.health(), {"status": "ok", "db": "connected"})
        session.__enter__.return_value.execute.assert_called_once()
        session.__exit__.assert_called_once()

    def test_database_failure_returns_503_without_exposing_details(self):
        session = MagicMock()
        session.__enter__.return_value.execute.side_effect = RuntimeError("private database address")
        with patch.object(main, "SessionLocal", return_value=session):
            response = main.health()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body), {"status": "error", "db": "unavailable"})
        session.__exit__.assert_called_once()
