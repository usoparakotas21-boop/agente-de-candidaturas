import os
from pathlib import Path

from sqlalchemy import create_engine, func, select, text

from app.database import Base, engine as target_engine
from app.models import (
    Application,
    ApplicationEvent,
    Candidate,
    Experience,
    Job,
    JobAnalysis,
    Skill,
)


if "DATABASE_URL" not in os.environ:
    raise SystemExit("DATABASE_URL não está configurada neste terminal.")

base_dir = Path(__file__).resolve().parent.parent
sqlite_path = base_dir / "data" / "agente.db"

if not sqlite_path.is_file():
    raise SystemExit(f"Banco local não encontrado: {sqlite_path}")

source_engine = create_engine(f"sqlite:///{sqlite_path}")

tables = [
    Candidate.__table__,
    Job.__table__,
    Experience.__table__,
    Skill.__table__,
    JobAnalysis.__table__,
    Application.__table__,
    ApplicationEvent.__table__,
]

Base.metadata.create_all(target_engine)

with target_engine.connect() as target:
    occupied = {
        table.name: target.execute(
            select(func.count()).select_from(table)
        ).scalar_one()
        for table in tables
    }

if any(occupied.values()):
    raise SystemExit(
        "Migração cancelada: o Supabase já contém registros: "
        + str(occupied)
    )

copied = {}

with source_engine.connect() as source:
    with target_engine.begin() as target:
        for table in tables:
            rows = [
                dict(row._mapping)
                for row in source.execute(select(table))
            ]

            if rows:
                target.execute(table.insert(), rows)

            copied[table.name] = len(rows)

        for table in tables:
            target.execute(
                text(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table.name}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table.name}), 1),
                        (SELECT COUNT(*) > 0 FROM {table.name})
                    )
                    """
                )
            )

print("Migração concluída.")
print("Registros copiados:")
for name, total in copied.items():
    print(f"- {name}: {total}")
