"""Public LinkedIn job-page collector.

Only public search pages are considered.  The collector never logs in, calls
private endpoints, bypasses a challenge, or circumvents robots.txt.  If the
public page disallows automated access, ``SafeHttpClient`` stops collection.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, jobs_from_jsonld


SOURCE = "linkedin"
PUBLIC_ENDPOINT = "https://www.linkedin.com/jobs/search/"
logger = logging.getLogger(__name__)


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
    url = f"{PUBLIC_ENDPOINT}?{urlencode({'keywords': query.strip(), 'location': location.strip()})}"
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        jobs = jobs_from_jsonld(await http.get_text(url), source=SOURCE, page_url=url, query=f"{query} {location}".strip(), limit=limit)
        logger.info("[%s] consulta=%r resultados=%d", SOURCE, query, len(jobs))
        return jobs
    finally:
        if own_client:
            await http.aclose()

