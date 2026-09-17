import io
import unittest
import zipfile

from PIL import Image

from app.resume_importer import parse_resume_pdf
from app.upload_validation import validate_image_upload, validate_magic_bytes


class UploadValidationTest(unittest.TestCase):
    def test_image_requires_matching_magic_bytes(self):
        with self.assertRaisesRegex(ValueError, "conteudo"):
            validate_image_upload(b"nao e png", "foto.png", max_bytes=1_500_000)

    def test_image_is_decoded_before_acceptance(self):
        output = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(output, format="PNG")
        self.assertEqual(
            validate_image_upload(output.getvalue(), "foto.png", max_bytes=1_500_000),
            "image/png",
        )

    def test_resume_pdf_requires_pdf_signature(self):
        with self.assertRaisesRegex(ValueError, "conteudo"):
            parse_resume_pdf(b"arquivo falso", "curriculo.pdf")

    def test_docx_requires_zip_structure(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as value:
            value.writestr("not-document.txt", "x")
        with self.assertRaisesRegex(ValueError, "estrutura DOCX"):
            validate_magic_bytes(archive.getvalue(), "curriculo.docx", allowed={".docx"})


if __name__ == "__main__":
    unittest.main()
