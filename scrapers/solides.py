"""Collector for public job pages exposed by Sólides."""

from __future__ import annotations

import json
import re
import logging
from urllib.parse import quote

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, fetch_via_scraperapi, is_generic_search, matches_location, matches_search_query_relaxed, parse_datetime, stable_external_id


SOURCE = "solides"
PUBLIC_ENDPOINT = "https://vagas.solides.com.br/api/vacancies"
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
    normalized = re.sub(r"\s+", " ", query).strip()
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        take = min(max(limit, 1), 50)
        page_numbers = (1, 2) if is_generic_search(normalized) else (1,)

        async def fetch_page(page: int, with_location: bool = True) -> tuple[str, dict, list[dict]]:
            requested_url = f"{PUBLIC_ENDPOINT}?page={page}&take={take}&title={quote(normalized)}"
            if with_location and location.strip():
                requested_url += f"&locations={quote(location.strip())}"
            logger.info("[Sólides] requisitando url=%s", requested_url)
            try:
                # The vacancies endpoint is JSON and works directly in most
                # regions. Use ScraperAPI only when the direct request is
                # blocked or the SPA requires rendering, avoiding needless
                # proxy timeouts for normal captures.
                try:
                    body = await http.get_text(requested_url)
                except Exception as direct_exc:  # noqa: BLE001 - proxy is the fallback
                    logger.warning("[Sólides] acesso direto falhou (%s); tentando ScraperAPI", direct_exc)
                    body = await fetch_via_scraperapi(requested_url, render_js=True, client=http)
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{SOURCE}: resposta da API não é JSON válido: {exc}") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError(f"{SOURCE}: resposta JSON inesperada; esperado objeto com data[]")
            items = [item for item in payload["data"] if isinstance(item, dict)]
            logger.info("[Sólides] url=%s itens_brutos=%d total=%s", requested_url, len(items), payload.get("count"))
            return requested_url, payload, items

        items: list[dict] = []
        seen_items: set[str] = set()
        for page in page_numbers:
            requested_url, payload, page_items = await fetch_page(page)
            if not page_items and page == 1 and location.strip():
                logger.info("[Sólides] localização sem resultados; repetindo busca por título")
                requested_url, payload, page_items = await fetch_page(page, with_location=False)
            for item in page_items:
                marker = clean_text(item.get("id") or item.get("slug") or json.dumps(item, sort_keys=True))
                if marker and marker in seen_items:
                    continue
                if marker:
                    seen_items.add(marker)
                items.append(item)
            if len(items) >= take and not is_generic_search(normalized):
                break
        if not items:
            raise ValueError(f"{SOURCE}: API retornou zero itens para a consulta {query!r}")
        jobs: list[VagaPadronizada] = []
        for item in items:
            title = clean_text(item.get("title"))
            company = clean_text(item.get("companyName")) or "Não informado"
            description = clean_text(item.get("description"))
            state = item.get("state") if isinstance(item.get("state"), dict) else {}
            city = item.get("city") if isinstance(item.get("city"), dict) else {}
            location_text = ", ".join(filter(None, (clean_text(city.get("name")), clean_text(state.get("name"))))) or "Não informado"
            if not title or not matches_search_query_relaxed(query, title, company, description) or not matches_location(location, location_text):
                continue
            publishers = item.get("publishers") if isinstance(item.get("publishers"), dict) else {}
            redirect_url = ""
            for publisher in publishers.values():
                if isinstance(publisher, dict) and publisher.get("redirectUrl"):
                    redirect_url = clean_text(publisher["redirectUrl"])
                    break
            job_id = clean_text(item.get("id"))
            job_url = redirect_url or f"https://vagas.solides.com.br/vaga/{job_id}/{clean_text(item.get('slug'))}".rstrip("/")
            tags = [clean_text(skill.get("name")) for skill in item.get("hardSkills", []) if isinstance(skill, dict)]
            jobs.append(
                VagaPadronizada(
                    id_externo=stable_external_id(SOURCE, job_id or job_url),
                    origem=SOURCE,
                    titulo=title,
                    empresa=company,
                    localidade=location_text,
                    tipo_modalidade=item.get("jobType") or ("remoto" if item.get("homeOffice") else "nao_informado"),
                    url_candidatura=job_url,
                    url_origem=PUBLIC_ENDPOINT,
                    descricao=description,
                    palavras_chave=tags,
                    tipo_contrato=clean_text(item.get("recruitmentContractType")) or None,
                    senioridade=clean_text(item.get("seniority")) or None,
                    data_publicacao=parse_datetime(item.get("createdAt")),
                    metadados={"raw_source": SOURCE, "parser": "/api/vacancies"},
                )
            )
            if len(jobs) >= limit:
                break
        if not jobs:
            logger.info("[%s] nenhum resultado compatível consulta=%r itens_brutos=%d", SOURCE, query, len(items))
        return jobs
    finally:
        if own_client:
            await http.aclose()

