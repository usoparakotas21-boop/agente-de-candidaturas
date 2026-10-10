"""Collector for public Infojobs job pages."""

from __future__ import annotations

import re
import logging
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, matches_search_query, parse_datetime, stable_external_id


SOURCE = "infojobs"
BASE_URL = "https://www.infojobs.com.br/vagas-de-emprego-"
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
    search_slug = re.sub(r"[^a-z0-9]+", "+", f"{query} {location}".casefold()).strip("+")
    url = f"{BASE_URL}{quote(search_slug, safe='+')}.aspx"
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        html = await http.get_text(url)
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".js_vacanciesGridFragment .js_rowCard[data-href]")
        if not cards:
            raise ValueError(f"{SOURCE}: página sem cartões [data-href]; seletor pode ter mudado")
        logger.info("[InfoJobs] url=%s itens_brutos=%d", url, len(cards))
        jobs: list[VagaPadronizada] = []
        for card in cards:
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
            effective_query = f"{query} {location}".strip()
            if not title or not matches_search_query(effective_query, title, company, location_text, description):
                continue
            href = card.get("data-href") or (title_node.find_parent("a").get("href") if title_node and title_node.find_parent("a") else "")
            job_url = urljoin(url, href or url)
            job_id = card.get("data-id") or job_url
            modality = "presencial" if "presencial" in text.casefold() else "remoto" if "home office" in text.casefold() or "remoto" in text.casefold() else "hibrido" if "híbrido" in text.casefold() or "hibrido" in text.casefold() else "nao_informado"
            jobs.append(
                VagaPadronizada(
                    id_externo=stable_external_id(SOURCE, job_id),
                    origem=SOURCE,
                    titulo=title,
                    empresa=company or "Não informado",
                    localidade=location_text or "Não informado",
                    tipo_modalidade=modality,
                    url_candidatura=job_url,
                    url_origem=url,
                    descricao=description,
                    metadados={"raw_source": SOURCE, "parser": ".js_rowCard[data-href]"},
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

