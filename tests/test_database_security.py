import unittest
from pathlib import Path

from app.database import _normalize_database_url


class DatabaseSecurityTest(unittest.TestCase):
    def test_postgresql_urls_use_psycopg_and_require_tls(self):
        self.assertEqual(
            _normalize_database_url("postgresql://user:pass@db.example/app"),
            "postgresql+psycopg://user:pass@db.example/app?sslmode=require",
        )
        normalized = _normalize_database_url(
            "postgres://user:pass@db.example/app?connect_timeout=5"
        )
        self.assertTrue(normalized.startswith("postgresql+psycopg://"))
        self.assertIn("sslmode=require", normalized)

    def test_existing_sslmode_is_preserved(self):
        value = "postgresql+psycopg://user:pass@db.example/app?sslmode=verify-full"
        self.assertEqual(_normalize_database_url(value), value)

    def test_sqlite_is_unchanged(self):
        value = "sqlite:///data/agente.db"
        self.assertEqual(_normalize_database_url(value), value)

    def test_service_role_key_is_not_declared_in_deploy_config(self):
        render_config = Path("render.yaml").read_text(encoding="utf-8")
        self.assertNotIn("SERVICE_ROLE_KEY", render_config)


if __name__ == "__main__":
    unittest.main()
