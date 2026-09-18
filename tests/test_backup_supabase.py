import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import backup_supabase


class SupabaseBackupTest(unittest.TestCase):
    def test_rejects_missing_or_non_postgres_database_url(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                backup_supabase._database_url()
        with patch.dict("os.environ", {"DATABASE_URL": "sqlite:///local.db"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
                backup_supabase._database_url()

    def test_backup_is_verified_and_does_not_put_url_on_command_line(self):
        commands = []

        def fake_run(command, **kwargs):
            commands.append((command, kwargs))
            if "--file" in command:
                output = Path(command[command.index("--file") + 1])
                output.write_bytes(b"PGDMP-test")
            return None

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {"DATABASE_URL": "postgresql://user:secret@example.invalid/db"},
            clear=True,
        ), patch.object(
            backup_supabase.shutil,
            "which",
            side_effect=lambda name: f"/tools/{name}",
        ), patch.object(backup_supabase.subprocess, "run", side_effect=fake_run):
            result = backup_supabase.create_backup(Path(directory))

            self.assertTrue(result.is_file())
            self.assertTrue(result.with_suffix(result.suffix + ".sha256").is_file())
            self.assertTrue(result.with_suffix(result.suffix + ".json").is_file())
            self.assertEqual(len(commands), 2)
            for command, kwargs in commands:
                self.assertNotIn("postgresql://user:secret", " ".join(command))
                if "--file" in command:
                    self.assertNotIn("DATABASE_URL", kwargs["env"])
                    self.assertEqual(
                        kwargs["env"]["PGDATABASE"],
                        "postgresql://user:secret@example.invalid/db",
                    )


if __name__ == "__main__":
    unittest.main()
