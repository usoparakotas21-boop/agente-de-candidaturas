"""Collector for We Work Remotely's public RSS feed."""

from __future__ import annotations

from typing import Any

import xmltodict

from schemas import TipoModalidade, VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, parse_datetime, stable_external_id


SOURCE = "weworkremotely"
PUBLIC_ENDPOINT = "https://weworkremotely.com/remote-jobs.rss"


def _items(payload: Any) -> list[dict[str, Any]]:
    channel = payload.get("rss", {}).get("channel", {}) if isinstance(payload, dict) else {}
    raw = channel.get("item", []) if isinstance(channel, dict) else []
    return raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []


async def collect(
    query: str = "",
    *,
    limit: int = 25,
    client: SafeHttpClient | None = None,
) -> list[VagaPadronizada]:
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        payload = xmltodict.parse(await http.get_text(PUBLIC_ENDPOINT))
        query_lower = query.casefold().strip()
        jobs: list[VagaPadronizada] = []
        for item in _items(payload):
            title = clean_text(item.get("title"))
            if not title:
                continue
            description = clean_text(item.get("description"))
            if query_lower and query_lower not in f"{title} {description}".casefold():
                continue
            url = clean_text(item.get("link")) or PUBLIC_ENDPOINT
            jobs.append(
                VagaPadronizada(
                    id_externo=stable_external_id(SOURCE, item.get("guid") or url),
                    origem=SOURCE,
                    titulo=title,
                    empresa=clean_text(item.get("dc:creator") or item.get("author")) or "Não informado",
                    localidade=clean_text(item.get("region")) or "Global / remoto",
                    tipo_modalidade=TipoModalidade.REMOTO,
                    url_candidatura=url,
                    url_origem=PUBLIC_ENDPOINT,
                    descricao=description,
                    data_publicacao=parse_datetime(item.get("pubDate")),
                    metadados={"raw_source": SOURCE},
                )
            )
            if len(jobs) >= limit:
                break
        return jobs
    finally:
        if own_client:
            await http.aclose()

