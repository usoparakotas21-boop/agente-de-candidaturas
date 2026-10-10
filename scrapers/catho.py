"""Collector for public Catho job pages."""

from __future__ import annotations

import re
from urllib.parse import quote

from schemas import VagaPadronizada
from utils.http_client import SafeHttpClient, jobs_from_jsonld


SOURCE = "catho"
BASE_URL = "https://www.catho.com.br/vagas/"


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
    search_slug = re.sub(r"[^a-z0-9]+", "-", f"{query} {location}".casefold()).strip("-")
    url = f"{BASE_URL}{quote(search_slug)}/"
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        return jobs_from_jsonld(await http.get_text(url), source=SOURCE, page_url=url, query=f"{query} {location}".strip(), limit=limit)
    finally:
        if own_client:
            await http.aclose()

