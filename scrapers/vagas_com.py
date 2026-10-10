"""Collector for public Schema.org postings on Vagas.com.br."""

from __future__ import annotations

import re
from urllib.parse import quote

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, jobs_from_jsonld


SOURCE = "vagas_com"
BASE_URL = "https://www.vagas.com.br/vagas-de-"


async def collect(
    query: str = "",
    *,
    limit: int = 25,
    client: SafeHttpClient | None = None,
) -> list[VagaPadronizada]:
    if not query.strip():
        return []
    slug = re.sub(r"[^a-z0-9]+", "-", query.casefold()).strip("-")
    url = f"{BASE_URL}{quote(slug)}"
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        return jobs_from_jsonld(await http.get_text(url), source=SOURCE, page_url=url, limit=limit)
    finally:
        if own_client:
            await http.aclose()

