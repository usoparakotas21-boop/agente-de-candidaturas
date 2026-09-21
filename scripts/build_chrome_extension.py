"""Package the stable Chrome/Edge extension into the download served by the app."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "chrome-extension"
OUTPUT = ROOT / "app" / "static" / "candidatura-certa-autopreenchimento.zip"
FILES = (
    "manifest.json",
    "icons/icon16.png",
    "icons/icon32.png",
    "icons/icon48.png",
    "icons/icon128.png",
    "background.js",
    "automation-policy.js",
    "job-page-policy.js",
    "job-context.js",
    "field-filler.js",
    "copilot-widget.js",
    "pdf-attachment.js",
    "popup.html",
    "popup.js",
    "sidepanel.html",
    "sidepanel.js",
    "README.md",
)


def main() -> None:
    missing = [name for name in FILES if not (EXTENSION_DIR / name).is_file()]
    if missing:
        raise SystemExit("Arquivos ausentes no complemento: " + ", ".join(missing))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name in FILES:
            archive.write(EXTENSION_DIR / name, arcname=name)
    print(f"Extensão empacotada: {OUTPUT.relative_to(ROOT)} ({len(FILES)} arquivos)")


if __name__ == "__main__":
    main()
