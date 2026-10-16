"""Real PostgreSQL regression; requires an empty disposable LOCAL audit database."""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.rls_security import FINANCIAL_TABLES, protect_financial_tables


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("command", ["INSERT", "UPDATE", "DELETE", "TRUNCATE"])
def test_financial_writes_are_server_only(role, command):
    url = os.getenv("AUDIT_POSTGRES_URL")
    if not url:
        pytest.skip("Set AUDIT_POSTGRES_URL to an empty local audit database")
    parsed = make_url(url)
    assert parsed.host in {"localhost", "127.0.0.1", "::1"}
    assert parsed.database.startswith("audit_")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                assert connection.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public'")) == 0
                for client_role in ("anon", "authenticated"):
                    connection.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{client_role}') THEN CREATE ROLE {client_role}; END IF; END $$"))
                for table in FINANCIAL_TABLES:
                    connection.execute(text(f'CREATE TABLE public."{table}" (owner_id text, status text)'))
                    connection.execute(text(f'INSERT INTO public."{table}" VALUES (\'owner-a\', \'pending\'), (\'owner-b\', \'paid\')'))
                    connection.execute(text(f'GRANT ALL ON public."{table}" TO anon, authenticated'))
                    connection.execute(text(f'CREATE POLICY owner_all ON public."{table}" FOR ALL TO authenticated USING (owner_id = \'owner-a\') WITH CHECK (owner_id = \'owner-a\')'))
                protect_financial_tables(connection)
                protect_financial_tables(connection)  # Idempotent with existing permissive policies.
                # The privileged backend retains write access.
                connection.execute(text('UPDATE public.billing_subscriptions SET status=\'active\' WHERE owner_id=\'owner-b\''))
                connection.execute(text(f"SET LOCAL ROLE {role}"))
                visible = connection.execute(text("SELECT owner_id FROM public.billing_subscriptions")).scalars().all()
                assert visible == (["owner-a"] if role == "authenticated" else [])
                statements = {
                    "INSERT": "INSERT INTO public.billing_subscriptions VALUES ('owner-a','paid')",
                    "UPDATE": "UPDATE public.billing_subscriptions SET status='paid' WHERE owner_id='owner-a'",
                    "DELETE": "DELETE FROM public.billing_subscriptions WHERE owner_id='owner-a'",
                    "TRUNCATE": "TRUNCATE public.billing_subscriptions",
                }
                with pytest.raises(DBAPIError):
                    connection.execute(text(statements[command]))
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
