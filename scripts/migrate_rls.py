#!/usr/bin/env python
"""Enable idempotent Supabase RLS policies for all user-owned data."""

import logging
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import engine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


DIRECT_OWNER_TABLES = (
    "candidates",
    "jobs",
    "email_integrations",
    "processed_email_messages",
    "queue_items",
)

CHILD_POLICIES = {
    "experiences": """
        EXISTS (
            SELECT 1 FROM candidates
            WHERE candidates.id = experiences.candidate_id
              AND candidates.owner_id = auth.uid()::text
        )
    """,
    "skills": """
        EXISTS (
            SELECT 1 FROM candidates
            WHERE candidates.id = skills.candidate_id
              AND candidates.owner_id = auth.uid()::text
        )
    """,
    "job_analysis": """
        EXISTS (
            SELECT 1 FROM jobs
            WHERE jobs.id = job_analysis.job_id
              AND jobs.owner_id = auth.uid()::text
        )
    """,
    "applications": """
        EXISTS (
            SELECT 1 FROM jobs
            WHERE jobs.id = applications.job_id
              AND jobs.owner_id = auth.uid()::text
        )
    """,
    "application_events": """
        EXISTS (
            SELECT 1
            FROM applications
            JOIN jobs ON jobs.id = applications.job_id
            WHERE applications.id = application_events.application_id
              AND jobs.owner_id = auth.uid()::text
        )
    """,
}


def _create_policy(connection, table: str, expression: str) -> None:
    policy = f"{table}_owner"
    connection.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    connection.execute(text(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"'))
    connection.execute(
        text(
            f'CREATE POLICY "{policy}" ON "{table}" '
            f"FOR ALL TO authenticated "
            f"USING ({expression}) WITH CHECK ({expression})"
        )
    )


def setup_rls() -> None:
    if engine.dialect.name != "postgresql":
        logger.info("RLS ignorado: o banco ativo nao e PostgreSQL.")
        return

    with engine.begin() as connection:
        for table in DIRECT_OWNER_TABLES:
            _create_policy(connection, table, "owner_id = auth.uid()::text")
        for table, expression in CHILD_POLICIES.items():
            _create_policy(connection, table, " ".join(expression.split()))

    logger.info("RLS configurado em %d tabelas.", len(DIRECT_OWNER_TABLES) + len(CHILD_POLICIES))


if __name__ == "__main__":
    setup_rls()
