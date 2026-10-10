"""Async HTTP client with pacing and bounded retries for public sources."""

from __future__ import annotations

import asyncio
import hashlib
import gzip
import html as html_lib
import json
import logging
import os
import re
import random
import time
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from schemas import TipoModalidade, VagaPadronizada

from .anti_ban import (
    AntiBanPolicy,
    obter_configuracao_proxy,
    obter_headers_camuflados,
)
from .delays import sleep_with_jitter
from .resilience import RetryPolicy, run_with_retries


RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
logger = logging.getLogger(__name__)

SEARCH_STOP_WORDS = {
    "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos", "e", "em",
    "na", "nas", "no", "nos", "o", "os", "para", "por", "um", "uma", "uns", "umas",
}


class RetryableHttpStatus(httpx.HTTPStatusError):
    """Marker used to retry transient HTTP responses."""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text = BeautifulSoup(html_lib.unescape(str(value)), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _search_tokens(value: str) -> list[str]:
    normalized = clean_text(value).casefold()
    return [
        token
        for token in re.findall(r"[\wÀ-ÿ]+", normalized, flags=re.UNICODE)
        if len(token) > 1 and token not in SEARCH_STOP_WORDS
    ]


def matches_search_query(query: str, *values: Any) -> bool:
    """Match every meaningful term without requiring one verbatim phrase."""

    query_text = clean_text(query).casefold()
    if not query_text:
        return True
    searchable = clean_text(" ".join(clean_text(value) for value in values)).casefold()
    if query_text in searchable:
        return True
    tokens = _search_tokens(query_text)
    if not tokens:
        return True
    unique_tokens = list(dict.fromkeys(tokens))
    matched = sum(token in searchable for token in unique_tokens)
    return matched == len(unique_tokens)


def stable_external_id(source: str, value: Any) -> str:
    candidate = clean_text(value)
    if candidate:
        return candidate[:250]
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None


async def fetch_via_scraperapi(
    url: str,
    render_js: bool = False,
    country: str = "br",
    *,
    client: SafeHttpClient | None = None,
) -> str:
    """Fetch a public URL through ScraperAPI when configured.

    The helper keeps the direct request path as the default so sources that do
    not need a proxy do not consume ScraperAPI credits. A caller may provide
    the shared ``SafeHttpClient`` to preserve pacing and retry behaviour.
    """

    parsed_url = urlsplit(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("A URL pública válida é obrigatória para o ScraperAPI.")
    api_key = os.getenv("SCRAPERAPI_KEY", "").strip()
    target_url = url
    if api_key:
        country_code = re.sub(r"[^A-Za-z]", "", country or "br").lower() or "br"
        target_url = (
            "https://api.scraperapi.com/?"
            f"api_key={quote(api_key, safe='')}"
            f"&url={quote(url, safe='')}"
            f"&country_code={quote(country_code, safe='')}"
        )
        if render_js:
            target_url += "&render=true"
        logger.info(
            "[ScraperAPI] proxy habilitado fonte=%s render_js=%s country=%s",
            parsed_url.netloc,
            render_js,
            country_code,
        )
    else:
        logger.debug("[ScraperAPI] SCRAPERAPI_KEY ausente; usando acesso direto fonte=%s", parsed_url.netloc)

    own_client = client is None
    http = client or SafeHttpClient()
    try:
        return await http.get_text(target_url)
    finally:
        if own_client:
            await http.aclose()


def _jsonld_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _jsonld_nodes(item)
    elif isinstance(value, dict):
        if isinstance(value.get("@graph"), list):
            yield from _jsonld_nodes(value["@graph"])
        else:
            yield value


def _location_text(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(filter(None, (_location_text(item) for item in value)))
    if isinstance(value, dict):
        address = value.get("address") if isinstance(value.get("address"), dict) else value
        return ", ".join(
            filter(
                None,
                (
                    clean_text(address.get("addressLocality")),
                    clean_text(address.get("addressRegion")),
                    clean_text(address.get("addressCountry")),
                ),
            )
        )
    return clean_text(value)


def jobs_from_jsonld(
    html: str,
    *,
    source: str,
    page_url: str,
    query: str = "",
    limit: int = 50,
) -> list[VagaPadronizada]:
    """Extract only explicit Schema.org JobPosting objects from public HTML."""

    soup = BeautifulSoup(html, "html.parser")
    jobs: list[VagaPadronizada] = []
    scripts = soup.select('script[type="application/ld+json"]')
    if not scripts:
        raise ValueError(f"{source}: resposta sem script JSON-LD; parser de vagas não encontrou dados estruturados")
    raw_count = 0
    for script in scripts:
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        for item in _jsonld_nodes(payload):
            job_type = item.get("@type")
            if not (job_type == "JobPosting" or (isinstance(job_type, list) and "JobPosting" in job_type)):
                continue
            raw_count += 1
            title = clean_text(item.get("title"))
            if not title:
                continue
            location_text = _location_text(item.get("jobLocation")) or "Não informado"
            description = clean_text(item.get("description"))
            company_value = item.get("hiringOrganization")
            company = clean_text(company_value.get("name") if isinstance(company_value, dict) else company_value)
            if query and not matches_search_query(query, title, company, location_text, description):
                continue
            url = urljoin(page_url, clean_text(item.get("url")) or page_url)
            modality = " ".join(
                filter(
                    None,
                    (
                        clean_text(item.get("jobLocationType")),
                        clean_text(item.get("workplaceType")),
                        clean_text(item.get("jobLocation")),
                    ),
                )
            )
            identifier = item.get("identifier")
            if isinstance(identifier, dict):
                identifier = identifier.get("value") or identifier.get("name")
            try:
                jobs.append(
                    VagaPadronizada(
                        id_externo=stable_external_id(source, identifier or url or title),
                        origem=source,
                        titulo=title,
                        empresa=company or "Não informado",
                        localidade=location_text,
                        tipo_modalidade=modality,
                        url_candidatura=url,
                        url_origem=page_url,
                        descricao=description,
                        tipo_contrato=clean_text(item.get("employmentType")) or None,
                        data_publicacao=parse_datetime(item.get("datePosted")),
                        metadados={"parser": "schema.org/JobPosting"},
                    )
                )
            except ValueError:
                continue
            if len(jobs) >= limit:
                logger.info("[JobParser] fonte=%s itens_brutos_jsonld=%d itens_filtrados=%d", source, raw_count, len(jobs))
                return jobs
    logger.info("[JobParser] fonte=%s itens_brutos_jsonld=%d itens_filtrados=%d", source, raw_count, len(jobs))
    if not jobs:
        raise ValueError(f"{source}: JSON-LD encontrado, mas nenhum JobPosting correspondeu à consulta {query!r}")
    return jobs


class SafeHttpClient:
    """Shared client for respectful, public, rate-limited requests."""

    def __init__(self, policy: AntiBanPolicy | None = None, client: httpx.AsyncClient | None = None):
        self.policy = policy or AntiBanPolicy()
        self._client = client or criar_cliente_protegido(policy=self.policy)
        self._owns_client = client is None
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}

    async def __aenter__(self) -> "SafeHttpClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _host_key(url: str) -> str:
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}".casefold()

    async def _wait_for_host(self, host: str) -> None:
        previous = self._last_request.get(host)
        if previous is not None:
            elapsed = time.monotonic() - previous
            target = self.policy.min_delay_seconds
            if elapsed < target:
                await sleep_with_jitter(target - elapsed, max(0.0, self.policy.max_delay_seconds - target))
        self._last_request[host] = time.monotonic()

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.policy.validate_url(url)
        host = self._host_key(url)
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        request_kwargs = {"headers": self.policy.headers, **kwargs}

        async def operation() -> httpx.Response:
            async with lock:
                await self._wait_for_host(host)
                response = await self._client.request(method, url, **request_kwargs)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise RetryableHttpStatus(
                        f"Resposta transitória {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                if len(response.content) > self.policy.max_response_bytes:
                    raise ValueError("A resposta excede o limite de tamanho configurado.")
                return response

        def retry_if(error: Exception) -> bool:
            return isinstance(error, (httpx.HTTPError, OSError)) and not isinstance(error, PermissionError)

        return await run_with_retries(
            operation,
            policy=RetryPolicy(attempts=self.policy.max_retries + 1),
            retry_if=retry_if,
        )

    async def get_text(self, url: str, **kwargs: Any) -> str:
        response = await self.request("GET", url, **kwargs)
        return self._decoded_content(response).decode(response.encoding or "utf-8", errors="replace")

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.request("GET", url, **kwargs)
        content = self._decoded_content(response).decode(response.encoding or "utf-8", errors="replace")
        return json.loads(content.lstrip("\ufeff"))

    @staticmethod
    def _decoded_content(response: httpx.Response) -> bytes:
        content = response.content
        if content.startswith(b"\x1f\x8b"):
            return gzip.decompress(content)
        return content

    async def get_public_html_jobs(
        self,
        url: str,
        *,
        source: str,
        limit: int = 50,
    ) -> list[VagaPadronizada]:
        html = await self.get_text(url)
        return jobs_from_jsonld(html, source=source, page_url=url, limit=limit)


async def fazer_requisicao_get(url: str, params: dict[str, Any] | None = None) -> str:
    """Fetch a public page through the shared safe client."""

    async with SafeHttpClient() as client:
        return await client.get_text(url, params=params)

def criar_cliente_protegido(
    timeout: float | None = 12.0,
    proxy: str | None = None,
    proxies_rotativos: Sequence[str] | None = None,
    *,
    policy: AntiBanPolicy | None = None,
) -> httpx.AsyncClient:
    """Create an async client with optional proxy selection.

    A proxy is opt-in and must be supplied by the caller. The helper does not
    rotate identities or bypass robots.txt, CAPTCHAs, authentication, or
    provider access controls.
    """

    request_policy = policy or AntiBanPolicy()
    timeout_seconds = request_policy.request_timeout_seconds if timeout is None else timeout
    if timeout_seconds <= 0:
        raise ValueError("O timeout deve ser positivo.")
    proxy_pool = [item.strip() for item in (proxies_rotativos or []) if item and item.strip()]
    selected_proxy = proxy or (random.choice(proxy_pool) if proxy_pool else None) or obter_configuracao_proxy()
    kwargs: dict[str, Any] = {
        "follow_redirects": True,
        "timeout": timeout_seconds,
        "headers": obter_headers_camuflados(),
        "verify": True,
    }
    if selected_proxy:
        kwargs["proxies"] = selected_proxy
    try:
        return httpx.AsyncClient(**kwargs)
    except TypeError:
        # httpx 0.28 renamed the singular-client proxy argument.
        if selected_proxy:
            kwargs.pop("proxies", None)
            kwargs["proxy"] = selected_proxy
            return httpx.AsyncClient(**kwargs)
        raise


