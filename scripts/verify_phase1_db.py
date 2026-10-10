"""Validate the Fase 1 Supabase schema and RLS contract.

The script is intentionally read-only. It accepts DATABASE_URL (or
SUPABASE_DATABASE_URL), checks the public schema, and exits 0 only when every
required table, column, constraint, index, trigger and RLS guarantee exists.
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


EXPECTED_TABLES = {
    "candidatos",
    "vagas",
    "historico_alertas",
    "candidaturas",
    "integracoes_email",
    "logs_coleta",
    "metricas_sistema",
}

EXPECTED_COLUMNS = {
    "candidates": {"user_id"},
    "candidatos": {
        "id",
        "user_id",
        "nome",
        "email",
        "telefone",
        "cargo_interesse",
        "localidade",
        "modalidades",
        "termos_derivados",
        "plano",
        "created_at",
        "updated_at",
    },
    "vagas": {
        "id",
        "id_externo",
        "origem",
        "titulo",
        "empresa",
        "localidade",
        "tipo_modalidade",
        "tipo_contrato",
        "url_candidatura",
        "data_publicacao",
        "tags",
        "raw_data",
        "created_at",
        "updated_at",
    },
    "historico_alertas": {
        "id",
        "candidato_id",
        "vaga_id",
        "status",
        "enviado_em",
        "notas",
        "created_at",
        "updated_at",
    },
    "candidaturas": {
        "id",
        "candidato_id",
        "vaga_id",
        "status",
        "enviado_em",
        "notas",
        "created_at",
        "updated_at",
    },
    "integracoes_email": {
        "id",
        "user_id",
        "provedor",
        "email_conectado",
        "access_token",
        "refresh_token",
        "token_expires_at",
        "status",
        "ultima_sincronizacao",
        "created_at",
        "updated_at",
    },
    "logs_coleta": {
        "id",
        "fonte",
        "status",
        "total_bruto",
        "total_salvo",
        "erro_detalhe",
        "executado_em",
        "updated_at",
    },
    "metricas_sistema": {
        "id",
        "fonte",
        "status",
        "total_bruto",
        "total_salvo",
        "erro_detalhe",
        "executado_em",
        "updated_at",
    },
}

EXPECTED_POLICIES = {
    "candidatos_owner",
    "candidates_owner_v2",
    "vagas_authenticated_read",
    "vagas_service_role_manage",
    "vagas_admin_insert",
    "vagas_admin_update",
    "vagas_admin_delete",
    "historico_alertas_owner",
    "candidaturas_owner",
    "integracoes_email_owner",
    "email_integrations_owner_v2",
    "logs_coleta_admin_read",
    "metricas_sistema_admin_read",
}


def _dsn_and_ssl(raw_url: str) -> tuple[str, bool]:
    """Convert libpq's sslmode query into asyncpg-compatible arguments."""

    parsed = urlsplit(raw_url.strip())
    query = []
    sslmode = "require" if parsed.scheme.startswith("postgres") else "disable"
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.casefold() == "sslmode":
            sslmode = value.casefold() or sslmode
            continue
        if key.casefold() == "channel_binding":
            continue
        query.append((key, value))
    clean = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    return clean, sslmode not in {"disable", "allow"}


async def _run() -> int:
    try:
        import asyncpg
    except ImportError as exc:  # pragma: no cover - depends on deployment image
        print(f"[FAIL] asyncpg não está instalado: {exc}")
        return 2

    raw_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DATABASE_URL")
    if not raw_url:
        print("[FAIL] Defina DATABASE_URL ou SUPABASE_DATABASE_URL para validar o banco.")
        return 2

    dsn, use_ssl = _dsn_and_ssl(raw_url)
    try:
        conn = await asyncpg.connect(dsn=dsn, ssl=use_ssl, timeout=15)
    except Exception as exc:  # pragma: no cover - depends on network/credentials
        print(f"[FAIL] Não foi possível conectar ao PostgreSQL: {type(exc).__name__}: {exc}")
        return 2

    failures: list[str] = []
    try:
        table_rows = await conn.fetch(
            """
            SELECT tablename, rowsecurity
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
        tables = {row["tablename"] for row in table_rows}
        missing_tables = sorted(EXPECTED_TABLES - tables)
        if missing_tables:
            failures.append(f"tabelas ausentes: {', '.join(missing_tables)}")

        not_rls = sorted(row["tablename"] for row in table_rows if not row["rowsecurity"])
        if not_rls:
            failures.append(f"RLS desativado em: {', '.join(not_rls)}")

        column_rows = await conn.fetch(
            """
            SELECT table_name, column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            """
        )
        columns: dict[str, set[str]] = {}
        types: dict[tuple[str, str], tuple[str, str]] = {}
        for row in column_rows:
            columns.setdefault(row["table_name"], set()).add(row["column_name"])
            types[(row["table_name"], row["column_name"])] = (row["data_type"], row["udt_name"])
        for table, required in EXPECTED_COLUMNS.items():
            missing = sorted(required - columns.get(table, set()))
            if missing:
                failures.append(f"{table}: colunas ausentes: {', '.join(missing)}")

        if types.get(("vagas", "raw_data")) != ("jsonb", "jsonb"):
            failures.append("vagas.raw_data precisa ser JSONB")
        if types.get(("candidatos", "user_id")) != ("uuid", "uuid"):
            failures.append("candidatos.user_id precisa ser UUID")
        if types.get(("integracoes_email", "user_id")) != ("uuid", "uuid"):
            failures.append("integracoes_email.user_id precisa ser UUID")

        constraints = {
            row["conname"]
            for row in await conn.fetch(
                "SELECT conname FROM pg_constraint WHERE connamespace = 'public'::regnamespace"
            )
        }
        for name in ("uq_vaga_origem_externo", "uq_candidato_vaga"):
            if name not in constraints:
                failures.append(f"constraint ausente: {name}")

        index_names = {
            row["indexname"]
            for row in await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
            )
        }
        for name in (
            "idx_vagas_titulo_portugues",
            "idx_vagas_origem_updated_at",
            "idx_vagas_localidade",
            "idx_candidatos_user_id",
            "idx_integracoes_email_user_id",
            "idx_candidaturas_vaga_id",
        ):
            if name not in index_names:
                failures.append(f"índice ausente: {name}")

        policy_names = {
            row["policyname"]
            for row in await conn.fetch(
                "SELECT policyname FROM pg_policies WHERE schemaname = 'public'"
            )
        }
        missing_policies = sorted(EXPECTED_POLICIES - policy_names)
        if missing_policies:
            failures.append(f"políticas ausentes: {', '.join(missing_policies)}")

        trigger_count = await conn.fetchval(
            """
            SELECT count(*)
            FROM information_schema.triggers
            WHERE trigger_schema = 'public'
              AND trigger_name = 'trigger_set_updated_at'
            """
        )
        updated_tables = await conn.fetchval(
            """
            SELECT count(DISTINCT table_name)
            FROM information_schema.columns
            WHERE table_schema = 'public' AND column_name = 'updated_at'
            """
        )
        if int(trigger_count or 0) < int(updated_tables or 0):
            failures.append(
                f"triggers updated_at incompletos: {trigger_count}/{updated_tables}"
            )
    finally:
        await conn.close()

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1

    print(
        "[OK] Fase 1 validada: "
        f"{len(EXPECTED_TABLES)} tabelas essenciais, "
        "RLS em todas as tabelas públicas, políticas, índices e triggers presentes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
