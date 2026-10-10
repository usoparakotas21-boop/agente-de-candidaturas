"""LinkedIn vacancy collector backed by the authorized Apify Actor."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, parse_datetime, stable_external_id


SOURCE = "linkedin"
APIFY_RUN_URL = "https://api.apify.com/v2/acts/curious_coder~linkedin-jobs-scraper/run-sync-get-dataset-items"
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
logger = logging.getLogger(__name__)


def _items(payload: Any) -> list[dict[str, Any]]:
    """Normalize the Actor response, which is normally a JSON array."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


async def collect(
    query: str = "",
    *,
    location: str = "",
    limit: int = 25,
    client: SafeHttpClient | None = None,
) -> list[VagaPadronizada]:
    if not query.strip():
        logger.info("[%s] consulta vazia; nenhum resultado a coletar", SOURCE)
        return []

    # Read on each run so a worker-side variable update is picked up without
    # importing the module again; keep the module constant for configuration
    # introspection and compatibility with deployment checks.
    apify_token = (os.getenv("APIFY_TOKEN") or APIFY_TOKEN or "").strip()
    if not apify_token:
        logger.info("[%s] APIFY_TOKEN ausente; fonte desativada nesta execução", SOURCE)
        return []

    search_url = (
        "https://www.linkedin.com/jobs/search?"
        f"keywords={quote(query.strip())}&location={quote(location.strip())}"
    )
    run_url = f"{APIFY_RUN_URL}?token={quote(apify_token, safe='')}"
    payload = {
        "urls": [search_url],
        "maxItems": 15,
        "scrapeCompanyDetails": False,
    }
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        logger.info(
            "[%s] iniciando Actor Apify url=%s maxItems=%d scrapeCompanyDetails=%s",
            SOURCE,
            search_url,
            payload["maxItems"],
            payload["scrapeCompanyDetails"],
        )
        try:
            response = await http.request(
                "POST",
                run_url,
                json=payload,
                timeout=45.0,
                _retry_attempts=1,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            try:
                actor_payload = response.json()
            except ValueError:
                logger.info("[%s] Actor retornou corpo sem JSON válido", SOURCE)
                return []

            items = _items(actor_payload)
            logger.info("[%s] Actor retornou itens_brutos=%d", SOURCE, len(items))
            jobs: list[VagaPadronizada] = []
            max_items = min(max(limit, 1), 15)
            for item in items:
                title = clean_text(item.get("title"))
                if not title:
                    continue
                company = clean_text(item.get("companyName") or item.get("company")) or "Não informado"
                location_text = clean_text(item.get("location")) or "Não informado"
                job_url = clean_text(item.get("jobUrl") or item.get("link"))
                if not job_url:
                    continue
                date_value = item.get("publishedAt") or item.get("publishedDate") or item.get("date") or item.get("createdAt")
                tags_value = item.get("skills") or item.get("tags") or []
                tags = [clean_text(tag) for tag in tags_value if clean_text(tag)] if isinstance(tags_value, list) else []
                jobs.append(
                    VagaPadronizada(
                        id_externo=stable_external_id(SOURCE, item.get("id") or item.get("jobId") or job_url),
                        origem=SOURCE,
                        titulo=title,
                        empresa=company,
                        localidade=location_text,
                        url_candidatura=job_url,
                        url_origem=search_url,
                        descricao=clean_text(item.get("description") or item.get("snippet")),
                        palavras_chave=tags,
                        data_publicacao=parse_datetime(date_value),
                        metadados={"raw_source": SOURCE, "parser": "apify/curious_coder~linkedin-jobs-scraper"},
                    )
                )
                if len(jobs) >= max_items:
                    break
            logger.info("[%s] consulta=%r resultados=%d", SOURCE, query, len(jobs))
            return jobs
        except Exception as err:  # noqa: BLE001 - Apify must not block other sources
            # The Apify URL contains the bearer token; keep the exact failure
            # class/status useful without writing that credential to Railway.
            detail = str(err).replace(apify_token, "[redacted]")
            logger.error("[%s] Actor Apify falhou: %s: %s", SOURCE, type(err).__name__, detail)
            return []
    finally:
        if own_client:
            await http.aclose()

