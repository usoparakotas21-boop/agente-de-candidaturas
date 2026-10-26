from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from app import gmail_integration as gmail, outlook_integration as outlook
from app.models import OAuthStateNonce
from app.oauth_nonce import consume_nonce


@pytest.fixture(params=["gmail", "outlook"])
def oauth(request, tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'nonces.db'}", connect_args={"check_same_thread": False})
    OAuthStateNonce.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    module = gmail if request.param == "gmail" else outlook
    monkeypatch.setattr(module, "SessionLocal", sessions)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "offline-test-secret")
    monkeypatch.setenv("OUTLOOK_CLIENT_SECRET", "offline-test-secret")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "offline-test-secret")
    create = module._create_state if request.param == "gmail" else module._state
    yield module, create, sessions
    engine.dispose()


def test_state_consumed_once_and_not_stored_in_plaintext(oauth):
    module, create, sessions = oauth
    state = create("owner-a")
    with sessions() as db:
        row = db.scalar(select(OAuthStateNonce))
        assert row and len(row.nonce_hash) == 64 and row.nonce_hash not in state
    module._validate_state(state, "owner-a")
    with pytest.raises(HTTPException) as error:
        module._validate_state(state, "owner-a")
    assert error.value.status_code == 400


def test_wrong_user_and_tamper_do_not_consume_legitimate_state(oauth):
    module, create, _ = oauth
    state = create("owner-a")
    with pytest.raises(HTTPException):
        module._validate_state(state, "owner-b")
    with pytest.raises(HTTPException):
        module._validate_state(state + "x", "owner-a")
    module._validate_state(state, "owner-a")


def test_expired_state_and_nonce_are_rejected(oauth):
    module, create, _ = oauth
    with patch.object(module.time, "time", return_value=1):
        state = create("owner-a")
    with pytest.raises(HTTPException) as error:
        module._validate_state(state, "owner-a")
    assert error.value.status_code == 400


def test_two_workers_only_one_can_consume(oauth):
    module, create, _ = oauth
    state = create("owner-a")
    def attempt(_):
        try:
            module._validate_state(state, "owner-a")
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [200, 400]


def test_replay_rejected_after_new_db_connection(oauth):
    module, create, sessions = oauth
    state = create("owner-a")
    module._validate_state(state, "owner-a")
    sessions.kw["bind"].dispose()
    with pytest.raises(HTTPException):
        module._validate_state(state, "owner-a")


def test_missing_nonce_cannot_be_consumed(oauth):
    _, _, sessions = oauth
    for nonce in (None, "", "short"):
        with pytest.raises(HTTPException):
            consume_nonce(sessions, "gmail", "owner-a", nonce)


def test_database_unavailable_rejects_issue_and_callback(oauth, monkeypatch):
    module, create, _ = oauth
    state = create('owner-a')
    def unavailable():
        raise OperationalError('offline', None, None)
    monkeypatch.setattr(module, 'SessionLocal', unavailable)
    for action in (lambda: create('owner-a'), lambda: module._validate_state(state, 'owner-a')):
        with pytest.raises(HTTPException) as error:
            action()
        assert error.value.status_code == 503
