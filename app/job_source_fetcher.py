from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
import unicodedata
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3


class SourceFetchError(RuntimeError):
    pass


class _StructuredDataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_json = False
        self.current: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() != "script":
            return
        values = {key.casefold(): value or "" for key, value in attrs}
        if "ld+json" in values.get("type", "").casefold():
            self.in_json = True
            self.current = []

    def handle_data(self, data):
        if self.in_json:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag.casefold() == "script" and self.in_json:
            self.scripts.append("".join(self.current))
            self.current = []
            self.in_json = False


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.values.append(value)


def _strip_html(value: str) -> str:
    parser = _TextParser()
    parser.feed(html.unescape(value or ""))
    return "\n".join(parser.values)


def _find_job_posting(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        kind = value.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(item).casefold() == "jobposting" for item in kinds):
            return value
        for child in value.values():
            found = _find_job_posting(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_job_posting(child)
            if found:
                return found
    return None


def _organization_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()
    if isinstance(value, list):
        for item in value:
            result = _organization_name(item)
            if result:
                return result
    return str(value or "").strip()


def _location(value: Any) -> str:
    if isinstance(value, list):
        values = [_location(item) for item in value]
        return " | ".join(item for item in values if item)
    if not isinstance(value, dict):
        return str(value or "").strip()
    address = value.get("address", value)
    if not isinstance(address, dict):
        return str(address or "").strip()
    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("addressCountry"),
    ]
    return "/".join(str(item).strip() for item in parts if item)


def extract_job_posting_html(page_html: str, url: str) -> dict[str, Any] | None:
    parser = _StructuredDataParser()
    parser.feed(page_html)
    posting = None
    for script in parser.scripts:
        try:
            posting = _find_job_posting(json.loads(script))
        except (json.JSONDecodeError, TypeError):
            continue
        if posting:
            break
    if not posting:
        return None

    title = str(posting.get("title") or posting.get("name") or "").strip()
    company = _organization_name(posting.get("hiringOrganization"))
    description = _strip_html(str(posting.get("description") or ""))
    location = _location(posting.get("jobLocation"))
    modality = ""
    if str(posting.get("jobLocationType") or "").casefold() == "telecommute":
        modality = "Remoto"
    employment = posting.get("employmentType")
    if isinstance(employment, list):
        employment = ", ".join(str(item) for item in employment)

    confidence = 10
    confidence += 20 if title else 0
    confidence += 20 if company else 0
    confidence += 30 if len(description) >= 300 else 15 if description else 0
    confidence += 10 if location else 0
    confidence += 10 if url else 0
    return {
        "title": title,
        "company": company,
        "description": description,
        "location": location,
        "modality": modality,
        "salary": "",
        "url": url,
        "employment_type": str(employment or ""),
        "confidence": min(confidence, 100),
        "method": "jobposting_jsonld",
    }


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SourceFetchError("Link publico invalido.")
    if parsed.username or parsed.password:
        raise SourceFetchError("Link com credenciais nao permitido.")
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or default_port)
    except OSError as exc:
        raise SourceFetchError("Nao foi possivel localizar o site da vaga.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise SourceFetchError("O link nao aponta para um site publico.")
    return url


def fetch_job_posting(url: str) -> dict[str, Any] | None:
    try:
        import httpx
    except ImportError as exc:
        raise SourceFetchError("O cliente HTTP nao esta instalado.") from exc
    current = _validate_public_url(url)
    headers = {
        "User-Agent": "AgenteDeCandidaturas/0.18 (+job-intake; public-pages-only)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        with httpx.Client(timeout=8.0, follow_redirects=False, headers=headers) as client:
            for _ in range(MAX_REDIRECTS + 1):
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise SourceFetchError("Redirecionamento sem destino.")
                        current = _validate_public_url(urljoin(current, location))
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").casefold()
                    if "html" not in content_type:
                        raise SourceFetchError("O link nao retornou uma pagina HTML.")
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_SOURCE_BYTES:
                            raise SourceFetchError("A pagina excede o limite de 2 MB.")
                        chunks.append(chunk)
                    encoding = response.encoding or "utf-8"
                    page_html = b"".join(chunks).decode(encoding, errors="replace")
                    return extract_job_posting_html(page_html, current)
    except httpx.HTTPError as exc:
        raise SourceFetchError("Nao foi possivel ler a pagina publica da vaga.") from exc
    raise SourceFetchError("A pagina excedeu o limite de redirecionamentos.")


def _slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return "-".join(re.findall(r"[a-z0-9]+", value.casefold()))


def infer_from_public_url(parsed_job: dict[str, Any]) -> dict[str, Any] | None:
    url = parsed_job.get("url") or ""
    parsed_url = urlparse(url)
    host = (parsed_url.hostname or "").casefold()
    if not host.endswith("bebee.com") or "/jobs/" not in parsed_url.path:
        return None

    slug = parsed_url.path.split("/jobs/", 1)[1].strip("/")
    slug = slug.split("--theirstack", 1)[0]
    title = parsed_job.get("title") or ""
    title_slug = _slugify(title)
    if not title_slug or not slug.startswith(f"{title_slug}-"):
        return None
    remainder = slug[len(title_slug) + 1:]
    for continuation in ("generalista", "junior", "pleno", "senior", "jr", "sr"):
        if remainder.startswith(f"{continuation}-"):
            title = f"{title} {continuation.title()}"
            remainder = remainder[len(continuation) + 1:]
            break

    location = parsed_job.get("location") or ""
    location_slug = _slugify(location)
    location_suffix = f"-{location_slug}" if location_slug else ""
    if not location_suffix or location_suffix not in remainder:
        city = location.split(",", 1)[0].strip() if "," in location else ""
        city_slug = _slugify(city)
        state_match = re.search(
            rf"-(?P<location>{re.escape(city_slug)}-[a-z]{{2}})$",
            remainder,
        ) if city_slug else None
        if not state_match:
            return None
        location_suffix = f"-{state_match.group('location')}"
    company_slug = remainder.rsplit(location_suffix, 1)[0]
    if not company_slug:
        return None
    company = " ".join(part.capitalize() for part in company_slug.split("-") if part)
    result = dict(parsed_job)
    result.update(
        {
            "title": title,
            "company": company,
            "confidence": 88,
            "method": "public_url_slug",
        }
    )
    return result
