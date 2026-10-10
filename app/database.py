import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
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
