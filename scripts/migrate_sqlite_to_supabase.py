import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select, text


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if "DATABASE_URL" not in os.environ:
    raise SystemExit("DATABASE_URL nao esta configurada neste terminal.")

from app.database import Base, engine as target_engine
from app import models as _models  # noqa: F401


base_dir = Path(__file__).resolve().parent.parent
sqlite_path = base_dir / "data" / "agente.db"

if not sqlite_path.is_file():
    raise SystemExit(f"Banco local nao encontrado: {sqlite_path}")
if target_engine.dialect.name != "postgresql":
    raise SystemExit("Migracao cancelada: DATABASE_URL nao aponta para PostgreSQL.")

source_engine = create_engine(f"sqlite:///{sqlite_path}")
source_table_names = set(inspect(source_engine).get_table_names())
tables = [
    table
    for table in Base.metadata.sorted_tables
    if table.name in source_table_names
]
if not tables:
    raise SystemExit(
        "Migracao cancelada: nenhuma tabela do modelo foi encontrada no SQLite."
    )

DIRECT_OWNER_TABLES = {
    "candidates",
    "jobs",
    "email_integrations",
    "processed_email_messages",
    "queue_items",
}

Base.metadata.create_all(target_engine)

with target_engine.connect() as target:
    user_ids = [
        str(row.id)
        for row in target.execute(text("SELECT id FROM auth.users ORDER BY created_at"))
    ]
    occupied = {
        table.name: target.execute(
            select(func.count()).select_from(table)
        ).scalar_one()
        for table in tables
    }

if len(user_ids) != 1:
    raise SystemExit(
        "Migracao cancelada: era esperado exatamente 1 usuario no Supabase Auth, "
        f"mas foram encontrados {len(user_ids)}."
    )
if any(occupied.values()):
    raise SystemExit(
        "Migracao cancelada: o Supabase ja contem registros: "
        + str(occupied)
    )

owner_id = user_ids[0]
copied = {}

with source_engine.connect() as source:
    with target_engine.begin() as target:
        for table in tables:
            rows = [
                dict(row._mapping)
                for row in source.execute(select(table))
            ]

            if table.name in DIRECT_OWNER_TABLES:
                for row in rows:
                    row["owner_id"] = owner_id

            if rows:
                target.execute(table.insert(), rows)

            copied[table.name] = len(rows)

        for table in tables:
            if "id" not in table.c:
                continue
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

print("Migracao concluida.")
print("Todos os registros com propriedade foram vinculados ao unico usuario Auth.")
print("Registros copiados:")
for name, total in copied.items():
    print(f"- {name}: {total}")
