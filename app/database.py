import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

LOCAL_DATABASE_URL = f"sqlite:///{DATA_DIR / 'agente.db'}"


def _normalize_database_url(value: str) -> str:
    database_url = value.strip()
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg2://",
            1,
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1,
        )
    elif database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace(
            "postgresql+asyncpg://",
            "postgresql+psycopg2://",
            1,
        )
    if not database_url.startswith("sqlite") and "sslmode=" not in database_url.casefold():
        database_url += "&sslmode=require" if "?" in database_url else "?sslmode=require"
    return database_url


def _normalize_async_database_url(value: str) -> str:
    """Normalize a Supabase DATABASE_URL for SQLAlchemy's asyncpg dialect.

    Supabase commonly supplies ``postgresql://...?...sslmode=require``.
    asyncpg expects the SQLAlchemy ``postgresql+asyncpg`` driver and receives
    ``ssl=require`` instead of psycopg's ``sslmode`` option.  Pooler flags and
    other libpq-only options are removed so they are not passed as unknown
    asyncpg connection arguments.
    """
    database_url = value.strip()
    if not database_url or database_url.startswith("sqlite"):
        return ""
    parsed = urlsplit(database_url)
    scheme = parsed.scheme.casefold()
    if scheme in {"postgres", "postgresql", "postgresql+psycopg2"}:
        scheme = "postgresql+asyncpg"
    elif scheme != "postgresql+asyncpg":
        return database_url

    allowed = {
        "ssl",
        "timeout",
        "command_timeout",
        "statement_cache_size",
        "max_cached_statement_lifetime",
        "max_cacheable_statement_size",
        "direct_tls",
    }
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.casefold()
        if key_lower == "sslmode":
            if value.casefold() in {"require", "verify-ca", "verify-full"}:
                query.append(("ssl", "require"))
            continue
        if key_lower in allowed:
            query.append((key_lower, value))
    if not any(key == "ssl" for key, _ in query):
        query.append(("ssl", "require"))
    return urlunsplit((scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL", LOCAL_DATABASE_URL))
ASYNC_DATABASE_URL = _normalize_async_database_url(os.getenv("DATABASE_URL", ""))

engine_options = {"pool_pre_ping": True}

if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
else:
    engine_options.update(
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
    )

engine = create_engine(DATABASE_URL, **engine_options)

async_engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None
if ASYNC_DATABASE_URL:
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """Yield an async Supabase session when DATABASE_URL is PostgreSQL."""
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL PostgreSQL não está configurada para asyncpg.")
    async with AsyncSessionLocal() as db:
        yield db


@asynccontextmanager
async def _managed_async_session(session: AsyncSession | None = None) -> AsyncIterator[AsyncSession]:
    """Use a caller-owned session or create a short-lived transactional session."""
    if session is not None:
        yield session
        return
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL PostgreSQL não está configurada para asyncpg.")
    async with AsyncSessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


def _as_mapping(value: Any) -> Mapping[str, Any]:
    """Convert a Pydantic model or mapping into the database field mapping."""
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    raise TypeError("Cada vaga deve ser um mapping ou um modelo com model_dump().")


def _clean_vaga(value: Any) -> dict[str, Any]:
    data = _as_mapping(value)
    required = ("id_externo", "origem", "titulo", "url_candidatura")
    missing = [field for field in required if not str(data.get(field) or "").strip()]
    if missing:
        raise ValueError(f"Vaga sem campos obrigatórios: {', '.join(missing)}")
    tags = data.get("tags") or data.get("palavras_chave") or []
    if isinstance(tags, str):
        tags = [tags]
    return {
        "id_externo": str(data["id_externo"]).strip(),
        "origem": str(data["origem"]).strip(),
        "titulo": str(data["titulo"]).strip(),
        "empresa": str(data.get("empresa") or "Não informado").strip(),
        "localidade": str(data.get("localidade") or "Não informado").strip(),
        "tipo_modalidade": str(data.get("tipo_modalidade") or "Não informado"),
        "tipo_contrato": data.get("tipo_contrato"),
        "url_candidatura": str(data["url_candidatura"]).strip(),
        "data_publicacao": data.get("data_publicacao"),
        "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
    }


async def salvar_vagas_em_lote(
    vagas: list[Any],
    session: AsyncSession | None = None,
) -> int:
    """Insert or update normalized jobs atomically and return the input count."""
    registros = [_clean_vaga(vaga) for vaga in vagas]
    if not registros:
        return 0
    statement = text(
        """
        INSERT INTO vagas (
            id_externo, origem, titulo, empresa, localidade, tipo_modalidade,
            tipo_contrato, url_candidatura, data_publicacao, tags, updated_at
        ) VALUES (
            :id_externo, :origem, :titulo, :empresa, :localidade, :tipo_modalidade,
            :tipo_contrato, :url_candidatura, :data_publicacao, :tags, CURRENT_TIMESTAMP
        )
        ON CONFLICT (origem, id_externo) DO UPDATE SET
            titulo = EXCLUDED.titulo,
            empresa = EXCLUDED.empresa,
            localidade = EXCLUDED.localidade,
            tipo_modalidade = EXCLUDED.tipo_modalidade,
            tipo_contrato = EXCLUDED.tipo_contrato,
            url_candidatura = EXCLUDED.url_candidatura,
            data_publicacao = EXCLUDED.data_publicacao,
            tags = EXCLUDED.tags,
            updated_at = CURRENT_TIMESTAMP
        """
    )
    async with _managed_async_session(session) as db:
        await db.execute(statement, registros)
    return len(registros)


async def consultar_vagas(
    termo: str | None = None,
    modalidade: str | None = None,
    limite: int = 50,
    offset: int = 0,
    session: AsyncSession | None = None,
    origem: str | None = None,
) -> list[dict[str, Any]]:
    """Search normalized jobs with text, modality and source filters."""
    limite = max(1, min(int(limite), 200))
    offset = max(0, int(offset))
    conditions = ["1 = 1"]
    params: dict[str, Any] = {"limite": limite, "offset": offset}
    if termo and termo.strip():
        conditions.append(
            "("
            "titulo ILIKE :termo OR empresa ILIKE :termo OR localidade ILIKE :termo "
            "OR COALESCE(array_to_string(tags, ' '), '') ILIKE :termo"
            ")"
        )
        params["termo"] = f"%{termo.strip()}%"
    if modalidade and modalidade.strip():
        conditions.append("tipo_modalidade = :modalidade")
        params["modalidade"] = modalidade.strip()
    if origem and origem.strip():
        conditions.append("origem = :origem")
        params["origem"] = origem.strip()
    statement = text(
        f"""
        SELECT id, id_externo, origem, titulo, empresa, localidade,
               tipo_modalidade, tipo_contrato, url_candidatura,
               data_publicacao, tags, created_at, updated_at,
               COUNT(*) OVER() AS total_count
        FROM vagas
        WHERE {' AND '.join(conditions)}
        ORDER BY updated_at DESC, id DESC
        LIMIT :limite OFFSET :offset
        """
    )
    async with _managed_async_session(session) as db:
        result = await db.execute(statement, params)
        return [dict(row) for row in result.mappings().all()]


async def cadastrar_candidato(
    nome: str,
    email: str,
    cargo_interesse: str,
    telefone: str | None = None,
    modalidade_preferida: str = "Todas",
    session: AsyncSession | None = None,
) -> dict[str, Any]:
    """Create or update a candidate identified by a normalized unique email."""
    nome = nome.strip()
    email = email.strip().casefold()
    cargo_interesse = cargo_interesse.strip()
    if not nome or not email or not cargo_interesse:
        raise ValueError("nome, email e cargo_interesse são obrigatórios.")
    statement = text(
        """
        INSERT INTO candidatos (nome, email, telefone, cargo_interesse, modalidade_preferida, updated_at)
        VALUES (:nome, :email, :telefone, :cargo_interesse, :modalidade_preferida, CURRENT_TIMESTAMP)
        ON CONFLICT (email) DO UPDATE SET
            nome = EXCLUDED.nome,
            telefone = EXCLUDED.telefone,
            cargo_interesse = EXCLUDED.cargo_interesse,
            modalidade_preferida = EXCLUDED.modalidade_preferida,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id, nome, email, telefone, cargo_interesse, modalidade_preferida, created_at, updated_at
        """
    )
    params = {
        "nome": nome,
        "email": email,
        "telefone": telefone.strip() if telefone else None,
        "cargo_interesse": cargo_interesse,
        "modalidade_preferida": modalidade_preferida.strip() or "Todas",
    }
    async with _managed_async_session(session) as db:
        result = await db.execute(statement, params)
        row = result.mappings().first()
        if row is None:
            raise RuntimeError("Não foi possível cadastrar o candidato.")
        return dict(row)


async def obter_matches_pendentes(
    candidato_id: int | None = None,
    limite: int = 100,
    offset: int = 0,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """Return pending candidate/job matches ready for notification."""
    limite = max(1, min(int(limite), 500))
    offset = max(0, int(offset))
    statement = text(
        """
        SELECT h.id AS alerta_id, h.candidato_id, h.vaga_id, h.tipo_alerta,
               h.status, h.created_at AS alerta_criado_em,
               c.nome AS candidato_nome, c.email AS candidato_email,
               v.titulo, v.empresa, v.localidade, v.tipo_modalidade,
               v.url_candidatura, v.data_publicacao
        FROM historico_alertas h
        JOIN candidatos c ON c.id = h.candidato_id
        JOIN vagas v ON v.id = h.vaga_id
        WHERE h.status = 'pendente'
          AND (:candidato_id IS NULL OR h.candidato_id = :candidato_id)
        ORDER BY h.created_at ASC, h.id ASC
        LIMIT :limite OFFSET :offset
        """
    )
    params = {
        "candidato_id": candidato_id,
        "limite": limite,
        "offset": offset,
    }
    async with _managed_async_session(session) as db:
        result = await db.execute(statement, params)
        return [dict(row) for row in result.mappings().all()]


async def registrar_alerta_enviado(
    candidato_id: int,
    vaga_id: int,
    tipo_alerta: str = "nova_vaga",
    session: AsyncSession | None = None,
) -> dict[str, Any]:
    """Mark a candidate/job alert as sent, upserting its unique pair."""
    statement = text(
        """
        INSERT INTO historico_alertas (
            candidato_id, vaga_id, tipo_alerta, status, enviado_em
        ) VALUES (:candidato_id, :vaga_id, :tipo_alerta, 'enviado', CURRENT_TIMESTAMP)
        ON CONFLICT (candidato_id, vaga_id) DO UPDATE SET
            tipo_alerta = EXCLUDED.tipo_alerta,
            status = 'enviado',
            enviado_em = CURRENT_TIMESTAMP
        RETURNING id, candidato_id, vaga_id, tipo_alerta, status, enviado_em, created_at
        """
    )
    params = {
        "candidato_id": int(candidato_id),
        "vaga_id": int(vaga_id),
        "tipo_alerta": tipo_alerta.strip() or "nova_vaga",
    }
    async with _managed_async_session(session) as db:
        result = await db.execute(statement, params)
        row = result.mappings().first()
        if row is None:
            raise RuntimeError("Não foi possível registrar o alerta enviado.")
        return dict(row)


async def limpar_vagas_expiradas(
    antes_de: datetime | None = None,
    dias_sem_atualizacao: int = 90,
    session: AsyncSession | None = None,
) -> int:
    """Remove vagas antigas e seus alertas; the schema has no expiration column."""
    if antes_de is None:
        antes_de = datetime.now(timezone.utc) - timedelta(days=max(1, int(dias_sem_atualizacao)))
    elif antes_de.tzinfo is None:
        antes_de = antes_de.replace(tzinfo=timezone.utc)
    statement = text("DELETE FROM vagas WHERE updated_at < :antes_de")
    async with _managed_async_session(session) as db:
        result = await db.execute(statement, {"antes_de": antes_de})
        return max(0, int(result.rowcount or 0))
