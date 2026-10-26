from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base
from app.models import BillingSubscription, Candidate, utc_now


@pytest.fixture
def db():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    with engine.begin() as connection:
        connection.execute(text("ATTACH DATABASE ':memory:' AS auth"))
        connection.execute(text('CREATE TABLE auth.users (id TEXT PRIMARY KEY, email TEXT, email_confirmed_at TEXT)'))
        connection.execute(text("INSERT INTO auth.users VALUES ('owner-real','person@example.com','2026-01-01'), ('owner-pending','pending@example.com',NULL)"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        yield session
    engine.dispose()


def _candidate(owner, email):
    return Candidate(owner_id=owner, name='Test', email=email, location='', phone='', linkedin='', target_roles='', summary='')


def _subscription(owner, email):
    return BillingSubscription(owner_id=owner, payer_email=email, plan_code='pro', external_reference=f'CORTESIA-{owner}', status='authorized', monthly_amount=0, currency='BRL', access_until=utc_now()+timedelta(days=5))


def test_profile_and_payer_email_cannot_change_another_owners_subscription(db):
    db.add_all([_candidate('owner-real','other@example.com'), _candidate('owner-attacker','person@example.com'),
                _subscription('owner-real','real@example.com'), _subscription('owner-attacker','person@example.com')])
    db.commit()
    result = main._admin_apply_action(db, 'admin@example.com', main.AdminActionRequest(email='person@example.com', action='revoke_access'))
    db.commit()
    rows = {row.owner_id: row for row in db.scalars(select(BillingSubscription))}
    assert rows['owner-real'].status == 'canceled'
    assert rows['owner-attacker'].status == 'authorized'
    assert 'revogados' in result['message']


def test_courtesy_goes_to_confirmed_auth_owner_even_when_profile_email_is_spoofed(db):
    db.add(_candidate('owner-attacker','person@example.com'))
    db.commit()
    main._admin_apply_action(db, 'admin@example.com', main.AdminActionRequest(email='person@example.com', action='grant_courtesy'))
    db.commit()
    subscription = db.scalar(select(BillingSubscription))
    assert subscription.owner_id == 'owner-real'
    assert db.scalar(select(Candidate).where(Candidate.owner_id == 'owner-real')) is not None


@pytest.mark.parametrize('email', ['missing@example.com', 'pending@example.com'])
def test_missing_or_unconfirmed_account_cannot_receive_courtesy(db, email):
    db.add(_candidate('attacker', email))
    db.commit()
    with pytest.raises(HTTPException) as error:
        main._admin_find_target(db, email)
    assert error.value.status_code == 404


def test_ambiguous_auth_email_fails_closed(db):
    db.execute(text("INSERT INTO auth.users VALUES ('owner-second','person@example.com','2026-01-02')"))
    with pytest.raises(HTTPException) as error:
        main._admin_find_target(db, 'person@example.com')
    assert error.value.status_code == 409


def test_unavailable_auth_database_fails_closed(db):
    db.execute(text('DROP TABLE auth.users'))
    with pytest.raises(HTTPException) as error:
        main._admin_find_target(db, 'person@example.com')
    assert error.value.status_code == 503


def test_user_cannot_access_subscription_or_ebook_through_payer_email(db):
    db.add(_subscription('owner-real', 'person@example.com'))
    db.commit()
    sessions = sessionmaker(bind=db.get_bind())
    attacker = {'id': 'owner-attacker', 'email': 'person@example.com'}
    with patch.object(main, 'SessionLocal', sessions):
        data = main.get_current_subscription(attacker)
        assert data['active'] is False
        with pytest.raises(HTTPException) as error:
            main.download_pro_ebook(attacker)
        assert error.value.status_code == 403
