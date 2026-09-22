"""Fail-closed ingestion for explicitly authorized public JSON job feeds.

This module does not schedule collection or scrape HTML. Each request requires
source-specific authorization, commercial display and description-cache rights,
and an available distributed rate limiter before making network calls.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import distributed_rate_limit
from .models import JobListing, utc_now
from .source_governance import (
    SOURCE_REGISTRY,
    JobSource,
    SourceApprovalError,
    SourceRegistry,
    SourceUse,
    require_approved_source,
)
from .text_sanitization import sanitize_untrusted_text

MAX_FEED_BYTES = 2_000_000
MAX_LISTINGS_PER_FEED = 500
FETCH_TIMEOUT_SECONDS = 10.0
MAX_FETCH_DURATION_SECONDS = 25.0
REQUIRED_INGESTION_USES = (
    SourceUse.AUTOMATED_FETCH,
    SourceUse.COMMERCIAL_DISPLAY,
    SourceUse.DESCRIPTION_CACHING,
)


class JobIngestionError(ValueError):
    """Raised when a source feed cannot safely be parsed or stored."""


@dataclass(frozen=True, slots=True)
class IngestionResult:
    fetched: int
    upserted: int
    skipped: int


def _text(value: Any, *, limit: int) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    return sanitize_untrusted_text(str(value), max_chars=limit).strip()


def _first_allowed(
    record: dict[str, Any], source: JobSource, aliases: Iterable[str], *, limit: int
) -> str:
    allowed = set(source.allowed_fields)
    for alias in aliases:
        if alias in allowed and alias in record:
            value = _text(record[alias], limit=limit)
            if value:
                return value
    return ""


def _safe_application_url(value: str) -> str:
    if not value or len(value) > 1000 or any(ord(char) < 0x20 or char.isspace() for char in value):
        return ""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
    ):
        return ""
    return value


def _infer_work_mode(explicit: str, searchable_text: str) -> str | None:
    normalized = explicit.casefold().replace("-", "_").strip()
    if normalized in {"remote", "remoto", "remota", "home office"}:
        return "remote"
    if normalized in {"hybrid", "hibrido", "híbrido", "hibrida", "híbrida"}:
        return "hybrid"
    if normalized in {"on_site", "onsite", "presencial"}:
        return "on_site"

    text = searchable_text.casefold()
    has_hybrid = bool(re.search(r"\b(h[ií]brid[oa]|hybrid)\b", text))
    has_remote = bool(re.search(r"\b(remot[oa]|home office|remote)\b", text))
    has_on_site = bool(re.search(r"\b(presencial|on[- ]?site)\b", text))
    matches = sum((has_hybrid, has_remote, has_on_site))
    if matches != 1:
        return None
    if has_hybrid:
        return "hybrid"
    if has_remote:
        return "remote"
    return "on_site"


def _infer_contract_type(explicit: str, searchable_text: str) -> str | None:
    normalized = explicit.strip().upper()
    if normalized in {"CLT", "PJ"}:
        return normalized
    text = searchable_text.casefold()
    has_clt = bool(re.search(r"\bclt\b", text))
    has_pj = bool(re.search(r"\bpj\b|pessoa jur[ií]dica", text))
    if has_clt == has_pj:
        return None
    return "CLT" if has_clt else "PJ"


def normalize_job_listing(record: Any, source: JobSource) -> dict[str, Any]:
    """Normalize one authorized JSON record; unsupported or ambiguous rows fail closed."""
    if not isinstance(record, dict):
        raise JobIngestionError("Listing must be a JSON object.")

    title = _first_allowed(record, source, ("title",), limit=250)
    company = _first_allowed(record, source, ("company_name", "company"), limit=200)
    location = _first_allowed(record, source, ("location",), limit=300)
    description = _first_allowed(record, source, ("description",), limit=20_000)
    application_url = _first_allowed(
        record, source, ("application_url", "apply_url"), limit=1000
    )
    application_url = _safe_application_url(application_url)
    salary_range = _first_allowed(
        record, source, ("salary_range", "salary"), limit=200
    )
    explicit_work_mode = _first_allowed(record, source, ("work_mode",), limit=40)
    explicit_contract_type = _first_allowed(record, source, ("contract_type",), limit=40)
    status = _first_allowed(record, source, ("status",), limit=20).casefold()
    status = status if status in {"active", "expired"} else "active"

    searchable_text = " ".join(part for part in (title, description) if part)
    work_mode = _infer_work_mode(explicit_work_mode, searchable_text)
    contract_type = _infer_contract_type(explicit_contract_type, searchable_text)
    external_id = _first_allowed(
        record, source, ("external_id", "id"), limit=300
    )
    if not external_id:
        identity = "|".join((application_url, title, company, location))
        if not any((application_url, title, company, location)):
            raise JobIngestionError("Listing has no stable fields for deduplication.")
        external_id = "derived:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()

    if not title or not application_url:
        raise JobIngestionError("Listing is missing a title or safe HTTPS application URL.")

    return {
        "source_name": source.source_id,
        "external_id": external_id,
        "title": title,
        "company_name": company,
        "location": location,
        "work_mode": work_mode,
        "contract_type": contract_type,
        "description": description,
        "application_url": application_url,
        "salary_range": salary_range,
        "status": status,
    }


def _require_ingestion_source(
    source_id: str, registry: SourceRegistry
) -> JobSource:
    return require_approved_source(
        source_id,
        registry=registry,
        required_uses=REQUIRED_INGESTION_USES,
    )


def fetch_authorized_json_feed(
    source_id: str,
    *,
    registry: SourceRegistry = SOURCE_REGISTRY,
    client_factory: Callable[..., Any] = httpx.Client,
    limiter_is_configured: Callable[[], bool] = distributed_rate_limit.is_configured,
    limiter_check: Callable[..., tuple[bool, int]] = distributed_rate_limit.check,
    lease_acquire: Callable[[str, int], str | None] = distributed_rate_limit.acquire_lease,
    lease_release: Callable[[str, str], bool] = distributed_rate_limit.release_lease,
) -> list[dict[str, Any]]:
    """Fetch one fixed, approved HTTPS JSON endpoint; redirects and HTML are rejected."""
    source = _require_ingestion_source(source_id, registry)
    if not limiter_is_configured():
        raise JobIngestionError("Distributed source rate limiting is unavailable.")
    lease_key = f"job-ingestion-lock:{source.source_id}"
    lease_token = lease_acquire(lease_key, 30)
    if not lease_token:
        raise JobIngestionError("Another request is already processing this source.")
    fetch_started = time.monotonic()
    try:
        blocked, retry_after = limiter_check(
            [f"job-ingestion:{source.source_id}"],
            source.rate_limit_requests_per_minute,
            60,
        )
        if blocked:
            raise JobIngestionError(f"Source rate limit reached; retry after {retry_after}s.")

        with client_factory(
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
            headers={"Accept": "application/json"},
        ) as client:
            with client.stream("GET", source.endpoint_url) as response:
                if 300 <= response.status_code < 400:
                    raise JobIngestionError("Source redirects are not accepted.")
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json" and not content_type.endswith("+json"):
                    raise JobIngestionError("Approved source did not return JSON.")
                declared_size = response.headers.get("content-length", "").strip()
                if declared_size.isdigit() and int(declared_size) > MAX_FEED_BYTES:
                    raise JobIngestionError("Source feed exceeds the configured size limit.")
                chunks: list[bytes] = []
                total_bytes = 0
                for chunk in response.iter_bytes():
                    if time.monotonic() - fetch_started > MAX_FETCH_DURATION_SECONDS:
                        raise JobIngestionError("Source feed exceeded the time limit.")
                    total_bytes += len(chunk)
                    if total_bytes > MAX_FEED_BYTES:
                        raise JobIngestionError("Source feed exceeds the configured size limit.")
                    chunks.append(chunk)
    except JobIngestionError:
        raise
    except httpx.HTTPError as exc:
        raise JobIngestionError("Approved source request failed.") from exc
    finally:
        lease_release(lease_key, lease_token)

    try:
        payload = json.loads(b"".join(chunks))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JobIngestionError("Approved source returned invalid JSON.") from exc

    records: Any = payload
    if isinstance(payload, dict):
        records = payload.get("jobs", payload.get("data"))
    if not isinstance(records, list):
        raise JobIngestionError("JSON feed must be a list or contain a jobs/data list.")
    if len(records) > MAX_LISTINGS_PER_FEED:
        raise JobIngestionError("Source feed exceeds the listing-count limit.")
    return records


def upsert_job_listings(
    db: Session,
    source_id: str,
    records: Iterable[Any],
    *,
    registry: SourceRegistry = SOURCE_REGISTRY,
) -> IngestionResult:
    """Deduplicate/update rows by (source_name, external_id); caller owns commit/rollback."""
    source = _require_ingestion_source(source_id, registry)
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        insert = pg_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:
        raise JobIngestionError("Job listing upsert requires PostgreSQL or SQLite.")

    fetched = upserted = skipped = 0
    for record in records:
        fetched += 1
        try:
            values = normalize_job_listing(record, source)
        except JobIngestionError:
            skipped += 1
            continue
        statement = insert(JobListing).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[JobListing.source_name, JobListing.external_id],
            set_={
                key: getattr(statement.excluded, key)
                for key in values
                if key not in {"source_name", "external_id"}
            } | {"updated_at": utc_now()},
        )
        db.execute(statement)
        upserted += 1
    db.flush()
    return IngestionResult(fetched=fetched, upserted=upserted, skipped=skipped)


def ingest_authorized_json_feed(
    db: Session,
    source_id: str,
    *,
    registry: SourceRegistry = SOURCE_REGISTRY,
    client_factory: Callable[..., Any] = httpx.Client,
) -> IngestionResult:
    """Fetch and upsert one approved JSON feed; no scheduler or source is enabled here."""
    records = fetch_authorized_json_feed(
        source_id,
        registry=registry,
        client_factory=client_factory,
    )
    return upsert_job_listings(db, source_id, records, registry=registry)
