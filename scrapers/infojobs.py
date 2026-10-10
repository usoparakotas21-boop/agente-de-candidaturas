"""Collector for public Infojobs job pages."""

from __future__ import annotations

import re
import logging
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, fetch_via_scraperapi, is_generic_search, matches_location, matches_search_query_relaxed, parse_datetime, stable_external_id


SOURCE = "infojobs"
BASE_URL = "https://www.infojobs.com.br/vagas-de-emprego-"
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
    search_slug = re.sub(r"[^a-z0-9]+", "+", f"{query} {location}".casefold()).strip("+")
    url = f"{BASE_URL}{quote(search_slug, safe='+')}.aspx"
    page_urls = [url, f"{url}?page=2"] if is_generic_search(query) else [url]
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        jobs: list[VagaPadronizada] = []
        seen: set[str] = set()
        raw_total = 0
        for page_url in page_urls:
            html = await fetch_via_scraperapi(page_url, client=http)
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(".js_vacanciesGridFragment .js_rowCard[data-href]")
            raw_total += len(cards)
            logger.info("[InfoJobs] url=%s itens_brutos=%d acumulado=%d", page_url, len(cards), raw_total)
            if not cards:
                continue
            for card in cards:
                if len(jobs) >= limit:
                    break
                title_node = card.select_one(".js_vacancyTitle")
                title = clean_text(title_node.get_text(" ") if title_node else "")
                company_links = card.select("a.text-body.text-decoration-none")
                company = clean_text(company_links[0].get_text(" ") if company_links else "Não informado")
                text = clean_text(card.get_text(" "))
                location_text = "Não informado"
                location_node = card.select_one(".js_vacancyLoad .mb-8") or card.select_one(".mb-8")
                if location_node:
                    location_text = clean_text(location_node.get_text(" "))
                description = clean_text(card.select_one(".text-medium:last-child").get_text(" ") if card.select_one(".text-medium:last-child") else text)
                if not title or not matches_search_query_relaxed(query, title, company, description) or not matches_location(location, location_text):
                    continue
                href = card.get("data-href") or (title_node.find_parent("a").get("href") if title_node and title_node.find_parent("a") else "")
                job_url = urljoin(page_url, href or page_url)
                job_id = card.get("data-id") or job_url
                stable_id = stable_external_id(SOURCE, job_id)
                if stable_id in seen:
                    continue
                seen.add(stable_id)
                modality = "presencial" if "presencial" in text.casefold() else "remoto" if "home office" in text.casefold() or "remoto" in text.casefold() else "hibrido" if "híbrido" in text.casefold() or "hibrido" in text.casefold() else "nao_informado"
                jobs.append(VagaPadronizada(id_externo=stable_id, origem=SOURCE, titulo=title, empresa=company or "Não informado", localidade=location_text or "Não informado", tipo_modalidade=modality, url_candidatura=job_url, url_origem=page_url, descricao=description, metadados={"raw_source": SOURCE, "parser": ".js_rowCard[data-href]"}))
                if len(jobs) >= limit:
                    break
            if len(jobs) >= limit and not is_generic_search(query):
                break
        if not jobs:
            logger.info("[%s] nenhum resultado compatível consulta=%r itens_brutos=%d", SOURCE, query, raw_total)
        return jobs
    finally:
        if own_client:
            await http.aclose()

