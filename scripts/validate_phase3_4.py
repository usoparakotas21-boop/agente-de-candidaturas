"""Offline validation for the Phase 3 (LGPD) and Phase 4 (AI/products) API.

The checks use an isolated in-memory SQLite database and patched entitlement/
Supabase calls.  No production account, provider token, email, charge, or
external AI request is created by this script.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import main
from app.database import Base
from app.models import Candidate, Experience, Job


def _request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": ("phase-validator", 50000),
            "server": ("validator", 80),
            "scheme": "https",
        }
    )


def _expect_http_error(call, status: int) -> None:
    try:
        call()
    except HTTPException as exc:
        assert exc.status_code == status, (exc.status_code, exc.detail)
        return
    raise AssertionError(f"expected HTTP {status}")


def main_validation() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    free = {"id": "test-auto-free", "email": "test_auto_free@example.test"}
    pro = {"id": "test-auto-pro", "email": "test_auto_pro@example.test"}

    db = session_factory()
    free_candidate = Candidate(
        owner_id=free["id"], name="Teste Gratuito", location="Salvador, BA",
        email=free["email"], phone="", linkedin="", target_roles="Analista de RH",
        summary="Experiência em pessoas e processos", profile_data="{}", preferences_data="{}",
    )
    pro_candidate = Candidate(
        owner_id=pro["id"], name="Teste Pro", location="Salvador, BA",
        email=pro["email"], phone="", linkedin="", target_roles="Analista de RH",
        summary="Experiência em pessoas e processos", profile_data="{}", preferences_data="{}",
    )
    db.add_all([free_candidate, pro_candidate])
    db.flush()
    db.add(Experience(candidate_id=pro_candidate.id, company="Empresa Teste", role="Analista", start_date="2020", end_date="2024", description="Conduziu processos de RH e indicadores."))
    free_job = Job(
        owner_id=free["id"], source="validator", external_id="phase3-free", company="Empresa A",
        title="Analista de RH", location="Salvador, BA", modality="hibrido", url="https://example.test/a",
        description="Rotinas de recrutamento, seleção e indicadores.",
    )
    pro_job = Job(
        owner_id=pro["id"], source="validator", external_id="phase3-pro", company="Empresa B",
        title="Analista de RH", location="Salvador, BA", modality="hibrido", url="https://example.test/b",
        description="Rotinas de recrutamento, seleção e indicadores.",
    )
    db.add_all([free_job, pro_job])
    db.commit()
    free_job_id, pro_job_id = free_job.id, pro_job.id
    db.close()

    def entitlement(user):
        if user["id"] == pro["id"]:
            return {"plan": "pro", "is_pro": True, "is_consultoria": False, "is_admin": False, "entitled": True}
        return {"plan": "essential", "is_pro": False, "is_consultoria": False, "is_admin": False, "entitled": False}

    with ExitStack() as stack:
        stack.enter_context(patch.object(main, "SessionLocal", session_factory))
        stack.enter_context(patch.object(main, "_get_user_plan_and_entitlement", side_effect=entitlement))
        stack.enter_context(patch.dict(os.environ, {"SUPABASE_URL": "https://supabase.example.test", "SUPABASE_SERVICE_ROLE_KEY": "phase-test"}, clear=False))

        # Free accounts receive an actionable upgrade payload before any AI work.
        _expect_http_error(lambda: asyncio.run(main.ai_adapt_resume(main.AIJobRequest(vaga_id=free_job_id), free)), 402)
        _expect_http_error(lambda: asyncio.run(main.ai_generate_cover_letter(main.AIJobRequest(vaga_id=free_job_id), free)), 402)

        # A paid account can adapt a CV and generate a complete letter.
        adapted = asyncio.run(main.ai_adapt_resume(main.AIJobRequest(vaga_id=pro_job_id), pro))
        assert adapted["status"] == "ok" and adapted["curriculo"]["target"] == "Analista de RH"
        letter = asyncio.run(main.ai_generate_cover_letter(main.AIJobRequest(vaga_id=pro_job_id), pro))
        assert letter["status"] == "ok" and "Empresa B" in letter["carta"]

        # Portability is owner-scoped and delivered as an attachment JSON.
        exported = main.export_user_data_lgpd(pro)
        exported_payload = json.loads(exported.body)
        assert exported_payload["profile"]["email"] == pro["email"]
        assert exported.headers["content-disposition"].startswith("attachment;")
        assert "encrypted_refresh_token" not in json.dumps(exported_payload)

        # The complete book is blocked for free accounts and downloadable for Pro.
        _expect_http_error(lambda: main.download_ebook_api(free), 402)
        ebook = main.download_ebook_api(pro)
        assert ebook.media_type == "application/pdf"

        # Right to erasure removes the account's local records in one purge.
        with patch.object(main, "_delete_supabase_auth_user", new=AsyncMock()):
            deleted = asyncio.run(
                main.delete_user_lgpd(
                    main.AccountDeletionRequest(confirmation=main.ACCOUNT_DELETION_CONFIRMATION),
                    _request("DELETE", "/api/usuario/me"),
                    free,
                )
            )
        assert json.loads(deleted.body)["deleted"] is True
        check = session_factory()
        try:
            assert check.scalar(select(Candidate).where(Candidate.owner_id == free["id"])) is None
            assert check.scalar(select(Job).where(Job.owner_id == free["id"])) is None
            assert check.scalar(select(Candidate).where(Candidate.owner_id == pro["id"])) is not None
        finally:
            check.close()

    engine.dispose()
    print("Phase 3/4 validation: OK (LGPD, AI entitlements, e-book and cleanup)")


if __name__ == "__main__":
    try:
        main_validation()
    except Exception as exc:  # keep CI output actionable and return non-zero
        print(f"Phase 3/4 validation: FAILED - {exc}", file=sys.stderr)
        raise
