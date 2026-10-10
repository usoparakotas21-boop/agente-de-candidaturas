"""Concurrent orchestrator for the isolated public job collectors."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from schemas import VagaPadronizada
from utils.anti_ban import AntiBanPolicy
from utils.http_client import SafeHttpClient

from . import catho, gupy, infojobs, linkedin, remoteok, solides, vagas_com, weworkremotely


logger = logging.getLogger(__name__)

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
    brutos_por_fonte: dict[str, int] = field(default_factory=dict)


async def collect_report(
    query: str = "",
    *,
    location: str = "",
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
                    source_query = f"{query} {location}".strip() if source in {"remoteok", "weworkremotely"} else query
                    jobs = await COLLECTORS[source](
                        source_query,
                        location=location,
                        limit=limit_per_source,
                        client=client,
                    )
                    logger.info(
                        "[JobCollector] fonte=%s consulta=%r resultados_filtrados=%d limite=%d",
                        source,
                        query,
                        len(jobs or []),
                        limit_per_source,
                    )
                    return source, jobs, None
                except Exception as exc:  # noqa: BLE001 - one source must not stop the others
                    logger.info(
                        "[JobCollector] fonte=%s consulta=%r resultados_brutos=indisponivel resultados_filtrados=0 status=erro",
                        source,
                        query,
                    )
                    logger.exception(
                        "[JobCollector] fonte=%s consulta=%r falhou: %s: %s",
                        source,
                        query,
                        type(exc).__name__,
                        exc,
                    )
                    return source, None, exc

        results = await asyncio.gather(*(collect_one(source) for source in selected))

    unique: dict[str, VagaPadronizada] = {}
    for source, jobs, error in results:
        report.brutos_por_fonte[source] = len(jobs or [])
        if error is not None:
            report.erros[source] = f"{type(error).__name__}: {error}"
            logger.error(
                "[JobCollector] fonte=%s erro_registrado=%s",
                source,
                report.erros[source],
            )
            continue
        logger.info(
            "[JobCollector] fonte=%s processamento concluido resultados_filtrados=%d",
            source,
            len(jobs or []),
        )
        for job in jobs or []:
            unique.setdefault(job.chave_deduplicacao, job)
    report.vagas = list(unique.values())
    logger.info(
        "[JobCollector] consulta=%r fontes=%d resultados_unicos=%d erros=%d",
        query,
        len(selected),
        len(report.vagas),
        len(report.erros),
    )
    return report


async def collect_all(
    query: str = "",
    *,
    location: str = "",
    sources: list[str] | None = None,
    limit_per_source: int = 25,
    concurrency: int = 4,
    policy: AntiBanPolicy | None = None,
) -> list[VagaPadronizada]:
    """Convenience API returning only the deduplicated vacancy list."""

    report = await collect_report(
        query,
        location=location,
        sources=sources,
        limit_per_source=limit_per_source,
        concurrency=concurrency,
        policy=policy,
    )
    return report.vagas

async def coletar_todas_as_fontes(
    termo: str = "",
    *,
    localizacao: str = "",
    limite_por_fonte: int = 25,
    concorrencia: int = 4,
    fontes: list[str] | None = None,
    policy: AntiBanPolicy | None = None,
) -> list[VagaPadronizada]:
    """Portuguese compatibility API used by the scheduler."""

    return await collect_all(
        termo,
        location=localizacao,
        sources=fontes,
        limit_per_source=limite_por_fonte,
        concurrency=concorrencia,
        policy=policy,
    )
