import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import job_file_intake
from app.job_file_intake import MAX_JOB_FILE_BYTES, extract_job_file_text


class JobFileIntakeTest(unittest.TestCase):
    def test_rejects_unsupported_file(self):
        with self.assertRaisesRegex(ValueError, "PNG"):
            extract_job_file_text(b"conteudo", "vaga.txt")

    def test_rejects_empty_file(self):
        with self.assertRaisesRegex(ValueError, "vazio"):
            extract_job_file_text(b"", "vaga.png")

    def test_rejects_oversized_file(self):
        with self.assertRaisesRegex(ValueError, "10 MB"):
            extract_job_file_text(b"x" * (MAX_JOB_FILE_BYTES + 1), "vaga.png")

    @patch("app.job_file_intake._ocr_text")
    def test_returns_ocr_metadata(self, mocked_ocr):
        mocked_ocr.return_value = (
            "Cargo: Coordenador de RH\nEmpresa: Exemplo\n"
            "Localizacao: Salvador/BA\nModalidade: Presencial\n"
            "Descricao da vaga\nResponsavel pela area de Recursos Humanos.\n"
            "Requisitos\nExperiencia em recrutamento e selecao.\n"
            "Conhecimento de indicadores e gestao de equipes.\n"
            "Dominio de legislacao trabalhista e departamento pessoal.\n"
            "Atuacao com treinamento, beneficios e folha de pagamento.\n"
            "Buscamos uma pessoa organizada, analitica e colaborativa."
        )
        result = extract_job_file_text(b"imagem", "vaga.png")
        self.assertEqual(result["method"], "local_ocr")
        self.assertIn("Coordenador", result["text"])

    def test_ocr_removes_temporary_files_when_engine_fails(self):
        image = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(image, format="PNG")
        created: list[Path] = []
        real_named_temporary_file = tempfile.NamedTemporaryFile

        def tracked_named_temporary_file(*args, **kwargs):
            handle = real_named_temporary_file(*args, **kwargs)
            created.append(Path(handle.name))
            return handle

        class FailingEngine:
            def __call__(self, _path):
                raise RuntimeError("falha simulada do OCR")

        with patch.object(job_file_intake.tempfile, "NamedTemporaryFile", tracked_named_temporary_file), patch.object(
            job_file_intake, "_ocr_engine", return_value=FailingEngine()
        ):
            with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                job_file_intake._ocr_text(image.getvalue(), ".png")

        self.assertTrue(created)
        self.assertTrue(all(not path.exists() for path in created))


if __name__ == "__main__":
    unittest.main()
