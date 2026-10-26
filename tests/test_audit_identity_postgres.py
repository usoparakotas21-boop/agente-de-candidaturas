"""Ownership policies are checked in a disposable local PostgreSQL transaction."""
import os
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.rls_security import protect_user_identities
from app.rls_security import protect_oauth_state
from app.models import OAuthStateNonce
from app.database import Base

A = '11111111-1111-1111-1111-111111111111'
B = '22222222-2222-2222-2222-222222222222'


@pytest.fixture
def connection():
    url = os.getenv('AUDIT_POSTGRES_URL')
    if not url:
        pytest.skip('Disposable local audit PostgreSQL required')
    parsed = make_url(url)
    assert parsed.host in {'localhost', '127.0.0.1', '::1'} and parsed.database.startswith('audit_')
    engine = create_engine(url)
    with engine.connect() as db:
        transaction = db.begin()
        try:
            assert db.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public'")) == 0
            db.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF; IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF; END $$"))
            db.execute(text('CREATE SCHEMA IF NOT EXISTS auth'))
            db.execute(text("CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$"))
            db.execute(text('GRANT USAGE ON SCHEMA auth TO authenticated, anon'))
            for table in ('candidates', 'candidatos', 'email_integrations'):
                db.execute(text(f'CREATE TABLE public."{table}" (id integer PRIMARY KEY, owner_id text, user_id uuid, name text)'))
                db.execute(text(f'GRANT SELECT, INSERT, UPDATE ON public."{table}" TO authenticated, anon'))
                db.execute(text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
                db.execute(text(f'CREATE POLICY legacy_owner ON public."{table}" FOR ALL TO authenticated USING (owner_id=auth.uid()::text OR user_id=auth.uid()) WITH CHECK (owner_id=auth.uid()::text OR user_id=auth.uid())'))
                db.execute(text(f"INSERT INTO public.\"{table}\" VALUES (1,:a,NULL,'one'),(2,:a,CAST(:a AS uuid),'two'),(3,:b,NULL,'other'),(4,:a,CAST(:b AS uuid),'conflict'),(5,NULL,CAST(:a AS uuid),'legacy')"), {'a': A, 'b': B})
            protect_user_identities(db)
            protect_user_identities(db)
            yield db
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.mark.parametrize('table', ['candidates','candidatos','email_integrations'])
@pytest.mark.parametrize('actor,visible', [(A,[1,2,5]),(B,[3])])
def test_both_ownership_columns_must_agree(connection, table, actor, visible):
    connection.execute(text("SELECT set_config('request.jwt.claim.sub',:actor,true)"), {'actor': actor})
    connection.execute(text('SET LOCAL ROLE authenticated'))
    assert connection.execute(text(f'SELECT id FROM public."{table}" ORDER BY id')).scalars().all() == visible


@pytest.mark.parametrize('table', ['candidates','candidatos','email_integrations'])
@pytest.mark.parametrize('column,value', [('owner_id',B),('user_id',B),('owner_id',None)])
def test_clients_cannot_reassign_or_null_ownership(connection, table, column, value):
    connection.execute(text("SELECT set_config('request.jwt.claim.sub',:actor,true)"), {'actor': A})
    connection.execute(text('SET LOCAL ROLE authenticated'))
    assert connection.execute(text(f'UPDATE public."{table}" SET name=\'updated\' WHERE id=1')).rowcount == 1
    with pytest.raises(DBAPIError):
        connection.execute(text(f'UPDATE public."{table}" SET "{column}"=:owner WHERE id=1'), {'owner': value})


def test_backend_can_reconcile_identity(connection):
    assert connection.execute(text('UPDATE public.candidates SET owner_id=:owner, user_id=CAST(:owner AS uuid) WHERE id=4'), {'owner': A}).rowcount == 1


@pytest.mark.parametrize('role', ['anon','authenticated'])
@pytest.mark.parametrize('operation', ['SELECT','INSERT','UPDATE','DELETE','TRUNCATE'])
def test_nonce_ledger_is_server_only(connection, role, operation):
    OAuthStateNonce.__table__.create(connection)
    connection.execute(text('GRANT ALL ON public.oauth_state_nonces TO anon, authenticated'))
    connection.execute(text('CREATE POLICY accidental_allow ON public.oauth_state_nonces FOR ALL USING (true) WITH CHECK (true)'))
    protect_oauth_state(connection)
    protect_oauth_state(connection)
    connection.execute(text(f'SET LOCAL ROLE {role}'))
    statements = {
        'SELECT':'SELECT * FROM public.oauth_state_nonces',
        'INSERT':"INSERT INTO public.oauth_state_nonces VALUES ('hash','gmail','owner',now())",
        'UPDATE':"UPDATE public.oauth_state_nonces SET provider='outlook'",
        'DELETE':'DELETE FROM public.oauth_state_nonces',
        'TRUNCATE':'TRUNCATE public.oauth_state_nonces',
    }
    with pytest.raises(DBAPIError):
        connection.execute(text(statements[operation]))


def test_full_rls_setup_is_idempotent_on_disposable_schema(connection, monkeypatch):
    from scripts import migrate_rls
    Base.metadata.create_all(connection)
    connection.execute(text('GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated'))
    class TransactionEngine:
        dialect = connection.dialect
        @contextmanager
        def begin(self):
            yield connection
    monkeypatch.setattr(migrate_rls, 'engine', TransactionEngine())
    # The real schema was created above inside the rollback-only transaction.
    monkeypatch.setattr(Base.metadata, 'create_all', lambda **kw: None)
    migrate_rls.setup_rls()
    migrate_rls.setup_rls()
    assert connection.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.oauth_state_nonces'::regclass"))
    assert not connection.scalar(text("SELECT has_table_privilege('authenticated','public.billing_subscriptions','UPDATE')"))
    connection.execute(text("SELECT set_config('request.jwt.claim.sub',:actor,true)"), {'actor': A})
    connection.execute(text('SET LOCAL ROLE authenticated'))
    assert connection.execute(text('SELECT id FROM public.candidates ORDER BY id')).scalars().all() == [1,2,5]
