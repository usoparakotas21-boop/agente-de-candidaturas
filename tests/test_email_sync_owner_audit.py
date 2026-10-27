import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from app import gmail_monitor, main, outlook_monitor
from services import scheduler


def test_combined_sync_only_runs_for_authenticated_owner(monkeypatch):
    gmail = AsyncMock(return_value={"captured": 2})
    outlook = AsyncMock(return_value={"captured": 1})
    all_users = AsyncMock()
    monkeypatch.setattr(gmail_monitor, "sync_owner", gmail)
    monkeypatch.setattr(outlook_monitor, "sync_owner", outlook)
    monkeypatch.setattr(scheduler, "executar_rotina_sincronizacao_emails", all_users)
    monkeypatch.setattr(scheduler, "LAST_EMAIL_SYNC_RESULT", {"secret_other_user_count": 99})
    tasks = BackgroundTasks()

    result = asyncio.run(main.sincronizar_todas_integracoes_email(tasks, {"id": "owner-a"}))
    assert result["background"] is True
    assert result["insercoes_ultima_execucao"] == {}
    asyncio.run(tasks())

    gmail.assert_awaited_once_with("owner-a")
    outlook.assert_awaited_once_with("owner-a")
    all_users.assert_not_awaited()


def test_one_disconnected_provider_does_not_prevent_the_other(monkeypatch):
    gmail = AsyncMock(side_effect=HTTPException(status_code=409, detail="not connected"))
    outlook = AsyncMock(return_value={})
    monkeypatch.setattr(gmail_monitor, "sync_owner", gmail)
    monkeypatch.setattr(outlook_monitor, "sync_owner", outlook)
    asyncio.run(main._sincronizar_integracoes_owner("owner-b"))
    gmail.assert_awaited_once_with("owner-b")
    outlook.assert_awaited_once_with("owner-b")


def test_missing_owner_never_queues_global_sync():
    tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.sincronizar_todas_integracoes_email(tasks, {}))
    assert exc.value.status_code == 409
    assert not tasks.tasks
