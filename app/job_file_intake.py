from __future__ import annotations

import io
import tempfile
import warnings
from pathlib import Path
from typing import Any

import numpy as np
from pypdf import PdfReader


MAX_JOB_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_IMAGE_PIXELS = 30_000_000
MIN_OCR_CHARS = 250
MIN_OCR_LINES = 8
SUPPORTED_JOB_FILES = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
_OCR_ENGINE: Any | None = None


class OCRUnavailableError(RuntimeError):
    pass


def _validated_image(content: bytes, suffix: str):
    signatures = {
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }
    if not signatures.get(suffix, False):
        raise ValueError("O conteudo do arquivo nao corresponde ao formato informado.")

    try:
        from PIL import Image
    except ImportError as exc:
        raise OCRUnavailableError(
            "O leitor de imagens ainda nao foi instalado no servidor."
        ) from exc

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                return image.convert("RGB")
        except Exception as exc:
            raise ValueError("A imagem esta corrompida ou excede o limite seguro.") from exc


def _central_content_crop(image):
    width, height = image.size
    if width < 900 or height < 600:
        return image

    gray = np.asarray(image.convert("L"))
    start_y = max(1, int(height * 0.08))
    ink = gray[start_y:, :] < 242
    column_density = ink.sum(axis=0)
    minimum_column_ink = max(8, int((height - start_y) * 0.012))
    active_columns = np.flatnonzero(column_density >= minimum_column_ink)
    if active_columns.size < 40:
        return image

    x0 = int(active_columns[0])
    x1 = int(active_columns[-1]) + 1
    if x1 - x0 < int(width * 0.16):
        return image

    margin_x = max(12, int(width * 0.025))
    x0 = max(0, x0 - margin_x)
    x1 = min(width, x1 + margin_x)

    row_density = ink[:, x0:x1].sum(axis=1)
    minimum_row_ink = max(6, int((x1 - x0) * 0.008))
    active_rows = np.flatnonzero(row_density >= minimum_row_ink)
    if active_rows.size < 20:
        return image

    y0 = start_y + int(active_rows[0])
    y1 = start_y + int(active_rows[-1]) + 1
    margin_y = max(12, int(height * 0.018))
    y0 = max(start_y, y0 - margin_y)
    y1 = min(height, y1 + margin_y)
    return image.crop((x0, y0, x1, y1))


def _ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise OCRUnavailableError(
            "OCR nao instalado. Execute: python -m pip install rapidocr onnxruntime"
        ) from exc
    _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _unique_lines(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        line = " ".join(str(value).split())
        key = line.casefold()
        if not line or key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def _ocr_text(content: bytes, suffix: str) -> str:
    from PIL import Image

    image = _validated_image(content, suffix)
    crop = _central_content_crop(image)
    variants = [image]
    if crop.size != image.size:
        scale = min(4.0, max(2.0, 1800 / max(crop.width, 1)))
        resized = crop.resize(
            (int(crop.width * scale), int(crop.height * scale)),
            resample=Image.Resampling.LANCZOS,
        )
        # The enlarged crop is more reliable for title, company and body.
        # Keep the original last so it can still contribute the address bar URL.
        variants = [resized, image]

    temp_paths: list[Path] = []
    try:
        lines: list[str] = []
        engine = _ocr_engine()
        for variant in variants:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                temp_path = Path(temp_file.name)
                temp_paths.append(temp_path)
            variant.save(temp_path, format="PNG", optimize=True)
            result = engine(str(temp_path))
            texts = getattr(result, "txts", None) or ()
            lines.extend(str(value) for value in texts)
        return "\n".join(_unique_lines(lines))
    finally:
        for temp_path in temp_paths:
            temp_path.unlink(missing_ok=True)


def _pdf_text(content: bytes) -> str:
    if not content.startswith(b"%PDF-"):
        raise ValueError("O conteudo do arquivo nao corresponde a um PDF.")
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise ValueError("Nao foi possivel abrir o PDF enviado.") from exc

    if reader.is_encrypted:
        raise ValueError("PDF protegido por senha nao pode ser processado.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError("O PDF excede o limite de 20 paginas.")

    lines = []
    for page in reader.pages:
        value = page.extract_text() or ""
        if value.strip():
            lines.append(value.strip())
    text = "\n".join(lines)
    if len(text) < 60:
        raise ValueError(
            "Este PDF nao possui texto suficiente. Envie um print PNG/JPG da vaga."
        )
    return text


def extract_job_file_text(content: bytes, filename: str) -> dict[str, Any]:
    if not filename:
        raise ValueError("Informe o nome do arquivo.")
    if len(content) > MAX_JOB_FILE_BYTES:
        raise ValueError("O arquivo excede o limite de 10 MB.")
    if not content:
        raise ValueError("O arquivo enviado esta vazio.")

    suffix = Path(filename).suffix.casefold()
    if suffix not in SUPPORTED_JOB_FILES:
        raise ValueError("Envie um arquivo PNG, JPG, JPEG, WEBP ou PDF.")

    if suffix == ".pdf":
        text = _pdf_text(content)
        method = "pdf_text"
    else:
        text = _ocr_text(content, suffix)
        method = "local_ocr"

    non_empty_lines = [line for line in text.splitlines() if line.strip()]
    if (
        method == "local_ocr"
        and (len(text.strip()) < MIN_OCR_CHARS or len(non_empty_lines) < MIN_OCR_LINES)
    ):
        raise ValueError(
            "O print esta distante demais para uma analise confiavel. "
            "Amplie a pagina e envie um print que mostre o anuncio em tamanho maior."
        )
    if len(text.strip()) < 60:
        raise ValueError(
            "Pouco texto foi reconhecido. Envie um print mais nitido e completo."
        )
    return {
        "text": text.strip(),
        "method": method,
        "filename": Path(filename).name[:240],
        "characters": len(text.strip()),
    }
