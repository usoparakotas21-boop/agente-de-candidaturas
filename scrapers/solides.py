"""Collector for public job pages exposed by Sólides."""

from __future__ import annotations

import json
import re
import logging
from urllib.parse import quote

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, fetch_via_scraperapi, matches_search_query, parse_datetime, stable_external_id


SOURCE = "solides"
PUBLIC_ENDPOINT = "https://vagas.solides.com.br/api/vacancies"
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
    normalized = re.sub(r"\s+", " ", query).strip()
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        params = {"page": 1, "take": min(max(limit, 1), 50), "title": normalized}
        if location.strip():
            params["locations"] = location.strip()
        requested_url = f"{PUBLIC_ENDPOINT}?page=1&take={params['take']}&title={quote(normalized)}"
        if location.strip():
            requested_url += f"&locations={quote(location.strip())}"
        logger.info("[Sólides] requisitando url=%s", requested_url)
        try:
            payload = json.loads(await fetch_via_scraperapi(requested_url, render_js=True, client=http))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{SOURCE}: resposta da API não é JSON válido: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError(f"{SOURCE}: resposta JSON inesperada; esperado objeto com data[]")
        items = [item for item in payload["data"] if isinstance(item, dict)]
        if not items and location.strip():
            fallback_params = {"page": 1, "take": min(max(limit, 1), 50), "title": normalized}
            logger.info("[Sólides] localização sem resultados; repetindo busca por título")
            fallback_url = f"{PUBLIC_ENDPOINT}?page=1&take={fallback_params['take']}&title={quote(normalized)}"
            try:
                fallback_payload = json.loads(await fetch_via_scraperapi(fallback_url, render_js=True, client=http))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{SOURCE}: resposta de fallback não é JSON válido: {exc}") from exc
            if isinstance(fallback_payload, dict) and isinstance(fallback_payload.get("data"), list):
                items = [item for item in fallback_payload["data"] if isinstance(item, dict)]
        logger.info("[Sólides] url=%s itens_brutos=%d total=%s", requested_url, len(items), payload.get("count"))
        jobs: list[VagaPadronizada] = []
        for item in items:
            title = clean_text(item.get("title"))
            company = clean_text(item.get("companyName")) or "Não informado"
            description = clean_text(item.get("description"))
            state = item.get("state") if isinstance(item.get("state"), dict) else {}
            city = item.get("city") if isinstance(item.get("city"), dict) else {}
            location_text = ", ".join(filter(None, (clean_text(city.get("name")), clean_text(state.get("name"))))) or "Não informado"
            effective_query = f"{query} {location}".strip()
            if not title or not matches_search_query(effective_query, title, company, location_text, description):
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
            raise ValueError(f"{SOURCE}: API retornou itens, mas nenhum correspondeu à consulta {query!r}")
        return jobs
    finally:
        if own_client:
            await http.aclose()

