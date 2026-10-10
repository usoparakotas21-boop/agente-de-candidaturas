"""Collector for public Schema.org postings on Vagas.com.br."""

from __future__ import annotations

import re
import logging
from urllib.parse import quote, urljoin

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, is_generic_search, matches_location, matches_search_query_relaxed, parse_datetime, stable_external_id
from bs4 import BeautifulSoup


SOURCE = "vagas_com"
BASE_URL = "https://www.vagas.com.br/vagas-de-"
logger = logging.getLogger(__name__)


async def collect(
    query: str = "",
    *,
    location: str = "",
    limit: int = 30,
    client: SafeHttpClient | None = None,
) -> list[VagaPadronizada]:
    if not query.strip():
        return []
    slug = re.sub(r"[^a-z0-9]+", "-", query.casefold()).strip("-")
    search_slug = re.sub(r"[^a-z0-9]+", "-", f"{query} {location}".casefold()).strip("-")
    url = f"{BASE_URL}{quote(search_slug)}"
    # A locality slug can be accepted by the browser route while still
    # returning an empty shell from Vagas.com. Keep a query-only fallback so
    # the source can return its real cards; the card locality filter below
    # still enforces the requested city/state when the cards contain it.
    fallback_url = f"{BASE_URL}{quote(slug)}"
    search_urls = [url]
    if location.strip() and fallback_url != url:
        search_urls.append(fallback_url)
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        jobs: list[VagaPadronizada] = []
        seen: set[str] = set()
        raw_total = 0
        for search_url in search_urls:
            page_urls = [search_url, f"{search_url}?pagina=2"] if is_generic_search(query) else [search_url]
            for page_url in page_urls:
                html = await http.get_text(page_url)
                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select("#todasVagas li.vaga")
                raw_total += len(cards)
                logger.info("[Vagas.com] url=%s itens_brutos=%d acumulado=%d", page_url, len(cards), raw_total)
                for card in cards:
                    if len(jobs) >= limit:
                        break
                    link = card.select_one("a.link-detalhes-vaga")
                    title = clean_text(link.get("title") if link else "") or clean_text(link.get_text(" ") if link else "")
                    company = clean_text(card.select_one(".emprVaga").get_text(" ") if card.select_one(".emprVaga") else "Não informado")
                    location_text = clean_text(card.select_one(".vaga-local").get_text(" ") if card.select_one(".vaga-local") else "Não informado")
                    description = clean_text(card.select_one(".detalhes").get_text(" ") if card.select_one(".detalhes") else "")
                    if not title or not matches_search_query_relaxed(query, title, company, description) or not matches_location(location, location_text):
                        continue
                    href = link.get("href") if link else ""
                    job_url = urljoin(page_url, href or page_url)
                    stable_id = stable_external_id(SOURCE, (link.get("data-id-vaga") if link else "") or job_url)
                    if stable_id in seen:
                        continue
                    seen.add(stable_id)
                    date_text = clean_text(card.select_one(".data-publicacao").get_text(" ") if card.select_one(".data-publicacao") else "")
                    jobs.append(VagaPadronizada(id_externo=stable_id, origem=SOURCE, titulo=title, empresa=company or "Não informado", localidade=location_text or "Não informado", url_candidatura=job_url, url_origem=page_url, descricao=description, data_publicacao=parse_datetime(date_text), metadados={"raw_source": SOURCE, "parser": "li.vaga"}))
                    if len(jobs) >= limit:
                        break
                if len(jobs) >= limit and not is_generic_search(query):
                    break
            if len(jobs) >= limit:
                break
        if not jobs:
            logger.info("[%s] nenhum resultado compatível consulta=%r itens_brutos=%d", SOURCE, query, raw_total)
        return jobs
    finally:
        if own_client:
            await http.aclose()

