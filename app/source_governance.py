"""Fail-closed approval checks for automated job-source uses.

This module intentionally contains no pre-approved sources. An ATS being
publicly reachable, or already supported by a user-initiated fetch flow, does
not by itself grant permission for automated collection, commercial display,
or candidate submission. Each worker or connector must request every right it
uses through :func:`require_approved_source`.

The guard is deliberately separate from ``job_source_fetcher.fetch_job_posting``
so existing user-initiated imports keep their current behavior.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Iterable
from urllib.parse import SplitResult, urlsplit


class SourceApprovalError(ValueError):
    """Raised when a source is unknown, unsafe, or not fully approved."""


class SourceStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    SUSPENDED = "suspended"


class SourceUse(str, Enum):
    """Rights which must be explicitly granted for each source behavior."""

    AUTOMATED_FETCH = "automated_fetch"
    COMMERCIAL_DISPLAY = "commercial_display"
    AI_PROCESSING = "ai_processing"
    DESCRIPTION_CACHING = "description_caching"
    REDISTRIBUTION = "redistribution"
    AUTOMATED_SUBMISSION = "automated_submission"


APPROVAL_MAX_AGE_DAYS = 180


_SOURCE_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")
_DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _canonical_domain(value: str) -> str:
    """Validate and canonicalize one DNS hostname (never a URL or IP)."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("approved domains must be non-empty hostnames")
    if any(ch.isspace() or ord(ch) < 0x21 or ord(ch) == 0x7F for ch in value):
        raise ValueError("approved domain contains whitespace or control characters")
    if any(ch in value for ch in "/\\@:#%?[]") or value.endswith("."):
        raise ValueError("approved domain must be a plain DNS hostname")

    try:
        ascii_host = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("approved domain is not a valid IDN hostname") from exc

    if len(ascii_host) > 253 or "." not in ascii_host:
        raise ValueError("approved domain must be a fully qualified hostname")
    try:
        ipaddress.ip_address(ascii_host)
    except ValueError:
        pass
    else:
        raise ValueError("IP addresses cannot be approved as source domains")

    labels = ascii_host.split(".")
    if any(not _DNS_LABEL_RE.fullmatch(label) for label in labels):
        raise ValueError("approved domain contains an invalid DNS label")
    if labels[-1] in {"localhost", "local", "internal", "test", "invalid", "example"}:
        raise ValueError("non-public or reserved hostnames cannot be approved")
    return ascii_host


def _parse_source_url(value: str) -> tuple[SplitResult, str]:
    """Parse only unambiguous HTTPS URLs with a public DNS hostname."""
    if not isinstance(value, str) or not value:
        raise SourceApprovalError("A source URL is required.")
    if value != value.strip() or any(
        ch.isspace() or ord(ch) < 0x21 or ord(ch) == 0x7F for ch in value
    ):
        raise SourceApprovalError("The source URL contains whitespace or control characters.")
    if "\\" in value or value.startswith("//"):
        raise SourceApprovalError("The source URL is ambiguous.")

    try:
        parsed = urlsplit(value)
        # Accessing .port also validates malformed and out-of-range ports.
        port = parsed.port
    except ValueError as exc:
        raise SourceApprovalError("The source URL is malformed.") from exc

    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SourceApprovalError("Automated sources must use an absolute HTTPS URL.")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise SourceApprovalError("Credentials are not allowed in a source URL.")
    if parsed.fragment:
        raise SourceApprovalError("Fragments are not allowed in a source URL.")
    if port not in (None, 443):
        raise SourceApprovalError("Only the default HTTPS port is allowed.")

    host = parsed.hostname
    if not host:
        raise SourceApprovalError("The source URL has no hostname.")
    try:
        canonical_host = _canonical_domain(host)
    except ValueError as exc:
        raise SourceApprovalError("The source URL has an invalid or non-public hostname.") from exc
    return parsed, canonical_host


