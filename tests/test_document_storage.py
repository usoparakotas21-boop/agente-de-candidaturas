import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import document_storage


class DocumentStorageTest(unittest.TestCase):
    def test_cleanup_removes_only_expired_document_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_doc = root / "old.docx"
            old_doc.write_bytes(b"doc")
            old_time = time.time() - 3 * 86400
            import os

            os.utime(old_doc, (old_time, old_time))
            keep_doc = root / "keep.docx"
            keep_doc.write_bytes(b"doc")
            unrelated = root / "keep.txt"
            unrelated.write_bytes(b"txt")
            with patch.object(document_storage, "OUTPUT_DIR", root):
                self.assertEqual(document_storage.cleanup_expired_documents(max_age_days=2), 1)
            self.assertFalse(old_doc.exists())
            self.assertTrue(keep_doc.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
