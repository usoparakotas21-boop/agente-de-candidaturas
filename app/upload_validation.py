"""Central validation for user supplied document and image uploads."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


IMAGE_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def validate_magic_bytes(content: bytes, filename: str, *, allowed: set[str]) -> str:
    """Return the normalized suffix only when bytes match the extension."""
    suffix = Path(filename or "").suffix.casefold()
    if suffix not in allowed:
        raise ValueError("Formato de arquivo nao permitido.")
    if not content:
        raise ValueError("O arquivo enviado esta vazio.")
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("O conteudo do arquivo nao corresponde ao formato informado.")
    if suffix == ".docx":
        if not content.startswith(b"PK"):
            raise ValueError("O conteudo do arquivo nao corresponde ao formato informado.")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("O arquivo nao possui uma estrutura DOCX valida.")
        except zipfile.BadZipFile as exc:
            raise ValueError("O arquivo enviado nao e um DOCX valido.") from exc
    if suffix == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("O conteudo do arquivo nao corresponde ao formato informado.")
    if suffix in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise ValueError("O conteudo do arquivo nao corresponde ao formato informado.")
    if suffix == ".webp" and not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
        raise ValueError("O conteudo do arquivo nao corresponde ao formato informado.")
    return suffix


def validate_image_upload(content: bytes, filename: str, *, max_bytes: int) -> str:
    suffix = validate_magic_bytes(content, filename, allowed=set(IMAGE_CONTENT_TYPES))
    if len(content) > max_bytes:
        raise ValueError("A imagem excede o limite permitido.")
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 30_000_000
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("A imagem esta corrompida ou excede o limite seguro.") from exc
    return IMAGE_CONTENT_TYPES[suffix]
