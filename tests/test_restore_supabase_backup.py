import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import restore_supabase_backup


class RestoreSupabaseBackupTest(unittest.TestCase):
    def test_rejects_non_disposable_project_ids(self):
        for project_id in ("production", "codex_restore_prod", "codex-restore-test"):
            with self.subTest(project_id=project_id):
                with self.assertRaises(ValueError):
                    restore_supabase_backup._validated_project_id(project_id)

    def test_archive_manifest_checksum_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "sample.dump.enc"
            archive.write_bytes(b"encrypted backup")
            manifest = archive.with_name(f"{archive.name}.json")
            manifest.write_text(
                json.dumps(
                    {
                        "filename": archive.name,
                        "format": "AES-256-GCM + RSA-OAEP-SHA256",
                        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(restore_supabase_backup._validated_archive(archive), b"encrypted backup")

            manifest.write_text(
                json.dumps(
                    {
                        "filename": archive.name,
                        "format": "AES-256-GCM + RSA-OAEP-SHA256",
                        "sha256": "wrong",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "manifesto"):
                restore_supabase_backup._validated_archive(archive)

    def test_restore_requires_explicit_disposable_confirmation(self):
        with self.assertRaisesRegex(ValueError, "descartável"):
            restore_supabase_backup.restore_archive(
                archive_path=Path("unused.dump.enc"),
                private_key_path=Path("unused.pem"),
                project_id="codex_restore_test",
                confirm_disposable=False,
            )

    def test_rejects_remote_docker_context(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(restore_supabase_backup, "_run", return_value=b'"tcp://remote.example:2376"') as run,
        ):
            with self.assertRaisesRegex(RuntimeError, "endpoint local"):
                restore_supabase_backup._verify_local_docker_engine("docker")
        self.assertEqual(run.call_count, 1)

    def test_rejects_docker_host_environment_override(self):
        with (
            patch.dict(os.environ, {"DOCKER_HOST": "tcp://remote.example:2376"}, clear=True),
            patch.object(restore_supabase_backup, "_run") as run,
        ):
            with self.assertRaisesRegex(RuntimeError, "overrides DOCKER_HOST"):
                restore_supabase_backup._verify_local_docker_engine("docker")
        run.assert_not_called()

    def test_accepts_local_docker_desktop_endpoint(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(restore_supabase_backup, "_run", side_effect=(b'"npipe:////./pipe/dockerDesktopLinuxEngine"', b"29.8.0")) as run,
        ):
            restore_supabase_backup._verify_local_docker_engine("docker")
        self.assertEqual(run.call_count, 2)

    def test_database_container_requires_supabase_cli_project_labels(self):
        metadata = (
            '{"com.supabase.cli.project":"codex_restore_test",'
            '"com.docker.compose.project":"codex_restore_test"}'
            '|public.ecr.aws/supabase/postgres:17.6.1'
        ).encode()
        with patch.object(
            restore_supabase_backup,
            "_run",
            side_effect=(b"supabase_db_codex_restore_test\n", metadata),
        ):
            self.assertEqual(
                restore_supabase_backup._database_container("docker", "codex_restore_test"),
                "supabase_db_codex_restore_test",
            )
        wrong_project = metadata.replace(b"codex_restore_test", b"another_project")
        with patch.object(
            restore_supabase_backup,
            "_run",
            side_effect=(b"supabase_db_codex_restore_test\n", wrong_project),
        ):
            with self.assertRaisesRegex(RuntimeError, "não pertence"):
                restore_supabase_backup._database_container("docker", "codex_restore_test")

    def test_rls_validation_requires_every_table_to_have_rls_and_a_policy(self):
        with patch.object(restore_supabase_backup, "_query", side_effect=("11", "10", "0")):
            with self.assertRaisesRegex(RuntimeError, "todas as tabelas"):
                restore_supabase_backup._validate_rls_coverage("docker", "container", "db", 11)
        with patch.object(restore_supabase_backup, "_query", side_effect=("11", "11", "1")):
            with self.assertRaisesRegex(RuntimeError, "sem política"):
                restore_supabase_backup._validate_rls_coverage("docker", "container", "db", 11)
        with patch.object(restore_supabase_backup, "_query", side_effect=("11", "11", "0")):
            self.assertEqual(
                restore_supabase_backup._validate_rls_coverage("docker", "container", "db", 11),
                (11, 11),
            )

    def test_error_summary_redacts_database_values_and_context(self):
        summary = restore_supabase_backup._safe_error_summary(
            b'pg_restore: error: ERROR: duplicate key value violates constraint "users_email_key" '
            b'DETAIL: Key (email)=(candidate@example.com) already exists.'
        )
        self.assertIn("duplicate key", summary)
        self.assertNotIn("candidate@example.com", summary)
        self.assertNotIn("users_email_key", summary)
        self.assertNotIn("DETAIL", summary)

    def test_error_summary_decodes_windows_cli_output_without_exposing_values(self):
        summary = restore_supabase_backup._safe_error_summary(
            'pg_restore: error: ERROR: permission denied for "secret@example.com"'.encode("utf-16-le")
        )
        self.assertIn("permission denied", summary)
        self.assertNotIn("secret@example.com", summary)

    def test_restore_targets_exact_local_container_and_reports_aggregate_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "sample.dump.enc"
            archive.write_bytes(b"encrypted backup")
            archive.with_name(f"{archive.name}.json").write_text(
                json.dumps(
                    {
                        "filename": archive.name,
                        "format": "AES-256-GCM + RSA-OAEP-SHA256",
                        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            outputs = iter((b"", b"", b"", b""))
            commands = []

            def fake_run(command, *, input_bytes=None, timeout=1200, operation="comando local"):
                commands.append((list(command), input_bytes))
                return next(outputs)

            with (
                patch.object(restore_supabase_backup, "_validated_archive", return_value=b"encrypted"),
                patch.object(restore_supabase_backup, "decrypt_bytes", return_value=b"PGDMP-valid"),
                patch.object(restore_supabase_backup, "_docker_executable", return_value="docker"),
                patch.object(restore_supabase_backup, "_verify_local_docker_engine"),
                patch.object(restore_supabase_backup, "_database_container", return_value="supabase_db_codex_restore_test"),
                patch.object(restore_supabase_backup, "_run", side_effect=fake_run),
                patch.object(
                    restore_supabase_backup,
                    "_query",
                    side_effect=("applications\njobs", "3", "2", "4", "2", "0"),
                ),
            ):
                result = restore_supabase_backup.restore_archive(
                    archive_path=archive,
                    private_key_path=Path(directory) / "private.pem",
                    project_id="codex_restore_test",
                    confirm_disposable=True,
                )

            self.assertEqual(result["public_tables"], 2)
            self.assertEqual(result["aggregate_rows"], 5)
            self.assertEqual(result["public_rls_policies"], 4)
            self.assertEqual(result["public_rls_enabled_tables"], 2)
            restore_command, restore_input = next(
                (command, input_bytes)
                for command, input_bytes in commands
                if "pg_restore" in command and "--exit-on-error" in command
            )
            self.assertIn("supabase_db_codex_restore_test", restore_command)
            self.assertEqual(restore_command[-2], "--dbname")
            self.assertEqual(restore_command[-1], "codex_restore_test")
            self.assertIn("supabase_admin", restore_command)
            self.assertEqual(restore_command[restore_command.index("--user") + 1], "postgres")
            self.assertEqual(restore_input, b"PGDMP-valid")


if __name__ == "__main__":
    unittest.main()
