"""Create and verify a private PostgreSQL backup for the Supabase database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "backups" / "database"


def _required_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(
            f"Ferramenta obrigatoria ausente: {name}. "
            "Instale os PostgreSQL client tools antes de executar o backup."
        )
    return executable


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL nao esta configurada no ambiente.")
    if not value.casefold().startswith(("postgres://", "postgresql://")):
        raise RuntimeError("DATABASE_URL nao possui um esquema PostgreSQL valido.")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_backup(output_dir: Path) -> Path:
    pg_dump = _required_tool("pg_dump")
    pg_restore = _required_tool("pg_restore")
    database_url = _database_url()

    destination = output_dir.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_path = destination / f"supabase-{timestamp}.dump"
    partial_path = destination / f".{final_path.name}.partial"

    child_env = os.environ.copy()
    child_env.pop("DATABASE_URL", None)
    child_env["PGDATABASE"] = database_url

    try:
        subprocess.run(
            [
                pg_dump,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(partial_path),
            ],
            env=child_env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if not partial_path.is_file() or partial_path.stat().st_size == 0:
            raise RuntimeError("O pg_dump nao produziu um arquivo valido.")

        subprocess.run(
            [pg_restore, "--list", str(partial_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        partial_path.replace(final_path)

        checksum = _sha256(final_path)
        final_path.with_suffix(final_path.suffix + ".sha256").write_text(
            f"{checksum}  {final_path.name}\n",
            encoding="utf-8",
        )
        final_path.with_suffix(final_path.suffix + ".json").write_text(
            json.dumps(
                {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "filename": final_path.name,
                    "format": "postgresql-custom",
                    "sha256": checksum,
                    "verified_with_pg_restore": True,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return final_path
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Falha ao criar ou verificar o backup PostgreSQL (codigo {exc.returncode})."
        ) from exc
    finally:
        partial_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Diretorio privado de destino (padrao: backups/database).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Valida DATABASE_URL e ferramentas sem acessar o banco.",
    )
    args = parser.parse_args()

    try:
        _database_url()
        _required_tool("pg_dump")
        _required_tool("pg_restore")
        if args.check:
            print("Backup prerequisites: OK")
            return 0
        path = create_backup(args.output_dir)
        print(f"Backup verificado: {path}")
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
