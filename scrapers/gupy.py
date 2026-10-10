"""Collector for Gupy's public jobs endpoint."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, parse_datetime, stable_external_id


SOURCE = "gupy"
PUBLIC_ENDPOINT = "https://portal.gupy.io/api/job"


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "jobs", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


async def collect(
    query: str = "",
    *,
    limit: int = 25,
    client: SafeHttpClient | None = None,
) -> list[VagaPadronizada]:
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        params = {"limit": min(max(limit, 1), 100), "offset": 0}
        if query.strip():
            params["name"] = quote_plus(query.strip())
        payload = await http.get_json(PUBLIC_ENDPOINT, params=params)
        jobs: list[VagaPadronizada] = []
        query_lower = query.casefold().strip()
        for item in _items(payload):
            title = clean_text(item.get("name") or item.get("title"))
            if not title:
                continue
            company = clean_text(item.get("companyName") or item.get("company")) or "Não informado"
            searchable = f"{title} {company} {clean_text(item.get('description'))}".casefold()
            if query_lower and query_lower not in searchable:
                continue
            job_url = clean_text(item.get("jobUrl") or item.get("url"))
            if not job_url:
                slug = clean_text(item.get("id") or item.get("jobId"))
                job_url = f"https://portal.gupy.io/job/{slug}" if slug else PUBLIC_ENDPOINT
            jobs.append(
                VagaPadronizada(
                    id_externo=stable_external_id(SOURCE, item.get("id") or job_url),
                    origem=SOURCE,
                    titulo=title,
                    empresa=company,
                    localidade=clean_text(item.get("city") or item.get("state") or item.get("location")) or "Não informado",
                    tipo_modalidade=item.get("workplaceType") or item.get("workplace") or item.get("type"),
                    url_candidatura=job_url,
                    url_origem=PUBLIC_ENDPOINT,
                    descricao=clean_text(item.get("description")),
                    data_publicacao=parse_datetime(item.get("publishedDate") or item.get("createdAt")),
                    metadados={"raw_source": SOURCE},
                )
            )
            if len(jobs) >= limit:
                break
        return jobs
    finally:
        if own_client:
            await http.aclose()

