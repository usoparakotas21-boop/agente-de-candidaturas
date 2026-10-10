"""Collector for Remote OK's public JSON feed."""

from __future__ import annotations

from schemas import TipoModalidade, VagaPadronizada
from utils.http_client import SafeHttpClient, clean_text, matches_search_query, parse_datetime, stable_external_id


SOURCE = "remoteok"
PUBLIC_ENDPOINT = "https://remoteok.com/api"


async def collect(
    query: str = "",
    *,
    limit: int = 25,
    client: SafeHttpClient | None = None,
) -> list[VagaPadronizada]:
    own_client = client is None
    http = client or SafeHttpClient()
    try:
        payload = await http.get_json(PUBLIC_ENDPOINT)
        if not isinstance(payload, list):
            raise ValueError(f"{SOURCE}: resposta JSON inesperada; esperado lista, recebido {type(payload).__name__}")
        query_lower = query.casefold().strip()
        jobs: list[VagaPadronizada] = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("position"):
                continue
            title = clean_text(item.get("position"))
            company = clean_text(item.get("company")) or "Não informado"
            tags = [clean_text(tag) for tag in item.get("tags", []) if clean_text(tag)]
            if query_lower and not matches_search_query(query, title, company, *tags):
                continue
            url = clean_text(item.get("url"))
            if not url:
                slug = clean_text(item.get("slug") or item.get("id"))
                url = f"https://remoteok.com/remote-jobs/{slug}" if slug else PUBLIC_ENDPOINT
            jobs.append(
                VagaPadronizada(
                    id_externo=stable_external_id(SOURCE, item.get("id") or item.get("slug") or url),
                    origem=SOURCE,
                    titulo=title,
                    empresa=company,
                    localidade=clean_text(item.get("location")) or "Global / remoto",
                    tipo_modalidade=TipoModalidade.REMOTO,
                    url_candidatura=url,
                    url_origem=PUBLIC_ENDPOINT,
                    descricao=clean_text(item.get("description")),
                    palavras_chave=tags,
                    tipo_contrato=clean_text(item.get("schedule")) or None,
                    data_publicacao=parse_datetime(item.get("date")),
                    metadados={"raw_source": SOURCE},
                )
            )
            if len(jobs) >= limit:
                break
        return jobs
    finally:
        if own_client:
            await http.aclose()

