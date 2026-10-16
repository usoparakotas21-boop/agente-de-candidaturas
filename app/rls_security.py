"""Shared financial write boundary for bootstrap and the explicit RLS setup tool."""

from sqlalchemy import text


FINANCIAL_TABLES = (
    "billing_subscriptions",
    "consultation_credits",
    "document_export_purchases",
    "ebook_purchases",
    "linkedin_rebranding_purchases",
)


def protect_financial_tables(connection) -> None:
    """Keep client reads under existing owner policies; reserve writes for server roles.

    Restrictive policies also block DML if another permissive policy or a
    column-level grant exists. TRUNCATE bypasses RLS and must be revoked.
    Identifiers come exclusively from the fixed tuple above.
    """
    for table in FINANCIAL_TABLES:
        connection.execute(text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        connection.execute(text(
            f'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER '
            f'ON TABLE public."{table}" FROM PUBLIC, anon, authenticated'
        ))
        for command in ("INSERT", "UPDATE", "DELETE"):
            name = f"{table}_server_{command.lower()}"
            connection.execute(text(f'DROP POLICY IF EXISTS "{name}" ON public."{table}"'))
            predicate = (
                "WITH CHECK (false)" if command == "INSERT" else
                "USING (false) WITH CHECK (false)" if command == "UPDATE" else
                "USING (false)"
            )
            connection.execute(text(
                f'CREATE POLICY "{name}" ON public."{table}" AS RESTRICTIVE '
                f'FOR {command} TO anon, authenticated {predicate}'
            ))
