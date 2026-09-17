"""Private storage for generated documents and bounded retention cleanup."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path


def _output_dir() -> Path:
    configured = os.getenv("DOCUMENT_OUTPUT_DIR", "").strip()
    base = Path(configured) if configured else Path(tempfile.gettempdir()) / "agente-candidaturas-documents"
    base = base.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    try:
        base.chmod(0o700)
    except OSError:
        pass
    return base


OUTPUT_DIR = _output_dir()


def cleanup_expired_documents(*, max_age_days: int | None = None) -> int:
    try:
        age_days = int(max_age_days or os.getenv("DOCUMENT_RETENTION_DAYS", "60"))
    except (TypeError, ValueError):
        age_days = 60
    age_days = max(1, min(age_days, 3650))
    cutoff = time.time() - age_days * 86400
    removed = 0
    for path in OUTPUT_DIR.iterdir():
        if not path.is_file() or path.suffix.casefold() not in {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
