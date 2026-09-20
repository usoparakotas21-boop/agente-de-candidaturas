"""Restore one encrypted backup into a named, disposable local Supabase stack.

The plaintext archive is decrypted only in memory and streamed to the local
Supabase PostgreSQL container. Cloud database URLs and arbitrary containers
are intentionally unsupported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from scripts.backup_encryption import decrypt_bytes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY = PROJECT_ROOT / "backups" / "database" / "backup-decryption-key.pem"
PROJECT_ID_RE = re.compile(r"^codex_restore_[a-z0-9_]{1,48}$")


def _validated_project_id(value: str) -> str:
    if not PROJECT_ID_RE.fullmatch(value) or re.search(r"(?:^|_)(?:prod|production)(?:_|$)", value):
        raise ValueError("O project-id deve começar com codex_restore_ e não pode indicar produção.")
    return value


def _validated_archive(path: Path) -> bytes:
    archive = path.expanduser().resolve()
    if not archive.is_file() or not archive.name.endswith(".dump.enc"):
        raise ValueError("Informe um arquivo .dump.enc existente.")
    manifest_path = archive.with_name(f"{archive.name}.json")
    if not manifest_path.is_file():
        raise ValueError("O manifesto do backup não foi encontrado.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("O manifesto do backup está inválido.") from exc
    encrypted = archive.read_bytes()
    if manifest.get("filename") != archive.name:
        raise ValueError("O arquivo não corresponde ao manifesto do backup.")
    if manifest.get("format") != "AES-256-GCM + RSA-OAEP-SHA256":
        raise ValueError("O formato de cifragem do backup não é reconhecido.")
    if manifest.get("sha256") != hashlib.sha256(encrypted).hexdigest():
        raise ValueError("O checksum do backup não confere com o manifesto.")
    return encrypted


def _docker_executable() -> str:
    executable = shutil.which("docker")
    if executable:
        return executable
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe"
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("Docker CLI não encontrado; inicie o Docker Desktop antes da restauração.")


def _decode_process_output(output: bytes) -> str:
    if output and output.count(b"\x00") > len(output) // 8:
        return output.decode("utf-16-le", "replace").rstrip("\x00")
    return output.decode("utf-8", "replace")


def _safe_error_summary(stderr: bytes) -> str:
    """Keep only a sanitized first error line; never echo restore context/data."""
    text = _decode_process_output(stderr)
    candidates = [
        line.strip()
        for line in text.splitlines()
        if any(
            marker in line.casefold()
            for marker in (
                "error:",
                "fatal:",
                "permission denied",
                "could not connect",
                "not found",
                "failed",
                "does not exist",
                "already exists",
                "unsupported",
                "must be",
                "cannot",
                "extension",
                "role",
            )
        )
    ]
    if not candidates:
        safe_words = {
            "already", "archive", "argument", "authentication", "available", "cannot", "closed",
            "command", "connect", "connection", "container", "could", "copy", "data", "database",
            "denied", "directory", "does", "duplicate", "error", "execute", "exist", "exists",
            "extension", "failed", "failure", "fatal", "file", "format", "found", "input", "invalid",
            "key", "missing", "no", "not", "option", "owner", "password", "permission", "process",
            "query", "read", "refused", "relation", "reset", "role", "schema", "server", "signal",
            "socket", "sql", "such", "superuser", "table", "terminated", "timeout", "unsupported",
            "version", "violates", "write",
        }
        tokens = re.findall(r"[a-z]+", text.casefold())
        return "sinais=" + (" ".join(token for token in tokens if token in safe_words) or "nenhum")
    line = re.split(r"\b(?:DETAIL|CONTEXT|STATEMENT):", candidates[0], maxsplit=1, flags=re.IGNORECASE)[0]
    line = re.sub(r"(?i)postgres(?:ql)?://\S+", "<url>", line)
    line = re.sub(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", "<email>", line)
    line = re.sub(r"'(?:[^']|'')*'", "'<valor>'", line)
    line = re.sub(r'"(?:[^"]|"")*"', '"<identificador>"', line)
    line = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<id>", line, flags=re.IGNORECASE)
    line = re.sub(r"\b[A-Za-z0-9_+/=-]{32,}\b", "<token>", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line[:220]


def _run(
    command: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    timeout: int = 1200,
    operation: str = "comando local",
) -> bytes:
    try:
        result = subprocess.run(
            list(command),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Não foi possível concluir a operação com o Docker local.") from exc
    if result.returncode != 0:
        diagnostic = _decode_process_output(result.stderr).casefold()
        safe_summary = _safe_error_summary(result.stderr + result.stdout)
        if "extension" in diagnostic and any(term in diagnostic for term in ("does not exist", "not available")):
            category = "extensão necessária ausente no stack local"
        elif "role" in diagnostic and "does not exist" in diagnostic:
            category = "role PostgreSQL do backup ausente no stack local"
        elif "permission denied" in diagnostic or "must be superuser" in diagnostic:
            category = "permissão insuficiente para restaurar um objeto PostgreSQL"
        elif "already exists" in diagnostic or "does not exist" in diagnostic:
            category = "dependência/objeto do archive incompatível com o stack local"
        elif "duplicate key" in diagnostic or "violates" in diagnostic:
            category = "conflito de dados ou restrição durante a restauração"
        else:
            category = "erro do cliente local Docker/PostgreSQL"
        raise RuntimeError(
            f"A etapa '{operation}' falhou (código {result.returncode}: {category}). "
            f"Resumo sanitizado: {safe_summary or 'sem resumo textual seguro'} "
            f"(saída={len(result.stdout)} bytes, erro={len(result.stderr)} bytes). "
            "O alvo permanece restrito ao stack descartável; "
            "os detalhes do banco foram omitidos para não expor dados."
        )
    return result.stdout


def _database_container(docker: str, project_id: str) -> str:
    expected = f"supabase_db_{project_id}"
    output = _run(
        [docker, "ps", "--filter", f"name=^{expected}$", "--format", "{{.Names}}"],
        timeout=30,
        operation="localizar container de banco",
    )
    names = [line.strip() for line in output.decode("utf-8", "replace").splitlines() if line.strip()]
    if names != [expected]:
        raise RuntimeError(
            f"O container local exato {expected} não está ativo; nenhum outro banco será usado."
        )
    metadata = _run(
        [docker, "inspect", "--format", "{{json .Config.Labels}}|{{.Config.Image}}", expected],
        timeout=30,
        operation="validar identidade do container Supabase",
    ).decode("utf-8", "replace").strip()
    try:
        labels_json, image = metadata.split("|", 1)
        labels = json.loads(labels_json)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Não foi possível validar os metadados do container descartável.") from exc
    if not isinstance(labels, dict) or not isinstance(image, str) or (
        labels.get("com.supabase.cli.project") != project_id
        or labels.get("com.docker.compose.project") != project_id
        or not image.startswith(("public.ecr.aws/supabase/postgres:", "supabase/postgres:"))
    ):
        raise RuntimeError("O container não pertence ao projeto Supabase descartável esperado.")
    return expected


def _verify_local_docker_engine(docker: str) -> None:
    """Reject Docker environment overrides and non-local active contexts."""
    if any(os.environ.get(name, "").strip() for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")):
        raise RuntimeError("Remova overrides DOCKER_HOST/DOCKER_CONTEXT/TLS para usar apenas o engine local.")
    endpoint_output = _run(
        [docker, "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
        timeout=30,
        operation="verificar endpoint do contexto Docker",
    )
    try:
        endpoint = json.loads(endpoint_output.decode("utf-8", "replace").strip())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Não foi possível confirmar o endpoint do Docker local.") from exc
    local_endpoints = {
        "npipe:////./pipe/docker_engine",
        "npipe:////./pipe/dockerDesktopLinuxEngine",
        "npipe:////./pipe/dockerDesktopWindowsEngine",
        "unix:///var/run/docker.sock",
        "unix:///run/docker.sock",
    }
    if not isinstance(endpoint, str) or endpoint not in local_endpoints:
        raise RuntimeError("O contexto Docker não aponta para um endpoint local permitido.")
    _run([docker, "info", "--format", "{{.ServerVersion}}"], timeout=30, operation="verificar engine Docker local")


def _query(
    docker: str,
    container: str,
    database: str,
    sql: str,
    *,
    operation: str = "validar restauração",
) -> str:
    output = _run(
        [
            docker,
            "exec",
            "--user",
            "postgres",
            container,
            "psql",
            "-X",
            "-A",
            "-t",
            "-U",
            "supabase_admin",
            "-d",
            database,
            "-c",
            sql,
        ],
        timeout=120,
        operation=operation,
    )
    return _decode_process_output(output).strip()


def _validate_rls_coverage(docker: str, container: str, database: str, expected_tables: int) -> tuple[int, int]:
    policy_count = _query(
        docker,
        container,
        database,
        "SELECT count(*) FROM pg_policies WHERE schemaname = 'public';",
        operation="validar políticas RLS",
    )
    enabled_tables = _query(
        docker,
        container,
        database,
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relrowsecurity;",
        operation="validar RLS habilitado nas tabelas públicas",
    )
    tables_without_policy = _query(
        docker,
        container,
        database,
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relrowsecurity "
        "AND NOT EXISTS (SELECT 1 FROM pg_policies p WHERE p.schemaname = 'public' "
        "AND p.tablename = c.relname);",
        operation="validar política RLS por tabela pública",
    )
    if not policy_count.isdecimal() or int(policy_count) == 0:
        raise RuntimeError("O backup foi restaurado, mas nenhuma política RLS pública foi encontrada.")
    if not enabled_tables.isdecimal() or int(enabled_tables) != expected_tables:
        raise RuntimeError("RLS não está habilitado em todas as tabelas públicas restauradas.")
    if not tables_without_policy.isdecimal() or int(tables_without_policy) != 0:
        raise RuntimeError("Há tabelas públicas restauradas com RLS sem política de acesso.")
    return int(policy_count), int(enabled_tables)


def restore_archive(
    *,
    archive_path: Path,
    private_key_path: Path,
    project_id: str,
    confirm_disposable: bool,
) -> dict[str, int | str | bool]:
    """Restore an encrypted archive into only the exact local test container."""
    if not confirm_disposable:
        raise ValueError("Confirme o stack local descartável com --confirm-disposable.")
    project_id = _validated_project_id(project_id)
    encrypted = _validated_archive(archive_path)
    plaintext = decrypt_bytes(encrypted, private_key_path)
    if not plaintext.startswith(b"PGDMP"):
        raise ValueError("O conteúdo descriptografado não é um archive custom PostgreSQL.")

    docker = _docker_executable()
    _verify_local_docker_engine(docker)
    container = _database_container(docker, project_id)

    # Parse the archive before making any change to the disposable database.
    _run(
        [docker, "exec", "-i", "--user", "postgres", container, "pg_restore", "--list"],
        input_bytes=plaintext,
        operation="validar formato do archive",
    )
    database = project_id
    _run(
        [docker, "exec", "--user", "postgres", container, "dropdb", "--if-exists", "--username", "supabase_admin", database],
        timeout=120,
        operation="limpar banco de teste anterior",
    )
    _run(
        [docker, "exec", "--user", "postgres", container, "createdb", "--username", "supabase_admin", database],
        timeout=120,
        operation="criar banco de teste isolado",
    )
    _run(
        [
            docker,
            "exec",
            "-i",
            "--user",
            "postgres",
            container,
            "pg_restore",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "--username",
            "supabase_admin",
            "--dbname",
            database,
        ],
        input_bytes=plaintext,
        timeout=1800,
        operation="restaurar archive no PostgreSQL local",
    )
    del plaintext

    table_names = _query(
        docker,
        container,
        database,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;",
        operation="listar tabelas restauradas",
    ).splitlines()
    if not table_names or any(not re.fullmatch(r"[A-Za-z0-9_]+", name) for name in table_names):
        raise RuntimeError("A restauração não apresentou tabelas públicas válidas.")
    row_count = 0
    for table_name in table_names:
        count = _query(
            docker,
            container,
            database,
            f'SELECT count(*) FROM public."{table_name}";',
            operation="contar linhas restauradas",
        )
        if not count.isdecimal():
            raise RuntimeError("Não foi possível validar as contagens agregadas da restauração.")
        row_count += int(count)
    policy_count, rls_enabled_tables = _validate_rls_coverage(docker, container, database, len(table_names))

    return {
        "restored": True,
        "target": "local disposable Supabase",
        "container": container,
        "database": database,
        "public_tables": len(table_names),
        "aggregate_rows": row_count,
        "public_rls_policies": policy_count,
        "public_rls_enabled_tables": rls_enabled_tables,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Caminho para o backup .dump.enc.")
    parser.add_argument(
        "--private-key",
        type=Path,
        default=DEFAULT_KEY,
        help="Chave privada PEM (padrão: backups/database/backup-decryption-key.pem).",
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="Project ID do stack local, com prefixo codex_restore_.",
    )
    parser.add_argument(
        "--confirm-disposable",
        action="store_true",
        help="Confirma que o alvo é o stack local descartável codex_restore_.",
    )
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                restore_archive(
                    archive_path=args.archive,
                    private_key_path=args.private_key,
                    project_id=args.project_id,
                    confirm_disposable=args.confirm_disposable,
                ),
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Restauração interrompida: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
