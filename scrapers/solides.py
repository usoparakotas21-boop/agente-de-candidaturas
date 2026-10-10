"""Collector for public job pages exposed by Sólides."""

from __future__ import annotations

import re
from urllib.parse import quote

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, jobs_from_jsonld


SOURCE = "solides"
BASE_URL = "https://vagas.solides.com.br/?search="


async def collect(
    query: str = "",
    *,
    limit: int = 25,
    client: SafeHttpClient | None = None,
) -> list[VagaPadronizada]:
    if not query.strip():
        return []
    normalized = re.sub(r"\s+", " ", query).strip()
    url = f"{BASE_URL}{quote(normalized)}"
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        return jobs_from_jsonld(await http.get_text(url), source=SOURCE, page_url=url, query=query, limit=limit)
    finally:
        if own_client:
            await http.aclose()

