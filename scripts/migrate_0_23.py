#!/usr/bin/env python
"""
Migracao para versao 0.23.0 - Adiciona tabela queue_items.
Idempotente: pode ser executado multiplas vezes sem causar erro.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import engine, Base
from app.models import QueueItem
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_queue_table():
    """Cria a tabela queue_items se nao existir."""
    logger.info("Criando tabela queue_items...")
    
    Base.metadata.create_all(
        bind=engine,
        tables=[QueueItem.__table__],
        checkfirst=True
    )
    logger.info("Tabela queue_items criada/verificada com sucesso.")


def create_indexes():
    """Cria indices adicionais se nao existirem."""
    logger.info("Verificando indices...")
    
    with engine.connect() as conn:
        dialect = engine.dialect.name
        
        if dialect == "postgresql":
            conn.execute(text("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_queue_items_owner_decision_status') THEN
                        CREATE INDEX ix_queue_items_owner_decision_status 
                        ON queue_items (owner_id, decision, status);
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_queue_items_owner_captured') THEN
                        CREATE INDEX ix_queue_items_owner_captured 
                        ON queue_items (owner_id, captured_at DESC);
                    END IF;
                END $$;
            """))
            conn.commit()
            logger.info("Indices PostgreSQL verificados.")
            
        elif dialect == "sqlite":
            # Verifica se os indices existem
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name IN ('ix_queue_items_owner_decision_status', 'ix_queue_items_owner_captured')"
            ))
            existing = [row[0] for row in result]
            
            if "ix_queue_items_owner_decision_status" not in existing:
                conn.execute(text(
                    "CREATE INDEX ix_queue_items_owner_decision_status ON queue_items (owner_id, decision, status)"
                ))
                logger.info("Indice owner_decision_status criado no SQLite.")
            
            if "ix_queue_items_owner_captured" not in existing:
                conn.execute(text(
                    "CREATE INDEX ix_queue_items_owner_captured ON queue_items (owner_id, captured_at DESC)"
                ))
                logger.info("Indice owner_captured criado no SQLite.")
            
            conn.commit()
        
        logger.info("Indices verificados.")


def setup_rls():
    """Configura RLS no Supabase (PostgreSQL)."""
    logger.info("Configurando RLS para queue_items...")
    
    with engine.connect() as conn:
        dialect = engine.dialect.name
        
        if dialect != "postgresql":
            logger.info("Nao e PostgreSQL, pulando RLS.")
            return
        
        try:
            conn.execute(text("ALTER TABLE queue_items ENABLE ROW LEVEL SECURITY;"))
            
            conn.execute(text("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'queue_items' AND policyname = 'queue_items_owner') THEN
                        CREATE POLICY queue_items_owner ON queue_items
                            FOR ALL
                            USING (owner_id = auth.uid()::text)
                            WITH CHECK (owner_id = auth.uid()::text);
                    END IF;
                END $$;
            """))
            conn.commit()
            logger.info("RLS configurado para queue_items.")
            
        except Exception as e:
            logger.warning(f"Nao foi possivel configurar RLS: {e}")
            logger.warning("Isso e normal se voce nao estiver usando Supabase/PostgreSQL.")


def main():
    logger.info("=" * 60)
    logger.info("Migracao 0.23.0 - Fila de Decisao")
    logger.info("=" * 60)
    
    try:
        create_queue_table()
        create_indexes()
        setup_rls()
        
        logger.info("=" * 60)
        logger.info("Migracao 0.23.0 concluida com sucesso!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Erro durante a migracao: {e}")
        raise


if __name__ == "__main__":
    main()