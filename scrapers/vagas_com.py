"""Collector for public Schema.org postings on Vagas.com.br."""

from __future__ import annotations

import re
import logging
from urllib.parse import quote, urljoin

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, matches_search_query, parse_datetime, stable_external_id
from bs4 import BeautifulSoup


SOURCE = "vagas_com"
BASE_URL = "https://www.vagas.com.br/vagas-de-"
logger = logging.getLogger(__name__)


async def collect(
    query: str = "",
    *,
    location: str = "",
    limit: int = 25,
    client: SafeHttpClient | None = None,
) -> list[VagaPadronizada]:
    if not query.strip():
        return []
    slug = re.sub(r"[^a-z0-9]+", "-", query.casefold()).strip("-")
    search_slug = re.sub(r"[^a-z0-9]+", "-", f"{query} {location}".casefold()).strip("-")
    url = f"{BASE_URL}{quote(search_slug)}"
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        html = await http.get_text(url)
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("#todasVagas li.vaga")
        if not cards:
            raise ValueError(f"{SOURCE}: página sem cartões li.vaga; seletor pode ter mudado")
        logger.info("[Vagas.com] url=%s itens_brutos=%d", url, len(cards))
        jobs: list[VagaPadronizada] = []
        for card in cards:
            link = card.select_one("a.link-detalhes-vaga")
            title = clean_text(link.get("title") if link else "") or clean_text(link.get_text(" ") if link else "")
            company = clean_text(card.select_one(".emprVaga").get_text(" ") if card.select_one(".emprVaga") else "Não informado")
            location_text = clean_text(card.select_one(".vaga-local").get_text(" ") if card.select_one(".vaga-local") else "Não informado")
            description = clean_text(card.select_one(".detalhes").get_text(" ") if card.select_one(".detalhes") else "")
            effective_query = f"{query} {location}".strip()
            if not title or not matches_search_query(effective_query, title, company, location_text, description):
                continue
            href = link.get("href") if link else ""
            job_url = urljoin(url, href or url)
            date_text = clean_text(card.select_one(".data-publicacao").get_text(" ") if card.select_one(".data-publicacao") else "")
            jobs.append(
                VagaPadronizada(
                    id_externo=stable_external_id(SOURCE, (link.get("data-id-vaga") if link else "") or job_url),
                    origem=SOURCE,
                    titulo=title,
                    empresa=company or "Não informado",
                    localidade=location_text or "Não informado",
                    url_candidatura=job_url,
                    url_origem=url,
                    descricao=description,
                    data_publicacao=parse_datetime(date_text),
                    metadados={"raw_source": SOURCE, "parser": "li.vaga"},
                )
            )
            if len(jobs) >= limit:
                break
        if not jobs:
            raise ValueError(f"{SOURCE}: cartões encontrados, mas nenhum correspondeu à consulta {query!r}")
        return jobs
    finally:
        if own_client:
            await http.aclose()

