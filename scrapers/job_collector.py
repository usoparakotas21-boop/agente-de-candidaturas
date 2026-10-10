"""Concurrent orchestrator for the isolated public job collectors."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from schemas import VagaPadronizada
from utils.anti_ban import AntiBanPolicy
from utils.http_client import SafeHttpClient

from . import catho, gupy, infojobs, linkedin, remoteok, solides, vagas_com, weworkremotely


Collector = Callable[..., Awaitable[list[VagaPadronizada]]]
COLLECTORS: dict[str, Collector] = {
    "gupy": gupy.collect,
    "remoteok": remoteok.collect,
    "weworkremotely": weworkremotely.collect,
    "vagas_com": vagas_com.collect,
    "solides": solides.collect,
    "linkedin": linkedin.collect,
    "catho": catho.collect,
    "infojobs": infojobs.collect,
}


@dataclass(slots=True)
class CollectionReport:
    vagas: list[VagaPadronizada] = field(default_factory=list)
    erros: dict[str, str] = field(default_factory=dict)
    fontes_consultadas: list[str] = field(default_factory=list)


async def collect_report(
    query: str = "",
    *,
    sources: list[str] | None = None,
    limit_per_source: int = 25,
    concurrency: int = 4,
    policy: AntiBanPolicy | None = None,
) -> CollectionReport:
    """Collect from selected sources concurrently and deduplicate the result."""

    selected = sources or list(COLLECTORS)
    unknown = sorted(set(selected) - set(COLLECTORS))
    if unknown:
        raise ValueError(f"Fontes desconhecidas: {', '.join(unknown)}")
    semaphore = asyncio.Semaphore(max(1, concurrency))
    report = CollectionReport(fontes_consultadas=list(selected))

    async with SafeHttpClient(policy=policy) as client:
        async def collect_one(source: str) -> tuple[str, list[VagaPadronizada] | None, Exception | None]:
            async with semaphore:
                try:
                    jobs = await COLLECTORS[source](query, limit=limit_per_source, client=client)
                    return source, jobs, None
                except Exception as exc:  # noqa: BLE001 - one source must not stop the others
                    return source, None, exc

        results = await asyncio.gather(*(collect_one(source) for source in selected))

    unique: dict[str, VagaPadronizada] = {}
    for source, jobs, error in results:
        if error is not None:
            report.erros[source] = f"{type(error).__name__}: {error}"
            continue
        for job in jobs or []:
            unique.setdefault(job.chave_deduplicacao, job)
    report.vagas = list(unique.values())
    return report


async def collect_all(
    query: str = "",
    *,
    sources: list[str] | None = None,
    limit_per_source: int = 25,
    concurrency: int = 4,
    policy: AntiBanPolicy | None = None,
) -> list[VagaPadronizada]:
    """Convenience API returning only the deduplicated vacancy list."""

    report = await collect_report(
        query,
        sources=sources,
        limit_per_source=limit_per_source,
        concurrency=concurrency,
        policy=policy,
    )
    return report.vagas

async def coletar_todas_as_fontes(
    termo: str = "",
    *,
    limite_por_fonte: int = 25,
    concorrencia: int = 4,
    fontes: list[str] | None = None,
    policy: AntiBanPolicy | None = None,
) -> list[VagaPadronizada]:
    """Portuguese compatibility API used by the scheduler."""

    return await collect_all(
        termo,
        sources=fontes,
        limit_per_source=limite_por_fonte,
        concurrency=concorrencia,
        policy=policy,
    )
