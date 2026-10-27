import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app import main


@pytest.mark.parametrize("value,disabled", [(None, False), ("false", False), ("TRUE", True)])
def test_lifespan_only_disables_automatic_jobs_when_explicit(monkeypatch, value, disabled):
    if value is None:
        monkeypatch.delenv("STAGING_DISABLE_BACKGROUND_WORKERS", raising=False)
    else:
        monkeypatch.setenv("STAGING_DISABLE_BACKGROUND_WORKERS", value)
    start = Mock()
    scheduler = Mock(running=False)
    collection = AsyncMock()
    sync = AsyncMock()
    monkeypatch.setattr(main, "startup", Mock())
    monkeypatch.setattr(main, "shutdown", AsyncMock())
    monkeypatch.setattr(main, "iniciar_agendador", start)
    monkeypatch.setattr(main, "vagas_scheduler", scheduler)
    monkeypatch.setattr(main, "executar_rotina_varredura", collection)
    monkeypatch.setattr(main, "executar_rotina_sincronizacao_emails", sync)
    monkeypatch.setattr(main, "async_engine", None)
    monkeypatch.setattr(main, "engine", Mock())
    monkeypatch.setattr(main, "_job_collection_task", None)
    monkeypatch.setattr(main, "_email_sync_task", None)

    async def run():
        async with main.lifespan(main.app):
            await asyncio.sleep(0)

    asyncio.run(run())
    assert start.call_count == (0 if disabled else 1)
    assert collection.await_count == (0 if disabled else 1)
    assert sync.await_count == (0 if disabled else 1)


def test_startup_keeps_schema_but_skips_cleanup_and_workers_in_staging(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGING_DISABLE_BACKGROUND_WORKERS", "true")
    engine = create_engine(f"sqlite:///{tmp_path / 'staging.db'}")
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    names = (
        "cleanup_expired_documents", "_cleanup_generated_document_records",
        "_backfill_legacy_generated_document_pairs", "_cleanup_raw_intake_data",
        "_cleanup_followup_email_outbox", "_cleanup_interview_email_outbox",
        "_cleanup_expiration_email_outbox", "_cleanup_copilot_preparations",
        "_start_purchase_generation_worker", "_start_lifecycle_email_worker",
        "start_monitor", "start_outlook_monitor", "_ensure_app",
    )
    mocks = {name: Mock() for name in names}
    for name, mock in mocks.items():
        monkeypatch.setattr(main, name, mock)

    main.startup()

    assert "candidates" in inspect(engine).get_table_names()
    for mock in mocks.values():
        mock.assert_not_called()
    engine.dispose()
