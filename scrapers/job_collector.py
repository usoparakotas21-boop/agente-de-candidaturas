"""Concurrent orchestrator for the isolated public job collectors."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from schemas import VagaPadronizada
from utils.anti_ban import AntiBanPolicy
from utils.http_client import SafeHttpClient

from . import catho, gupy, infojobs, linkedin, remoteok, solides, vagas_com, weworkremotely


logger = logging.getLogger(__name__)


def _is_expected_no_result(error: Exception) -> bool:
    """Keep an empty search from being reported as a source outage."""

    message = str(error).casefold()
    markers = (
        "nenhuma vaga correspondeu",
        "nenhum resultado compatível",
        "nenhum jobposting correspondeu",
        "itens brutos=0",
        "cartões encontrados, mas nenhum",
        # Dynamic portals often omit structured data from the anonymous HTML
        # shell. This is a source-level no-result, not a transport failure;
        # keep the exact parser detail in the log without inflating the user
        # alert's failure count.
        "página pública sem __next_data__",
        "resposta sem script json-ld",
    )
    return isinstance(error, ValueError) and any(marker in message for marker in markers)

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

# Keep one slow provider from holding the manual capture request open until
# the Railway/Cloudflare gateway returns an HTML timeout page. LinkedIn runs a
# browser Actor and therefore receives a longer, explicit budget.
SOURCE_TIMEOUTS_SECONDS = {
    "solides": 55.0,
    "linkedin": 95.0,
}

_STATE_ALIASES = {
    "ac": "Acre", "al": "Alagoas", "ap": "Amapá", "am": "Amazonas",
    "ba": "Bahia", "ce": "Ceará", "df": "Distrito Federal", "es": "Espírito Santo",
    "go": "Goiás", "ma": "Maranhão", "mt": "Mato Grosso", "ms": "Mato Grosso do Sul",
    "mg": "Minas Gerais", "pa": "Pará", "pb": "Paraíba", "pr": "Paraná",
    "pe": "Pernambuco", "pi": "Piauí", "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte",
    "rs": "Rio Grande do Sul", "ro": "Rondônia", "rr": "Roraima", "sc": "Santa Catarina",
    "sp": "São Paulo", "se": "Sergipe", "to": "Tocantins",
}


def normalizar_localidade(value: str | None) -> str:
    """Normalize Brazilian state abbreviations before source-specific URLs."""

    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    key = text.casefold().replace(".", "")
    if key in _STATE_ALIASES:
        return _STATE_ALIASES[key]
    # Preserve city names while expanding a trailing state abbreviation.
    match = re.search(r"(?:^|[\s,/-])([a-z]{2})$", key)
    if match and match.group(1) in _STATE_ALIASES:
        start, end = match.span(1)
        return text[:start] + _STATE_ALIASES[match.group(1)] + text[end:]
    return text


def normalizar_termo(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


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
    limit_per_source: int = 30,
    concurrency: int = 4,
    policy: AntiBanPolicy | None = None,
) -> CollectionReport:
    """Collect from selected sources concurrently and deduplicate the result."""

    query = normalizar_termo(query)
    location = normalizar_localidade(location)
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
                    collect_call = COLLECTORS[source](
                        source_query,
                        location=location,
                        limit=limit_per_source,
                        client=client,
                    )
                    timeout = SOURCE_TIMEOUTS_SECONDS.get(source, 45.0)
                    jobs = await asyncio.wait_for(collect_call, timeout=timeout)
                    logger.info(
                        "[JobCollector] fonte=%s consulta=%r resultados_filtrados=%d limite=%d",
                        source,
                        query,
                        len(jobs or []),
                        limit_per_source,
                    )
                    return source, jobs, None
                except Exception as exc:  # noqa: BLE001 - one source must not stop the others
                    if _is_expected_no_result(exc):
                        logger.info(
                            "[JobCollector] fonte=%s consulta=%r sem_resultados status=sem_resultados detalhe=%s",
                            source,
                            query,
                            exc,
                        )
                        return source, [], None
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
    limit_per_source: int = 30,
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
    limite_por_fonte: int = 30,
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
