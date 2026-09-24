import os
from pathlib import Path

from sqlalchemy import create_engine
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
    if not database_url.startswith("sqlite") and "sslmode=" not in database_url.casefold():
        database_url += "&sslmode=require" if "?" in database_url else "?sslmode=require"
    return database_url


DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL", LOCAL_DATABASE_URL))

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
