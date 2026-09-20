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
from urllib.parse import parse_qs, unquote, urlsplit


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


def _postgres_error_summary(stderr: str | None) -> str:
    """Return a useful, credential-free summary of a libpq client error."""
    message = (stderr or "").casefold()
    if not message.strip():
        return "o cliente PostgreSQL nao forneceu detalhes adicionais"

    categories = (
        (("could not translate host name", "name or service not known", "temporary failure in name resolution"),
         "falha de DNS ao localizar o servidor"),
        (("password authentication failed", "authentication failed"),
         "falha de autenticacao; confira usuario e senha da conexao"),
        (("connection timed out", "timeout expired", "operation timed out"),
         "timeout de conexao; confira host, porta e conectividade do runner"),
        (("connection refused",),
         "conexao recusada; confira host e porta do PostgreSQL"),
        (("no pg_hba.conf entry", "not allowed to connect"),
         "conexao bloqueada pela politica de rede ou SSL"),
        (("ssl error", "ssl syscall", "certificate verify failed", "ssl required"),
         "falha na negociacao TLS/SSL"),
        (("permission denied", "must be owner", "insufficient privilege"),
         "permissao insuficiente para ler ou restaurar os objetos"),
        (("does not exist",),
         "banco ou objeto PostgreSQL nao encontrado"),
        (("server closed the connection", "connection reset by peer", "unexpected eof"),
         "conexao encerrada pelo servidor durante o dump"),
    )
    for needles, summary in categories:
        if any(needle in message for needle in needles):
            return summary
    return "erro do cliente PostgreSQL; detalhes brutos omitidos por seguranca"


def _connection_environment(database_url: str) -> dict[str, str]:
    """Convert a PostgreSQL URL into libpq variables without exposing it in argv."""
    parsed = urlsplit(database_url)
    if not parsed.hostname or not parsed.path.strip("/"):
        raise RuntimeError("DATABASE_URL precisa informar host e banco PostgreSQL.")
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment["PGHOST"] = parsed.hostname
    environment["PGPORT"] = str(parsed.port or 5432)
    environment["PGUSER"] = unquote(parsed.username or "")
    environment["PGPASSWORD"] = unquote(parsed.password or "")
    environment["PGDATABASE"] = unquote(parsed.path.lstrip("/"))
    environment["PGSSLMODE"] = parse_qs(parsed.query).get("sslmode", ["require"])[0]
    return environment


def restore_backup(backup_path: Path, target_url: str) -> None:
    """Restore a dump into an explicitly supplied isolated PostgreSQL database."""
    pg_restore = _required_tool("pg_restore")
    environment = _connection_environment(target_url)
    subprocess.run(
        [
            pg_restore,
            "--clean",
            "--if-exists",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            environment["PGDATABASE"],
            str(backup_path),
        ],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def create_backup(output_dir: Path, restore_to: str | None = None) -> Path:
    pg_dump = _required_tool("pg_dump")
    pg_restore = _required_tool("pg_restore")
    database_url = _database_url()

    destination = output_dir.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_path = destination / f"supabase-{timestamp}.dump"
    partial_path = destination / f".{final_path.name}.partial"

    child_env = _connection_environment(database_url)

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

        if restore_to:
            restore_backup(final_path, restore_to)

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
        command = exc.cmd[0] if isinstance(exc.cmd, (list, tuple)) and exc.cmd else exc.cmd
        tool = Path(str(command)).name if command else "cliente PostgreSQL"
        raise RuntimeError(
            f"Falha ao executar {tool} (codigo {exc.returncode}): "
            f"{_postgres_error_summary(exc.stderr)}."
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
    parser.add_argument(
        "--restore-to",
        default="",
        help=(
            "URL PostgreSQL de um banco descartável para restauração de teste. "
            "Nunca informe a URL do banco de produção."
        ),
    )
    args = parser.parse_args()

    try:
        _database_url()
        _required_tool("pg_dump")
        _required_tool("pg_restore")
        if args.check:
            print("Backup prerequisites: OK")
            return 0
        path = create_backup(args.output_dir, restore_to=args.restore_to.strip() or None)
        print(f"Backup verificado: {path}")
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
