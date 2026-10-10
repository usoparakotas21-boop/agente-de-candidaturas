"""Offline validation for the continuous email and web vacancy ingestion.

The validator deliberately replaces source collectors with deterministic
fixtures.  It verifies orchestration, deduplication and the non-blocking
email endpoint without contacting Gmail, Microsoft, Apify or job portals.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import BackgroundTasks
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app import main
from app.database import Base
from app.models import JobListing
from schemas import VagaPadronizada
from scrapers import job_collector


def _fixture(source: str):
    async def collect(query: str = "", *, location: str = "", limit: int = 30, client=None):
        return [
            VagaPadronizada(
                id_externo=f"{source}-analista-1",
                origem=source,
                titulo=f"Analista {source}",
                empresa="Empresa de teste",
                localidade=location or "Brasil",
                url_candidatura=f"https://example.test/{source}/1",
            )
        ]

    return collect


async def _run() -> None:
    sources = list(job_collector.COLLECTORS)
    fixtures = {source: _fixture(source) for source in sources}
    with patch.dict(job_collector.COLLECTORS, fixtures, clear=True):
        report = await job_collector.collect_report(
            "Analista",
            location="BA",
            limit_per_source=15,
            concurrency=4,
        )
    assert len(report.vagas) == len(sources), report
    assert report.erros == {}, report.erros
    assert report.brutos_por_fonte == {source: 1 for source in sources}

    # The same source/external pair cannot be duplicated in the canonical
    # listing table.  Use an isolated SQLite database for this check.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        db.add_all(
            [
                JobListing(
                    source_name="gupy",
                    external_id="same-id",
                    title="Analista",
                    company_name="Empresa",
                    location="Bahia",
                    application_url="https://example.test/1",
                ),
                JobListing(
                    source_name="infojobs",
                    external_id="same-id",
                    title="Analista",
                    company_name="Empresa",
                    location="Bahia",
                    application_url="https://example.test/2",
                ),
            ]
        )
        db.commit()
        duplicates = db.execute(
            select(JobListing.source_name, JobListing.external_id)
            .group_by(JobListing.source_name, JobListing.external_id)
            .having(func.count(JobListing.id) > 1)
        ).all()
        assert not duplicates, duplicates
    finally:
        db.close()
        engine.dispose()

    endpoint = main.sincronizar_todas_integracoes_email
    parameters = inspect.signature(endpoint).parameters
    assert "background_tasks" in parameters, "endpoint sem BackgroundTasks"
    tasks = BackgroundTasks()
    started = time.perf_counter()
    payload = await endpoint(tasks, {"id": "phase6-validator"})
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, f"endpoint bloqueou por {elapsed:.3f}s"
    assert payload["status"] == "queued" and payload["background"] is True
    assert len(tasks.tasks) == 1, "sincronização não foi enfileirada"

    print(
        "Phase 6/7 validation: OK "
        f"(fontes={len(report.vagas)}, duplicatas=0, endpoint={elapsed:.3f}s, background=True)"
    )


def main_validation() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    try:
        main_validation()
    except Exception as exc:
        print(f"Phase 6/7 validation: FAILED - {exc}", file=sys.stderr)
        raise
