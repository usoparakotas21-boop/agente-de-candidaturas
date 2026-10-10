"""Collector for Gupy's public jobs endpoint."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import urlencode

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, matches_location, matches_search_query_relaxed, parse_datetime, stable_external_id


SOURCE = "gupy"
PUBLIC_ENDPOINT = "https://portal.gupy.io/vagas"
OFFICIAL_API_ENDPOINT = "https://api.gupy.io/api/v1/jobs"
logger = logging.getLogger(__name__)


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "jobs", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    keys = sorted(payload) if isinstance(payload, dict) else type(payload).__name__
    raise ValueError(f"{SOURCE}: resposta JSON inesperada; chaves={keys}")


def _next_items(html: str) -> list[dict[str, Any]]:
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.S | re.I)
    if not match:
        raise ValueError(f"{SOURCE}: página pública sem __NEXT_DATA__")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{SOURCE}: __NEXT_DATA__ inválido: {exc}") from exc
    page_props = payload.get("props", {}).get("pageProps", {})
    items = page_props.get("initialJobList", {}).get("data")
    if not isinstance(items, list):
        raise ValueError(f"{SOURCE}: __NEXT_DATA__ sem initialJobList.data")
    return [item for item in items if isinstance(item, dict)]


async def collect(
    query: str = "",
    *,
    location: str = "",
    limit: int = 25,
    client: SafeHttpClient | None = None,
) -> list[VagaPadronizada]:
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        token = os.getenv("GUPY_API_TOKEN", "").strip()
        if token:
            params = {"name": query.strip(), "perPage": min(max(limit, 1), 100), "fields": "all"}
            if location.strip():
                params["addressState"] = location.strip()
            requested_url = f"{OFFICIAL_API_ENDPOINT}?{urlencode(params)}"
            logger.info("[Gupy] requisitando url=%s modo=api_oficial", requested_url)
            payload = await http.get_json(
                OFFICIAL_API_ENDPOINT,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            items = _items(payload)
            source_url = OFFICIAL_API_ENDPOINT
            logger.info("[Gupy] url=%s itens_brutos=%d", requested_url, len(items))
        else:
            params = {"jobName": query.strip()}
            if location.strip():
                params["state"] = location.strip()
            requested_url = f"{PUBLIC_ENDPOINT}?{urlencode(params)}"
            logger.info("[Gupy] requisitando url=%s modo=portal_publico", requested_url)
            html = await http.get_text(PUBLIC_ENDPOINT, params=params)
            items = _next_items(html)
            source_url = PUBLIC_ENDPOINT
            logger.info("[Gupy] url=%s itens_brutos=%d", requested_url, len(items))
        jobs: list[VagaPadronizada] = []
        query_lower = f"{query} {location}".casefold().strip()
        for item in items:
            title = clean_text(item.get("name") or item.get("title"))
            if not title:
                continue
            company = clean_text(item.get("companyName") or item.get("company")) or "Não informado"
            if query_lower and (
                not matches_search_query_relaxed(query, title, company, clean_text(item.get("description")))
                or not matches_location(location, item.get("city"), item.get("state"), item.get("location"))
            ):
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
                    url_origem=source_url,
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

