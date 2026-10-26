"""Shared financial write boundary for bootstrap and the explicit RLS setup tool."""

from sqlalchemy import text


FINANCIAL_TABLES = (
    "billing_subscriptions",
    "consultation_credits",
    "document_export_purchases",
    "ebook_purchases",
    "linkedin_rebranding_purchases",
)


def protect_oauth_state(connection) -> None:
    connection.execute(text('ALTER TABLE public.oauth_state_nonces ENABLE ROW LEVEL SECURITY'))
    connection.execute(text('REVOKE ALL ON TABLE public.oauth_state_nonces FROM PUBLIC, anon, authenticated'))
    connection.execute(text('DROP POLICY IF EXISTS oauth_state_server_only ON public.oauth_state_nonces'))
    connection.execute(text(
        'CREATE POLICY oauth_state_server_only ON public.oauth_state_nonces AS RESTRICTIVE '
        'FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)'
    ))


def protect_user_identities(connection) -> None:
    """Preserve legacy owner-only rows without permitting a second foreign owner."""
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION public.audit_identity_guard()
        RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog
        AS $$ BEGIN
            IF current_user IN ('anon', 'authenticated') AND (
                (to_jsonb(OLD)->'owner_id') IS DISTINCT FROM (to_jsonb(NEW)->'owner_id') OR
                (to_jsonb(OLD)->'user_id') IS DISTINCT FROM (to_jsonb(NEW)->'user_id')
            ) THEN
                RAISE EXCEPTION 'Ownership changes require the server reconciliation path'
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END $$;
        REVOKE ALL ON FUNCTION public.audit_identity_guard() FROM PUBLIC, anon, authenticated;
    """))
    has_admin = bool(connection.scalar(text("SELECT to_regprocedure('public.is_admin()') IS NOT NULL")))
    for table in ("candidates", "candidatos", "email_integrations"):
        columns = set(connection.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:table "
            "AND column_name IN ('owner_id','user_id')"
        ), {"table": table}).scalars())
        if not columns:
            continue
        checks = [f'("{column}" IS NULL OR "{column}"::text = (SELECT auth.uid())::text)' for column in sorted(columns)]
        present = " OR ".join(f'"{column}" IS NOT NULL' for column in sorted(columns))
        expression = " AND ".join(checks) + f" AND ({present})"
        if has_admin:
            expression = f"((SELECT public.is_admin()) OR ({expression}))"
        connection.execute(text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        connection.execute(text(f'DROP POLICY IF EXISTS audit_identity_consistent ON public."{table}"'))
        connection.execute(text(
            f'CREATE POLICY audit_identity_consistent ON public."{table}" AS RESTRICTIVE '
            f'FOR ALL TO authenticated USING ({expression}) WITH CHECK ({expression})'
        ))
        connection.execute(text(f'DROP TRIGGER IF EXISTS audit_identity_immutable ON public."{table}"'))
        connection.execute(text(
            f'CREATE TRIGGER audit_identity_immutable BEFORE UPDATE ON public."{table}" '
            'FOR EACH ROW EXECUTE FUNCTION public.audit_identity_guard()'
        ))


def protect_client_table_privileges(connection) -> None:
    """RLS does not constrain TRUNCATE; clients need no DDL-like privileges."""
    connection.execute(text("""
        DO $$ DECLARE target record; BEGIN
            FOR target IN
                SELECT tablename FROM pg_tables WHERE schemaname = 'public'
            LOOP
                EXECUTE format(
                    'REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE public.%I FROM PUBLIC, anon, authenticated',
                    target.tablename
                );
                IF current_setting('server_version_num')::int >= 170000 THEN
                    EXECUTE format(
                        'REVOKE MAINTAIN ON TABLE public.%I FROM PUBLIC, anon, authenticated',
                        target.tablename
                    );
                END IF;
            END LOOP;
        END $$;
    """))


def protect_financial_tables(connection) -> None:
    """Keep client reads under existing owner policies; reserve writes for server roles.

    Restrictive policies also block DML if another permissive policy or a
    column-level grant exists. TRUNCATE bypasses RLS and must be revoked.
    Identifiers come exclusively from the fixed tuple above.
    """
    protect_client_table_privileges(connection)
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