@dataclass(frozen=True, slots=True)
class JobSource:
    """Review record required before a source can be used by an automated worker.

    ``approved_domains`` are exact hostnames. Subdomains must be listed
    separately; this avoids silently trusting an entire domain tree.
    """

    source_id: str
    display_name: str
    source_owner: str
    source_owner_reference: str
    approved_domains: tuple[str, ...]
    endpoint_url: str
    allowed_fields: tuple[str, ...]
    permitted_uses: frozenset[SourceUse]
    status: SourceStatus
    permission_basis: str
    permission_evidence: str
    terms_reference: str
    robots_review: str
    attribution: str
    rate_limit_requests_per_minute: int
    rate_limit_max_concurrency: int
    raw_content_retention_ttl_days: int
    reviewed_at: date

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not _SOURCE_ID_RE.fullmatch(self.source_id):
            raise ValueError("source_id must be a lowercase slug")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("display_name is required")
        for field_name in ("source_owner", "source_owner_reference", "endpoint_url"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise ValueError(f"{field_name} must be text")
        try:
            status = SourceStatus(self.status)
        except (TypeError, ValueError) as exc:
            raise ValueError("status must be pending, approved, denied, or suspended") from exc
        object.__setattr__(self, "status", status)

        if isinstance(self.approved_domains, str):
            raise ValueError("approved_domains must be a sequence of exact hostnames")
        domains = tuple(_canonical_domain(domain) for domain in self.approved_domains)
        if len(domains) != len(set(domains)):
            raise ValueError("approved_domains cannot contain duplicates")
        object.__setattr__(self, "approved_domains", domains)

        if isinstance(self.allowed_fields, str):
            raise ValueError("allowed_fields must be a sequence of field names")
        fields = tuple(self.allowed_fields)
        if any(not isinstance(field, str) for field in fields):
            raise ValueError("allowed_fields entries must be text")
        if any(not field.strip() for field in fields) or len(fields) != len(set(fields)):
            raise ValueError("allowed_fields must contain unique, non-empty field names")
        object.__setattr__(self, "allowed_fields", fields)

        if isinstance(self.permitted_uses, str):
            raise ValueError("permitted_uses must be a sequence of explicit rights")
        try:
            permitted_uses = frozenset(SourceUse(use) for use in self.permitted_uses)
        except (TypeError, ValueError) as exc:
            raise ValueError("permitted_uses contains an unknown right") from exc
        object.__setattr__(self, "permitted_uses", permitted_uses)

        if self.endpoint_url.strip():
            endpoint, endpoint_host = _parse_source_url(self.endpoint_url)
            if endpoint.query:
                raise ValueError("endpoint_url must identify a fixed path without query parameters")
            if endpoint_host not in domains:
                raise ValueError("endpoint_url host must be listed in approved_domains")

        for field_name in (
            "permission_basis",
            "permission_evidence",
            "terms_reference",
            "robots_review",
            "attribution",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise ValueError(f"{field_name} must be text")

        if (
            isinstance(self.rate_limit_requests_per_minute, bool)
            or not isinstance(self.rate_limit_requests_per_minute, int)
            or self.rate_limit_requests_per_minute < 1
        ):
            raise ValueError("rate_limit_requests_per_minute must be a positive integer")
        if (
            isinstance(self.rate_limit_max_concurrency, bool)
            or not isinstance(self.rate_limit_max_concurrency, int)
            or self.rate_limit_max_concurrency < 1
        ):
            raise ValueError("rate_limit_max_concurrency must be a positive integer")
        if (
            isinstance(self.raw_content_retention_ttl_days, bool)
            or not isinstance(self.raw_content_retention_ttl_days, int)
            or self.raw_content_retention_ttl_days < 0
        ):
            raise ValueError("raw_content_retention_ttl_days must be zero or greater")
        if type(self.reviewed_at) is not date:
            raise ValueError("reviewed_at must be a date")

    def approval_gaps(self) -> tuple[str, ...]:
        """Return required approval evidence that is still missing."""
        required = {
            "source_owner": bool(self.source_owner.strip()),
            "source_owner_reference": bool(self.source_owner_reference.strip()),
            "approved_domains": bool(self.approved_domains),
            "endpoint_url": bool(self.endpoint_url.strip()),
            "allowed_fields": bool(self.allowed_fields),
            "permitted_uses": SourceUse.AUTOMATED_FETCH in self.permitted_uses,
            "permission_basis": bool(self.permission_basis.strip()),
            "permission_evidence": bool(self.permission_evidence.strip()),
            "terms_reference": bool(self.terms_reference.strip()),
            "robots_review": bool(self.robots_review.strip()),
            "attribution": bool(self.attribution.strip()),
        }
        return tuple(name for name, present in required.items() if not present)


class SourceRegistry:
    """In-memory registry; starts empty and denies every unregistered source."""

    def __init__(self, sources: Iterable[JobSource] = ()) -> None:
        self._sources: dict[str, JobSource] = {}
        for source in sources:
            self.register(source)

    def register(self, source: JobSource) -> None:
        if not isinstance(source, JobSource):
            raise TypeError("source must be a JobSource")
        if source.source_id in self._sources:
            raise ValueError(f"source_id already registered: {source.source_id}")
        self._sources[source.source_id] = source

    def get(self, source_id: str) -> JobSource | None:
        return self._sources.get(source_id)

    def matching_domain(self, hostname: str) -> tuple[JobSource, ...]:
        # Exact host matching is intentional. Add every reviewed subdomain as
        # its own entry; never infer permission from a parent or suffix match.
        return tuple(
            source
            for source in self._sources.values()
            if hostname in source.approved_domains
        )

    def sources(self) -> tuple[JobSource, ...]:
        """Return a stable snapshot for server-side authorized schedulers."""
        return tuple(self._sources[key] for key in sorted(self._sources))

    def __len__(self) -> int:
        return len(self._sources)


SOURCE_REGISTRY = SourceRegistry()


def _normalize_required_uses(required_uses: Iterable[SourceUse | str]) -> frozenset[SourceUse]:
    if isinstance(required_uses, str):
        raise SourceApprovalError("required_uses must be a sequence of explicit rights.")
    try:
        normalized = frozenset(SourceUse(use) for use in required_uses)
    except (TypeError, ValueError) as exc:
        raise SourceApprovalError("An unknown source use was requested.") from exc
    if not normalized:
        raise SourceApprovalError("At least one source use must be required.")
    return normalized


def _ensure_source_approved(
    source: JobSource,
    *,
    required_uses: frozenset[SourceUse],
    as_of: date,
) -> JobSource:
    if source.status is not SourceStatus.APPROVED:
        raise SourceApprovalError(
            f"Source '{source.source_id}' is {source.status.value}, not approved."
        )
    gaps = source.approval_gaps()
    if gaps:
        raise SourceApprovalError(
            f"Source '{source.source_id}' is missing approval evidence: {', '.join(gaps)}."
        )
    if source.reviewed_at > as_of:
        raise SourceApprovalError(f"Source '{source.source_id}' has a future review date.")
    if (as_of - source.reviewed_at).days > APPROVAL_MAX_AGE_DAYS:
        raise SourceApprovalError(
            f"Source '{source.source_id}' approval is stale; it must be reviewed again."
        )
    missing_uses = required_uses - source.permitted_uses
    if missing_uses:
        names = ", ".join(sorted(use.value for use in missing_uses))
        raise SourceApprovalError(
            f"Source '{source.source_id}' does not grant required uses: {names}."
        )
    return source


def require_approved_source(
    url_or_source: str | JobSource,
    *,
    registry: SourceRegistry = SOURCE_REGISTRY,
    required_uses: Iterable[SourceUse | str] = (
        SourceUse.AUTOMATED_FETCH,
        SourceUse.COMMERCIAL_DISPLAY,
    ),
    as_of: date | None = None,
) -> JobSource:
    """Return a fully reviewed source or raise :class:`SourceApprovalError`.

    Pass a complete HTTPS URL to validate its exact hostname and reviewed
    endpoint path, or pass a registered ``source_id`` / ``JobSource`` to
    validate that record. The default requires explicit rights for automated
    fetch and commercial display. Callers must add every other use they
    perform (such as AI processing, description caching, or redistribution)
    and that right must be separately granted by the source record. Candidate
    submission is a distinct right (`automated_submission`) and must never be
    inferred from permission to fetch or display a job. Reviews expire after
    180 days. Existing user-initiated ``fetch_job_posting`` calls are
    intentionally not routed through this automated-source gate.
    """
    normalized_uses = _normalize_required_uses(required_uses)
    review_date = date.today() if as_of is None else as_of
    if type(review_date) is not date:
        raise ValueError("as_of must be a date")

    if isinstance(url_or_source, JobSource):
        registered = registry.get(url_or_source.source_id)
        if registered is None or registered != url_or_source:
            raise SourceApprovalError("The supplied source is not registered in this registry.")
        return _ensure_source_approved(
            registered, required_uses=normalized_uses, as_of=review_date
        )

    if not isinstance(url_or_source, str) or not url_or_source:
        raise SourceApprovalError("A source URL or registered source_id is required.")

    looks_like_url = bool(
        _URL_SCHEME_RE.match(url_or_source)
        or "/" in url_or_source
        or "?" in url_or_source
        or "#" in url_or_source
        or "@" in url_or_source
    )
    if looks_like_url:
        parsed, hostname = _parse_source_url(url_or_source)
        matches = registry.matching_domain(hostname)
        if not matches:
            raise SourceApprovalError(f"No approved source matches hostname '{hostname}'.")
        if len(matches) != 1:
            raise SourceApprovalError(f"Hostname '{hostname}' matches multiple source records.")
        source = matches[0]
        endpoint, endpoint_host = _parse_source_url(source.endpoint_url)
        if hostname != endpoint_host or parsed.path != endpoint.path:
            raise SourceApprovalError(
                f"URL does not match the reviewed endpoint for source '{source.source_id}'."
            )
        return _ensure_source_approved(
            source, required_uses=normalized_uses, as_of=review_date
        )

    source = registry.get(url_or_source)
    if source is None:
        raise SourceApprovalError(f"Unknown source_id '{url_or_source}'.")
    return _ensure_source_approved(source, required_uses=normalized_uses, as_of=review_date)
