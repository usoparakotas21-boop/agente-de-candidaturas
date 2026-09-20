import tempfile
import unittest
from pathlib import Path

from cryptography.exceptions import InvalidTag

from scripts.backup_encryption import (
    decrypt_bytes,
    decrypt_dump,
    encrypt_dump,
    generate_keypair,
)


class BackupEncryptionTest(unittest.TestCase):
    def test_encrypted_backup_round_trips_and_removes_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = root / "private.pem"
            public_key = root / "public.pem"
            dump = root / "database.dump"
            expected = b"private database dump contents"
            generate_keypair(private_key, public_key)
            dump.write_bytes(expected)
            dump.with_suffix(".dump.sha256").write_text("plaintext checksum")
            dump.with_suffix(".dump.json").write_text("plaintext manifest")

            encrypted = encrypt_dump(dump, public_key, private_key_path=private_key)

            self.assertTrue(encrypted.is_file())
            self.assertFalse(dump.exists())
            self.assertFalse(dump.with_suffix(".dump.sha256").exists())
            self.assertFalse(dump.with_suffix(".dump.json").exists())
            self.assertEqual(decrypt_bytes(encrypted.read_bytes(), private_key), expected)

            restored = root / "restored.dump"
            decrypt_dump(encrypted, private_key, restored)
            self.assertEqual(restored.read_bytes(), expected)

    def test_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = root / "private.pem"
            public_key = root / "public.pem"
            dump = root / "database.dump"
            generate_keypair(private_key, public_key)
            dump.write_bytes(b"private database dump contents")
            encrypted = encrypt_dump(
                dump,
                public_key,
                private_key_path=private_key,
                delete_plaintext=False,
            )
            tampered = bytearray(encrypted.read_bytes())
            tampered[-1] ^= 1
            with self.assertRaises(InvalidTag):
                decrypt_bytes(bytes(tampered), private_key)

    def test_key_generation_does_not_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = root / "private.pem"
            public_key = root / "public.pem"
            private_key.write_text("keep")
            with self.assertRaises(FileExistsError):
                generate_keypair(private_key, public_key)
            self.assertEqual(private_key.read_text(), "keep")
            self.assertFalse(public_key.exists())

    def test_encryption_does_not_overwrite_an_existing_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = root / "private.pem"
            public_key = root / "public.pem"
            dump = root / "database.dump"
            generate_keypair(private_key, public_key)
            dump.write_bytes(b"first dump")
            archive = encrypt_dump(
                dump,
                public_key,
                private_key_path=private_key,
                delete_plaintext=False,
            )
            original_archive = archive.read_bytes()
            dump.write_bytes(b"second dump")

            with self.assertRaises(FileExistsError):
                encrypt_dump(dump, public_key, private_key_path=private_key)

            self.assertEqual(archive.read_bytes(), original_archive)
            self.assertEqual(dump.read_bytes(), b"second dump")


if __name__ == "__main__":
    unittest.main()
